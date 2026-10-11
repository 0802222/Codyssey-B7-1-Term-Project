"""실패해도 서버는 멈추지 않고, 막아야 할 요청은 막는다. (EE-18)

AI 시간 초과 · DB 오류 · 비로그인 · 남의 대화 · CSRF 없음 — 모두 실제 로그인을 거친다.
"""

from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError
from sqlmodel import Session

from app.chat.fake_provider import FakeAIProvider, FakeMode
from app.chat.provider import get_ai_provider


def error_code(response):
    return response.json()["error"]["code"]


def start_conversation(user):
    response = user.post("/api/conversations", json={})
    assert response.status_code == 201
    return response.json()["id"]


def test_ai_timeout_is_explained_saved_and_server_keeps_running(app, user):
    conversation_id = start_conversation(user)
    app.dependency_overrides[get_ai_provider] = lambda: FakeAIProvider(mode=FakeMode.TIMEOUT)

    timed_out = user.ask(conversation_id, "도커가 뭐야?")

    assert timed_out.status_code == 504
    assert error_code(timed_out) == "AI_TIMEOUT"
    assert timed_out.json()["error"]["message"]  # 화면에 보여 줄 한국어 안내
    assert user.client.get("/health").status_code == 200

    # 실패한 턴은 기록에 failed 로 남는다.
    turn = user.client.get(f"/api/conversations/{conversation_id}").json()["turns"][0]
    assert (turn["status"], turn["error_code"], turn["answer"]) == ("failed", "AI_TIMEOUT", None)

    # AI 가 돌아오면 새 요청은 정상으로 답한다.
    app.dependency_overrides.pop(get_ai_provider)
    assert user.ask(conversation_id, "도커가 뭐야?").status_code == 200


def test_db_error_returns_503_and_server_keeps_running(user, monkeypatch):
    def failing_commit(self):
        raise OperationalError("INSERT", {}, Exception("test-only DB failure"))

    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", failing_commit)
        failed = user.post("/api/conversations", json={})

    assert failed.status_code == 503
    assert error_code(failed) == "DB_ERROR"
    assert user.client.get("/health").status_code == 200
    assert user.post("/api/conversations", json={}).status_code == 201


PROTECTED_APIS = [
    ("get", "/api/auth/me"),
    ("post", "/api/auth/logout"),
    ("post", "/api/conversations"),
    ("get", "/api/me/conversations"),
    ("get", f"/api/conversations/{uuid4()}"),
    ("get", "/api/me/chats"),
    ("post", "/api/chat"),
]


@pytest.mark.parametrize(("method", "path"), PROTECTED_APIS)
def test_logged_out_api_is_401(client, method, path):
    response = getattr(client, method)(path)

    assert response.status_code == 401
    assert error_code(response) == "AUTH_REQUIRED"


@pytest.mark.parametrize("path", ["/chat", "/history"])
def test_logged_out_page_redirects_to_login(client, path):
    response = client.get(path, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_other_users_conversation_is_hidden(user, other_user):
    conversation_id = start_conversation(user)
    assert user.ask(conversation_id, "내 질문").status_code == 200

    # 남의 대화는 조회도, 질문도 404 (존재 여부를 알려 주지 않음)
    peek = other_user.client.get(f"/api/conversations/{conversation_id}")
    assert peek.status_code == 404
    assert error_code(peek) == "CONVERSATION_NOT_FOUND"
    sneak = other_user.ask(conversation_id, "끼어들기")
    assert sneak.status_code == 404
    assert error_code(sneak) == "CONVERSATION_NOT_FOUND"

    # 목록에도 보이지 않고, 주인의 기록은 그대로다.
    assert other_user.client.get("/api/me/conversations").json()["items"] == []
    assert other_user.client.get("/api/me/chats").json()["items"] == []
    turns = user.client.get(f"/api/conversations/{conversation_id}").json()["turns"]
    assert [t["question"] for t in turns] == ["내 질문"]


@pytest.mark.parametrize("token", [None, "wrong-token"])
@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/conversations", {}),
        ("/api/chat", None),
        ("/api/auth/logout", None),
    ],
)
def test_state_change_without_valid_csrf_is_403(user, token, path, body):
    if path == "/api/chat":
        body = {
            "conversation_id": start_conversation(user),
            "question": "CSRF 없이 질문",
            "level": "easy",
            "client_request_id": str(uuid4()),
        }
    headers = {} if token is None else {"X-CSRF-Token": token}

    response = user.client.post(path, headers=headers, json=body)

    assert response.status_code == 403
    assert error_code(response) == "CSRF_REJECTED"
    # 막힌 요청은 아무것도 바꾸지 않는다: 로그인도 그대로 유지된다.
    assert user.client.get("/api/auth/me").status_code == 200

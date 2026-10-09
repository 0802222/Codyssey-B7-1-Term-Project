"""내 기록 화면과 이어서 질문이 기대는 서버 동작을 실제 API 로 확인한다. (C 담당, EE-17)

화면(app/static/js/history.js, chat.js 의 이어서 질문)은 이렇게 기댄다.
- 서버가 대화를 만들 때 붙이는 제목이 HISTORY_RULES.untitled("새 대화")면
  첫 질문 앞부분으로 바꿔 보여 준다
- 목록은 서버가 정렬해 준 순서(최근에 질문한 대화가 위) 그대로, limit·offset 으로 page_size 개씩
- 상세의 턴은 오래된 순이고, 답이 없는 턴은 answer 가 null 이며 status·error_code 로 안내를 고른다
- 시각에 UTC 표시(Z 또는 +00:00)가 있어야 브라우저의 new Date() 가 한국 시간으로 바르게 바꾼다
- 없는 대화와 남의 대화는 똑같이 404 이고, 그 문구가 화면이 묻지 않고 보여 주는 문구와 같다
- 이어서 질문은 conversation_id 만 이어 쓴다 — 서버가 그 대화의 완료된 턴을 문맥으로 쓴다
실제 가입·로그인·CSRF 를 거치고 AI 만 가짜로 끼운다. 서버(A·B 영역)가 바뀌면 여기서 실패한다 —
그때는 화면도 같이 바꾼다.
"""

import re
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.chat.fake_provider import FakeAIProvider
from app.chat.provider import AITimeoutError, get_ai_provider
from app.web.router import HISTORY_RULES

JS_DIR = Path(__file__).parents[2] / "app" / "static" / "js"
PASSWORD = "history-pass-1"
UTC_TIME = re.compile(r"(Z|\+00:00)$")


def script(name: str) -> str:
    return (JS_DIR / name).read_text(encoding="utf-8")


class RecordingProvider(FakeAIProvider):
    """가짜 AI. 받은 메시지(문맥 + 지금 질문)를 남기고, error 를 넣으면 그 오류를 낸다."""

    def __init__(self):
        super().__init__(reply="테스트 답변")
        self.received: list[list[str]] = []
        self.error = None

    async def generate_reply(self, messages, **kwargs):
        self.received.append([message.content for message in messages])
        if self.error is not None:
            raise self.error
        return await super().generate_reply(messages, **kwargs)


@pytest.fixture
def ai(app):
    provider = RecordingProvider()
    app.dependency_overrides[get_ai_provider] = lambda: provider
    yield provider
    app.dependency_overrides.pop(get_ai_provider, None)


def sign_in(client, settings, email):
    """화면과 같은 순서로 가입·로그인한 client 와 X-CSRF-Token 헤더"""
    account = {"email": email, "password": PASSWORD}
    origin = {"Origin": settings.site_origin}
    assert client.post("/api/auth/signup", headers=origin, json=account).status_code == 201
    login = client.post("/api/auth/login", headers=origin, json=account)
    assert login.status_code == 200
    return SimpleNamespace(client=client, csrf={"X-CSRF-Token": login.json()["csrf_token"]})


@pytest.fixture
def me(client, settings):
    return sign_in(client, settings, "me@example.com")


@pytest.fixture
def someone(app, settings, me):
    """다른 사용자 — 쿠키가 따로인 client"""
    with TestClient(app, raise_server_exceptions=False) as other:
        yield sign_in(other, settings, "someone@example.com")


def new_conversation(user) -> dict:
    response = user.client.post("/api/conversations", headers=user.csrf, json={})
    assert response.status_code == 201
    return response.json()


def ask(user, conversation_id, question, level="easy"):
    body = {
        "conversation_id": conversation_id,
        "question": question,
        "level": level,
        "client_request_id": str(uuid4()),
    }
    return user.client.post("/api/chat", headers=user.csrf, json=body)


def list_page(user, offset=0):
    # history.js 의 loadConversations 가 만드는 주소 그대로
    return user.client.get(
        f"/api/me/conversations?limit={HISTORY_RULES.page_size}&offset={offset}"
    )


def test_screen_builds_the_list_address_this_way():
    assert (
        "apiGet(`/api/me/conversations?limit=${PAGE_SIZE}&offset=${nextOffset}`)"
        in script("history.js")
    )


# ── 제목 ──


def test_new_conversation_gets_the_title_the_screen_replaces(me, ai):
    # 서버가 제목을 채우게 되면(첫 질문 일부 등) 화면은 그 제목을 그대로 쓴다
    # — 그때 이 테스트를 고친다
    created = new_conversation(me)
    assert ask(me, created["id"], "API가 뭐야?").status_code == 200

    assert created["title"] == HISTORY_RULES.untitled
    item = list_page(me).json()["items"][0]
    # 질문한 뒤에도 그대로 → 화면이 첫 질문으로 바꾼다
    assert item["title"] == HISTORY_RULES.untitled
    detail = me.client.get(f"/api/conversations/{created['id']}").json()
    assert detail["turns"][0]["question"] == "API가 뭐야?"  # 화면이 제목 대신 쓰는 값


# ── 목록 ──


def test_list_comes_in_pages_of_the_screen_size(me):
    ids = [new_conversation(me)["id"] for _ in range(HISTORY_RULES.page_size + 5)]

    first = list_page(me).json()
    second = list_page(me, offset=HISTORY_RULES.page_size).json()

    assert (len(first["items"]), first["has_more"]) == (HISTORY_RULES.page_size, True)
    assert (len(second["items"]), second["has_more"]) == (5, False)
    shown = [item["id"] for item in first["items"] + second["items"]]
    assert shown == ids[::-1]  # 최근에 만든 것이 위, 두 쪽을 이어도 빠지거나 겹치지 않는다


def test_asking_again_moves_an_old_conversation_to_the_top(me, ai):
    older = new_conversation(me)["id"]
    newer = new_conversation(me)["id"]
    assert [item["id"] for item in list_page(me).json()["items"]] == [newer, older]

    assert ask(me, older, "이어서 질문").status_code == 200

    # 화면은 다시 정렬하지 않고 서버 순서(updated_at 최신 → 오래된)를 그대로 보여 준다
    assert [item["id"] for item in list_page(me).json()["items"]] == [older, newer]


def test_list_shows_only_my_conversations(me, someone):
    mine = new_conversation(me)["id"]
    new_conversation(someone)

    assert [item["id"] for item in list_page(me).json()["items"]] == [mine]


def test_reading_history_logged_out_is_401_for_the_login_redirect(client):
    # apiGet 은 401 이면 로그인 화면으로 보낸다 (페이지 /history 는 303, API 는 401 — 명세 1장)
    assert client.get("/api/me/conversations?limit=20&offset=0").status_code == 401
    assert client.get(f"/api/conversations/{uuid4()}").status_code == 401


# ── 상세 ──


def test_detail_turns_are_oldest_first_and_unanswered_turns_have_no_answer(me, ai):
    conversation = new_conversation(me)["id"]
    assert ask(me, conversation, "첫 질문", level="easy").status_code == 200
    ai.error = AITimeoutError()
    assert ask(me, conversation, "두 번째 질문", level="beginner").status_code == 504
    ai.error = None
    assert ask(me, conversation, "세 번째 질문", level="advanced").status_code == 200

    turns = me.client.get(f"/api/conversations/{conversation}").json()["turns"]

    assert [turn["question"] for turn in turns] == ["첫 질문", "두 번째 질문", "세 번째 질문"]
    assert [turn["level"] for turn in turns] == ["easy", "beginner", "advanced"]
    # history.js 의 hasAnswer·missingNote 가 보는 값
    assert [(turn["status"], turn["answer"] is None) for turn in turns] == [
        ("completed", False),
        ("failed", True),
        ("completed", False),
    ]
    assert turns[1]["error_code"] == "AI_TIMEOUT"


def test_times_carry_a_utc_mark_for_the_korea_time_conversion(me, ai):
    # 표시가 없으면 브라우저가 한국 시간으로 읽어서 9시간 어긋나게 보인다
    conversation = new_conversation(me)["id"]
    assert ask(me, conversation, "시각 확인").status_code == 200
    item = list_page(me).json()["items"][0]
    detail = me.client.get(f"/api/conversations/{conversation}").json()

    times = [
        item["created_at"],
        item["updated_at"],
        detail["conversation"]["created_at"],
        detail["turns"][0]["created_at"],
    ]
    for value in times:
        assert UTC_TIME.search(value), value
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        assert parsed.utcoffset() == UTC.utcoffset(None)


def test_missing_and_others_conversations_look_the_same_as_the_screen_message(me, someone):
    # 화면은 모양이 틀린 id 면 묻지 않고 CONVERSATION_NOT_FOUND_MESSAGE 를 보여 준다
    # — 서버 404 와 같은 말이어야 사용자에게는 어떤 경우든 같은 안내로 보인다
    screen = re.search(r'CONVERSATION_NOT_FOUND_MESSAGE = "([^"]+)";', script("api.js")).group(1)
    others = new_conversation(someone)["id"]

    for conversation in (others, str(uuid4())):
        response = me.client.get(f"/api/conversations/{conversation}")
        assert response.status_code == 404
        error = response.json()["error"]
        assert (error["code"], error["message"]) == ("CONVERSATION_NOT_FOUND", screen)


# ── 이어서 질문 ──


def test_continuing_a_conversation_sends_its_answered_turns_as_context(me, ai):
    # 이어서 질문은 화면이 conversation_id 만 이어 쓴다
    # — 서버가 그 대화의 완료된 턴을 문맥으로 붙인다
    conversation = new_conversation(me)["id"]
    assert ask(me, conversation, "API가 뭐야?").status_code == 200
    ai.error = AITimeoutError()
    assert ask(me, conversation, "답을 못 받은 질문").status_code == 504
    ai.error = None

    # 나중에(새로고침·다른 날) 같은 대화로 이어서 묻는다
    assert ask(me, conversation, "예시 하나 더").status_code == 200

    # 완료된 턴(질문·답변)만 문맥 — 답을 못 받은 질문은 빠진다 (chat.js 도 완료된 턴만 그린다)
    assert ai.received[-1] == ["API가 뭐야?", "테스트 답변", "예시 하나 더"]

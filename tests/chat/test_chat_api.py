"""채팅 API의 인증·저장·문맥·중복 요청 계약을 HTTP로 확인한다. (EE-13)"""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, select

from app.chat.provider import (
    AIResult,
    AITimeoutError,
    AIUnavailableError,
    AIUpstreamError,
    get_ai_provider,
)
from app.db.models import ChatTurn, Conversation, User


class SpyProvider:
    """실제 AI 대신 호출 인자를 보관하고, 원하는 답변이나 오류를 돌려준다."""

    def __init__(self):
        self.calls = []
        self.text = "테스트 답변"
        self.error = None
        self.before_reply = None

    async def generate_reply(self, messages, *, system, timeout_seconds, max_output_tokens):
        self.calls.append(
            {
                "messages": [(message.role, message.content) for message in messages],
                "system": system,
                "timeout_seconds": timeout_seconds,
                "max_output_tokens": max_output_tokens,
            }
        )
        if self.before_reply is not None:
            self.before_reply()
        if self.error is not None:
            raise self.error
        return AIResult(text=self.text, model="test-spy")


@pytest.fixture
def provider(app):
    spy = SpyProvider()
    app.dependency_overrides[get_ai_provider] = lambda: spy
    yield spy
    app.dependency_overrides.pop(get_ai_provider, None)


@pytest.fixture
def chat_client(app, logged_in_client, current_user):
    # 공통 로그인 fixture는 인증만 대신하므로 외래키에 필요한 사용자 행을 넣는다.
    with Session(app.state.engine) as session:
        session.add(User(id=current_user.id, email=current_user.email, password_hash="test-hash"))
        session.commit()
    return logged_in_client


@pytest.fixture
def conversation(chat_client):
    response = chat_client.post("/api/conversations", json={})
    assert response.status_code == 201
    return response.json()["id"]


@pytest.fixture
def payload(conversation):
    return {
        "conversation_id": conversation,
        "question": "API가 뭐야?",
        "level": "easy",
        "client_request_id": str(uuid4()),
    }


@pytest.fixture
def seed_turn(app, current_user):
    def seed(conversation_id, *, question="이전 질문", answer="이전 답변", status="completed"):
        with Session(app.state.engine) as session:
            turn = ChatTurn(
                conversation_id=UUID(conversation_id),
                user_id=current_user.id,
                client_request_id=uuid4(),
                request_id="seed-request",
                level="easy",
                question=question,
                answer=answer if status == "completed" else None,
                status=status,
                error_code="AI_TIMEOUT" if status == "failed" else None,
                created_at=datetime(2020, 1, 1, tzinfo=UTC),
            )
            session.add(turn)
            session.commit()
            session.refresh(turn)
            return turn.id

    return seed


def _turns(app):
    with Session(app.state.engine) as session:
        return session.exec(select(ChatTurn).order_by(ChatTurn.id)).all()


def _assert_error(response, status, code):
    assert response.status_code == status
    error = response.json()["error"]
    assert error["code"] == code
    assert error["message"]
    assert error["request_id"] == response.headers["X-Request-ID"]


def test_chat_requires_login(client, provider, app):
    response = client.post(
        "/api/chat",
        json={
            "conversation_id": str(uuid4()),
            "question": "질문",
            "level": "easy",
            "client_request_id": str(uuid4()),
        },
    )

    _assert_error(response, 401, "AUTH_REQUIRED")
    assert provider.calls == []
    assert _turns(app) == []


@pytest.mark.parametrize("csrf", [None, "wrong-token"])
def test_chat_checks_real_session_csrf(client, settings, provider, app, csrf):
    # 이 테스트는 로그인·CSRF를 대체하지 않고 실제 가입과 로그인을 거친다.
    credentials = {"email": "real-auth@example.com", "password": "test-password"}
    origin = {"Origin": settings.site_origin}
    assert client.post("/api/auth/signup", headers=origin, json=credentials).status_code == 201
    login = client.post("/api/auth/login", headers=origin, json=credentials)
    assert login.status_code == 200
    valid_headers = {"X-CSRF-Token": login.json()["csrf_token"]}
    created = client.post("/api/conversations", headers=valid_headers, json={})
    assert created.status_code == 201
    headers = {} if csrf is None else {"X-CSRF-Token": csrf}

    response = client.post(
        "/api/chat",
        headers=headers,
        json={
            "conversation_id": created.json()["id"],
            "question": "질문",
            "level": "easy",
            "client_request_id": str(uuid4()),
        },
    )

    _assert_error(response, 403, "CSRF_REJECTED")
    assert provider.calls == []
    assert _turns(app) == []


@pytest.mark.parametrize("belongs_to_other_user", [False, True])
def test_missing_and_other_users_conversations_are_404(
    chat_client, app, provider, payload, belongs_to_other_user
):
    missing_id = uuid4()
    if belongs_to_other_user:
        with Session(app.state.engine) as session:
            other = User(email="other@example.com", password_hash="test-hash")
            session.add(other)
            session.commit()
            session.refresh(other)
            session.add(Conversation(id=missing_id, user_id=other.id, title="남의 대화"))
            session.commit()
    payload["conversation_id"] = str(missing_id)

    response = chat_client.post("/api/chat", json=payload)

    _assert_error(response, 404, "CONVERSATION_NOT_FOUND")
    assert provider.calls == []
    assert _turns(app) == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("question", ""),
        ("question", " \n\t "),
        ("question", "가" * 2001),
        ("level", "unknown"),
        ("conversation_id", "not-a-uuid"),
        ("client_request_id", "not-a-uuid"),
        ("user_id", 999),
        ("question", None),
    ],
    ids=[
        "empty",
        "whitespace",
        "too-long",
        "level",
        "conversation-uuid",
        "request-uuid",
        "extra",
        "null",
    ],
)
def test_invalid_input_does_not_save_or_call_ai(chat_client, app, provider, payload, field, value):
    payload[field] = value

    response = chat_client.post("/api/chat", json=payload)

    _assert_error(response, 422, "VALIDATION_ERROR")
    assert provider.calls == []
    assert _turns(app) == []


@pytest.mark.parametrize("question", ["가", "가" * 2000], ids=["one-character", "2000-characters"])
def test_question_boundaries_are_accepted(chat_client, provider, payload, question):
    payload["question"] = question

    response = chat_client.post("/api/chat", json=payload)

    assert response.status_code == 200
    assert provider.calls[0]["messages"][-1] == ("user", question)


def test_success_commits_pending_before_ai_and_completed_after(chat_client, app, provider, payload):
    observed = []

    def observe_saved_turn():
        # 별도 세션에서도 보여야 AI 호출 전에 commit한 것을 확인할 수 있다.
        observed.extend((turn.status, turn.answer) for turn in _turns(app))

    provider.before_reply = observe_saved_turn
    payload["question"] = "  API가 뭐야? \n"

    response = chat_client.post("/api/chat", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "request_id",
        "turn_id",
        "conversation_id",
        "level",
        "question",
        "answer",
        "status",
        "created_at",
    }
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert body["conversation_id"] == payload["conversation_id"]
    assert body["level"] == "easy"
    assert body["question"] == "API가 뭐야?"
    assert body["answer"] == provider.text
    assert body["status"] == "completed"
    created_at = datetime.fromisoformat(body["created_at"].replace("Z", "+00:00"))
    assert created_at.utcoffset() == timedelta(0)
    assert observed == [("pending", None)]
    saved = _turns(app)[0]
    assert saved.id == body["turn_id"]
    assert saved.status == "completed"
    assert saved.answer == provider.text
    assert saved.completed_at is not None


def test_ai_receives_current_settings(chat_client, settings, provider, payload):
    settings.ai_timeout_seconds = 4.5
    settings.ai_max_output_tokens = 123

    response = chat_client.post("/api/chat", json=payload)

    assert response.status_code == 200
    assert provider.calls[0]["timeout_seconds"] == 4.5
    assert provider.calls[0]["max_output_tokens"] == 123


def test_level_switch_uses_the_current_request(chat_client, provider, payload):
    for level, label in [("easy", "아주 쉽게"), ("beginner", "입문자"), ("advanced", "전공자")]:
        payload.update(level=level, client_request_id=str(uuid4()))
        response = chat_client.post("/api/chat", json=payload)
        assert response.status_code == 200
        assert f"현재 설명 수준은 {level}이다" in provider.calls[-1]["system"]
        assert f"{label}:" in provider.calls[-1]["system"]


def test_repeated_short_question_keeps_context_when_switching_to_advanced(
    chat_client, provider, payload
):
    # 모의 답변 품질이 아니라, #54의 3턴에 실제로 전달되는 문맥과 수준을 확인한다.
    turns = [
        ("easy", "도커?", "첫 요청의 모의 답변"),
        ("easy", "더 쉽게", "두 번째 요청의 모의 답변"),
        ("advanced", "도커?", "세 번째 요청의 모의 답변"),
    ]
    for level, question, answer in turns:
        provider.text = answer
        payload.update(level=level, question=question, client_request_id=str(uuid4()))
        response = chat_client.post("/api/chat", json=payload)

        assert response.status_code == 200
        assert response.json()["status"] == "completed"
        assert f"현재 설명 수준은 {level}이다" in provider.calls[-1]["system"]

    first_pair = [("user", "도커?"), ("assistant", turns[0][2])]
    second_pair = [("user", "더 쉽게"), ("assistant", turns[1][2])]
    assert len(provider.calls) == 3
    assert [len(call["messages"]) for call in provider.calls] == [1, 3, 5]
    assert provider.calls[0]["messages"] == [("user", "도커?")]
    assert provider.calls[1]["messages"] == first_pair + [("user", "더 쉽게")]
    assert provider.calls[2]["messages"] == first_pair + second_pair + [("user", "도커?")]
    assert "전공자:" in provider.calls[2]["system"]
    assert "아주 쉽게:" not in provider.calls[2]["system"]
    assert "현재 설명 수준으로 다시 설명한다" in provider.calls[2]["system"]


def test_context_contains_only_completed_turns_in_this_conversation(
    chat_client, provider, payload, seed_turn
):
    seed_turn(payload["conversation_id"], question="완료 질문", answer="완료 답변")
    for status in ["pending", "failed", "interrupted"]:
        seed_turn(payload["conversation_id"], question=f"{status} 질문", status=status)
    other_conversation = chat_client.post("/api/conversations", json={}).json()["id"]
    seed_turn(other_conversation, question="다른 대화 질문")

    response = chat_client.post("/api/chat", json=payload)

    assert response.status_code == 200
    assert provider.calls[0]["messages"] == [
        ("user", "완료 질문"),
        ("assistant", "완료 답변"),
        ("user", payload["question"]),
    ]


@pytest.mark.parametrize(
    ("max_turns", "max_chars", "include_last_pair"),
    [(1, 12000, True), (5, 6, True), (0, 12000, False), (5, 0, False)],
)
def test_context_respects_settings_and_zero_disables_history(
    chat_client, settings, provider, payload, seed_turn, max_turns, max_chars, include_last_pair
):
    settings.context_turns = max_turns
    settings.context_max_chars = max_chars
    # 같은 시각이면 ID순이다. 오래된 한 쌍을 빼고 최신 Q/A를 통째로 남긴다.
    seed_turn(payload["conversation_id"], question="Q1", answer="A1")
    seed_turn(payload["conversation_id"], question="Q2", answer="A2")

    response = chat_client.post("/api/chat", json=payload)

    assert response.status_code == 200
    expected = [("user", "Q2"), ("assistant", "A2")] if include_last_pair else []
    assert provider.calls[0]["messages"] == expected + [("user", payload["question"])]


@pytest.mark.parametrize(
    ("failure", "status", "code"),
    [
        (AITimeoutError, 504, "AI_TIMEOUT"),
        (AIUpstreamError, 502, "AI_UPSTREAM_ERROR"),
        (AIUnavailableError, 503, "AI_UNAVAILABLE"),
        (None, 502, "AI_UPSTREAM_ERROR"),
    ],
)
def test_ai_failure_is_saved_sanitized_and_replayed_without_another_call(
    chat_client, app, provider, payload, caplog, failure, status, code
):
    marker = "SYNTHETIC-UPSTREAM-SECRET"
    payload["question"] = "로그에 넣지 않는 질문 원문"
    if failure is None:
        provider.text = " \n "
    else:
        provider.error = failure(marker)

    with caplog.at_level(logging.INFO, logger="easyexplain"):
        response = chat_client.post("/api/chat", json=payload)
        replay = chat_client.post("/api/chat", json=payload)

    _assert_error(response, status, code)
    _assert_error(replay, status, code)
    assert len(provider.calls) == 1
    saved = _turns(app)
    assert len(saved) == 1
    assert saved[0].status == "failed"
    assert saved[0].answer is None
    assert saved[0].error_code == code
    assert saved[0].completed_at is not None
    assert marker not in response.text + caplog.text
    assert payload["question"] not in caplog.text
    events = [record.getMessage().split()[0] for record in caplog.records]
    assert "ai_call_start" in events
    assert "ai_call_failed" in events
    assert "ai_call_success" not in events


def test_completed_duplicate_returns_saved_answer_without_calling_ai(
    chat_client, app, provider, payload
):
    first = chat_client.post("/api/chat", json=payload)
    provider.text = "다시 호출하면 달라지는 답변"

    second = chat_client.post("/api/chat", json=payload)

    assert first.status_code == second.status_code == 200
    assert second.json()["turn_id"] == first.json()["turn_id"]
    assert second.json()["answer"] == first.json()["answer"]
    assert len(provider.calls) == 1
    assert len(_turns(app)) == 1


@pytest.mark.parametrize("changed_field", ["question", "level", "conversation_id"])
def test_duplicate_key_with_changed_content_is_conflict(
    chat_client, app, provider, payload, changed_field
):
    assert chat_client.post("/api/chat", json=payload).status_code == 200
    if changed_field == "conversation_id":
        payload[changed_field] = chat_client.post("/api/conversations", json={}).json()["id"]
    else:
        payload[changed_field] = "다른 질문" if changed_field == "question" else "advanced"

    response = chat_client.post("/api/chat", json=payload)

    _assert_error(response, 409, "REQUEST_CONFLICT")
    assert len(provider.calls) == 1
    assert len(_turns(app)) == 1


def test_pending_duplicate_is_busy_without_calling_ai(chat_client, app, provider, payload):
    with Session(app.state.engine) as session:
        session.add(
            ChatTurn(
                conversation_id=UUID(payload["conversation_id"]),
                user_id=1,
                client_request_id=UUID(payload["client_request_id"]),
                request_id="original-request",
                level=payload["level"],
                question=payload["question"],
                status="pending",
            )
        )
        session.commit()

    response = chat_client.post("/api/chat", json=payload)

    _assert_error(response, 409, "CHAT_BUSY")
    assert provider.calls == []
    assert len(_turns(app)) == 1


def test_new_key_retries_a_failed_question(chat_client, app, provider, payload):
    provider.error = AITimeoutError("synthetic timeout")
    _assert_error(chat_client.post("/api/chat", json=payload), 504, "AI_TIMEOUT")
    provider.error = None
    payload["client_request_id"] = str(uuid4())

    response = chat_client.post("/api/chat", json=payload)

    assert response.status_code == 200
    assert len(provider.calls) == 2
    assert [turn.status for turn in _turns(app)] == ["failed", "completed"]


def test_pending_insert_failure_is_503_and_does_not_call_ai(
    chat_client, app, provider, payload, caplog
):
    def fail_turn_insert(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO chat_turns"):
            raise OperationalError("synthetic insert", {}, Exception("synthetic DB failure"))

    engine = app.state.engine
    event.listen(engine, "before_cursor_execute", fail_turn_insert)
    try:
        with caplog.at_level(logging.INFO, logger="easyexplain"):
            response = chat_client.post("/api/chat", json=payload)
    finally:
        event.remove(engine, "before_cursor_execute", fail_turn_insert)

    _assert_error(response, 503, "DB_ERROR")
    assert provider.calls == []
    assert _turns(app) == []
    assert "db_save_failed" in caplog.text

"""실제 채팅 흐름에서 AI 호출만 집계하고 429도 실패 턴으로 저장한다. (EE-16)"""

import asyncio
import logging
from datetime import date, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, select

from app.auth.dependencies import CurrentUser, get_current_user, require_csrf
from app.chat import rate_limit
from app.chat.fake_provider import FakeAIProvider
from app.chat.provider import get_ai_provider
from app.chat.schemas import ChatRequest
from app.chat.service import answer_question
from app.conversations import repository
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.db.models import ChatTurn, Conversation, User
from app.main import create_app


class CountedProvider(FakeAIProvider):
    def __init__(self):
        super().__init__()
        self.calls = 0

    async def generate_reply(self, *args, **kwargs):
        self.calls += 1
        return await super().generate_reply(*args, **kwargs)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    clock = SimpleNamespace(seconds=100.0, day=date(2026, 10, 8))
    monkeypatch.setattr(rate_limit, "monotonic", lambda: clock.seconds)
    monkeypatch.setattr(rate_limit, "_today_utc", lambda: clock.day)
    return clock


@pytest.fixture
def provider(app):
    fake = CountedProvider()
    app.dependency_overrides[get_ai_provider] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_ai_provider, None)


@pytest.fixture
def chat_client(app, settings, logged_in_client, current_user):
    settings.user_requests_per_minute = 1
    settings.daily_request_limit = 10
    with Session(app.state.engine) as session:
        session.add(User(id=current_user.id, email=current_user.email, password_hash="test-only"))
        session.commit()
    return logged_in_client


@pytest.fixture
def payload(chat_client):
    created = chat_client.post("/api/conversations", json={})
    assert created.status_code == 201
    return _payload(created.json()["id"])


def _payload(conversation_id):
    return {
        "conversation_id": str(conversation_id),
        "question": "비밀 질문 원문",
        "level": "easy",
        "client_request_id": str(uuid4()),
    }


def _error(response, status, code):
    assert response.status_code == status
    error = response.json()["error"]
    assert error["code"] == code
    assert error["message"]
    assert error["request_id"] == response.headers["X-Request-ID"]


def _turns(app):
    with Session(app.state.engine) as session:
        return session.exec(select(ChatTurn).order_by(ChatTurn.id)).all()


def _add_user_conversation(app, user_id):
    with Session(app.state.engine) as session:
        session.add(
            User(id=user_id, email=f"quota-{user_id}@example.com", password_hash="test-only")
        )
        session.commit()
        conversation = Conversation(user_id=user_id, title="테스트 대화")
        session.add(conversation)
        session.commit()
        session.refresh(conversation)
        return conversation.id


def _act_as(app, user_id):
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=user_id, email=f"quota-{user_id}@example.com"
    )


def test_429_is_saved_and_same_key_stays_429_after_window_resets(
    chat_client, settings, provider, payload, app, clock
):
    settings.daily_request_limit = 2
    assert chat_client.post("/api/chat", json=payload).status_code == 200
    denied = dict(payload, client_request_id=str(uuid4()))

    _error(chat_client.post("/api/chat", json=denied), 429, "RATE_LIMITED")
    saved = _turns(app)[1]
    assert (saved.status, saved.error_code, saved.answer) == ("failed", "RATE_LIMITED", None)
    assert saved.completed_at is not None
    assert provider.calls == 1
    clock.seconds += 60
    _error(chat_client.post("/api/chat", json=denied), 429, "RATE_LIMITED")
    assert len(_turns(app)) == 2

    # 429를 저장하거나 재전송해도 전체 한도를 소모하지 않는다. 새 키는 다시 시도한다.
    retry = dict(payload, client_request_id=str(uuid4()))
    assert chat_client.post("/api/chat", json=retry).status_code == 200
    assert provider.calls == 2


@pytest.mark.parametrize(
    ("mode", "status", "code"),
    [
        ("timeout", 504, "AI_TIMEOUT"),
        ("upstream_error", 502, "AI_UPSTREAM_ERROR"),
        ("unavailable", 503, "AI_UNAVAILABLE"),
        ("empty", 502, "AI_UPSTREAM_ERROR"),
    ],
)
def test_fake_failure_consumes_allowance_but_replay_does_not_call_ai(
    chat_client, provider, payload, app, caplog, mode, status, code
):
    provider.mode = mode
    with caplog.at_level(logging.INFO, logger="easyexplain"):
        failed = chat_client.post("/api/chat", json=payload)
        replay = chat_client.post("/api/chat", json=payload)
        retry = dict(payload, client_request_id=str(uuid4()))
        limited = chat_client.post("/api/chat", json=retry)

    _error(failed, status, code)
    _error(replay, status, code)
    _error(limited, 429, "RATE_LIMITED")
    assert provider.calls == 1
    assert [(turn.status, turn.error_code, turn.answer) for turn in _turns(app)] == [
        ("failed", code, None),
        ("failed", "RATE_LIMITED", None),
    ]
    assert payload["question"] not in caplog.text
    assert "모의 AI" not in failed.text + caplog.text
    assert "ai_call_failed" in caplog.text


@pytest.mark.parametrize("invalid", [{"question": " "}, {"level": "wrong"}, {"user_id": 999}])
def test_validation_rejection_does_not_consume_allowance(
    chat_client, settings, provider, payload, app, invalid
):
    settings.daily_request_limit = 1
    _error(chat_client.post("/api/chat", json=dict(payload, **invalid)), 422, "VALIDATION_ERROR")
    assert provider.calls == 0
    assert _turns(app) == []

    assert chat_client.post("/api/chat", json=payload).status_code == 200
    assert provider.calls == 1


def test_replay_and_conflict_do_not_consume_allowance(chat_client, settings, provider, payload):
    settings.user_requests_per_minute = 2
    settings.daily_request_limit = 2
    first = chat_client.post("/api/chat", json=payload)
    assert first.status_code == 200
    replay = chat_client.post("/api/chat", json=payload)
    assert replay.status_code == 200
    assert replay.json()["turn_id"] == first.json()["turn_id"]
    _error(
        chat_client.post("/api/chat", json=dict(payload, question="다른 질문")),
        409,
        "REQUEST_CONFLICT",
    )

    second = dict(payload, client_request_id=str(uuid4()))
    assert chat_client.post("/api/chat", json=second).status_code == 200
    assert provider.calls == 2


def test_missing_or_other_conversation_does_not_consume_allowance(
    chat_client, settings, provider, payload, app
):
    settings.daily_request_limit = 1
    other_id = _add_user_conversation(app, 2)
    for conversation_id in [uuid4(), other_id]:
        invalid = dict(payload, conversation_id=str(conversation_id))
        _error(chat_client.post("/api/chat", json=invalid), 404, "CONVERSATION_NOT_FOUND")
    assert provider.calls == 0

    assert chat_client.post("/api/chat", json=payload).status_code == 200
    assert provider.calls == 1


def test_login_and_csrf_rejections_do_not_consume_allowance(client, settings, provider):
    settings.user_requests_per_minute = settings.daily_request_limit = 1
    _error(client.post("/api/chat", json=_payload(uuid4())), 401, "AUTH_REQUIRED")
    credentials = {"email": "quota-auth@example.com", "password": "test-password"}
    origin = {"Origin": settings.site_origin}
    assert client.post("/api/auth/signup", headers=origin, json=credentials).status_code == 201
    login = client.post("/api/auth/login", headers=origin, json=credentials)
    assert login.status_code == 200
    headers = {"X-CSRF-Token": login.json()["csrf_token"]}
    created = client.post("/api/conversations", headers=headers, json={})
    assert created.status_code == 201
    payload = _payload(created.json()["id"])
    _error(client.post("/api/chat", json=payload), 403, "CSRF_REJECTED")

    assert client.post("/api/chat", headers=headers, json=payload).status_code == 200
    assert provider.calls == 1


def test_pending_duplicate_does_not_consume_allowance(
    chat_client, settings, provider, payload, app
):
    settings.daily_request_limit = 1
    with Session(app.state.engine) as session:
        session.add(
            ChatTurn(
                conversation_id=UUID(payload["conversation_id"]),
                user_id=1,
                client_request_id=UUID(payload["client_request_id"]),
                request_id="pending-request",
                level=payload["level"],
                question=payload["question"],
                status="pending",
            )
        )
        session.commit()
    _error(chat_client.post("/api/chat", json=payload), 409, "CHAT_BUSY")

    fresh = dict(payload, client_request_id=str(uuid4()))
    assert chat_client.post("/api/chat", json=fresh).status_code == 200
    assert provider.calls == 1


def test_context_db_failure_does_not_consume_allowance(
    chat_client, settings, provider, payload, monkeypatch
):
    settings.daily_request_limit = 1

    def failed_read(*args, **kwargs):
        raise AppError(503, ErrorCode.DB_ERROR, "테스트 DB 조회 실패")

    with monkeypatch.context() as patch:
        patch.setattr(repository, "get_recent_completed_turns", failed_read)
        _error(chat_client.post("/api/chat", json=payload), 503, "DB_ERROR")
    assert provider.calls == 0

    fresh = dict(payload, client_request_id=str(uuid4()))
    assert chat_client.post("/api/chat", json=fresh).status_code == 200
    assert provider.calls == 1


def test_pending_insert_failure_does_not_consume_allowance(
    chat_client, settings, provider, payload, app
):
    settings.daily_request_limit = 1

    def reject_insert(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO chat_turns"):
            raise OperationalError("INSERT", {}, Exception("test-only write failure"))

    engine = app.state.engine
    event.listen(engine, "before_cursor_execute", reject_insert)
    try:
        _error(chat_client.post("/api/chat", json=payload), 503, "DB_ERROR")
    finally:
        event.remove(engine, "before_cursor_execute", reject_insert)
    assert provider.calls == 0
    assert _turns(app) == []

    assert chat_client.post("/api/chat", json=payload).status_code == 200
    assert provider.calls == 1


def test_result_save_failure_keeps_the_consumed_allowance(chat_client, provider, payload, app):
    def reject_completed_update(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE chat_turns") and "completed" in parameters:
            raise OperationalError("UPDATE", {}, Exception("test-only write failure"))

    engine = app.state.engine
    event.listen(engine, "before_cursor_execute", reject_completed_update)
    try:
        _error(chat_client.post("/api/chat", json=payload), 503, "DB_ERROR")
    finally:
        event.remove(engine, "before_cursor_execute", reject_completed_update)
    assert provider.calls == 1
    assert _turns(app)[0].status == "pending"
    _error(chat_client.post("/api/chat", json=payload), 409, "CHAT_BUSY")

    fresh = dict(payload, client_request_id=str(uuid4()))
    _error(chat_client.post("/api/chat", json=fresh), 429, "RATE_LIMITED")
    assert provider.calls == 1


def test_active_user_busy_rejection_does_not_consume_allowance(
    chat_client, settings, provider, payload, app
):
    settings.user_requests_per_minute = settings.daily_request_limit = 2
    limiter = rate_limit.get_rate_limiter(Request({"type": "http", "app": app}), settings)

    async def scenario():
        started, release = asyncio.Event(), asyncio.Event()

        class BlockingProvider(FakeAIProvider):
            async def generate_reply(self, *args, **kwargs):
                started.set()
                await release.wait()
                return await super().generate_reply(*args, **kwargs)

        async def ask(session, request, fake):
            return await answer_question(
                request,
                user_id=1,
                request_id="busy-quota-request",
                session=session,
                settings=settings,
                provider=fake,
                rate_limiter=limiter,
            )

        with Session(app.state.engine) as first, Session(app.state.engine) as second:
            task = asyncio.create_task(ask(first, ChatRequest(**payload), BlockingProvider()))
            try:
                await asyncio.wait_for(started.wait(), timeout=2)
                other = ChatRequest(**dict(payload, client_request_id=str(uuid4())))
                with pytest.raises(AppError) as caught:
                    await ask(second, other, FakeAIProvider())
                assert (caught.value.status_code, caught.value.code) == (409, ErrorCode.CHAT_BUSY)
            finally:
                release.set()
                await task

    asyncio.run(scenario())
    fresh = dict(payload, client_request_id=str(uuid4()))
    assert chat_client.post("/api/chat", json=fresh).status_code == 200
    assert provider.calls == 1
    assert [turn.status for turn in _turns(app)] == ["completed", "completed"]


def test_user_minute_limit_does_not_block_another_user(chat_client, provider, payload, app):
    assert chat_client.post("/api/chat", json=payload).status_code == 200
    _error(
        chat_client.post("/api/chat", json=dict(payload, client_request_id=str(uuid4()))),
        429,
        "RATE_LIMITED",
    )
    other_conversation = _add_user_conversation(app, 2)
    _act_as(app, 2)

    assert chat_client.post("/api/chat", json=_payload(other_conversation)).status_code == 200
    assert provider.calls == 2


def test_daily_allowance_is_shared_and_resets_on_utc_date_change(
    chat_client, settings, provider, payload, app, clock
):
    settings.user_requests_per_minute = 10
    settings.daily_request_limit = 2
    assert chat_client.post("/api/chat", json=payload).status_code == 200
    second_conversation = _add_user_conversation(app, 2)
    third_conversation = _add_user_conversation(app, 3)
    _act_as(app, 2)
    assert chat_client.post("/api/chat", json=_payload(second_conversation)).status_code == 200
    _act_as(app, 3)
    _error(chat_client.post("/api/chat", json=_payload(third_conversation)), 429, "RATE_LIMITED")
    clock.seconds += 60
    _error(chat_client.post("/api/chat", json=_payload(third_conversation)), 429, "RATE_LIMITED")

    clock.day += timedelta(days=1)
    assert chat_client.post("/api/chat", json=_payload(third_conversation)).status_code == 200
    assert provider.calls == 3


def test_separate_app_has_its_own_counter(chat_client, provider, payload, settings, tmp_path):
    assert chat_client.post("/api/chat", json=payload).status_code == 200
    second_settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite:///{tmp_path / 'second-app.db'}",
        ai_provider="fake",
        user_requests_per_minute=1,
        daily_request_limit=1,
    )
    second_app = create_app(second_settings)
    second_app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=1, email="second@example.com"
    )
    second_app.dependency_overrides[require_csrf] = lambda: None
    second_app.dependency_overrides[get_ai_provider] = lambda: provider
    with TestClient(second_app, raise_server_exceptions=False) as second_client:
        conversation_id = _add_user_conversation(second_app, 1)
        assert second_client.post("/api/chat", json=_payload(conversation_id)).status_code == 200
    assert provider.calls == 2


def test_cancelled_ai_still_consumes_allowance(chat_client, provider, payload, settings, app):
    limiter = rate_limit.get_rate_limiter(Request({"type": "http", "app": app}), settings)

    async def scenario():
        started = asyncio.Event()

        class BlockingProvider(FakeAIProvider):
            async def generate_reply(self, *args, **kwargs):
                started.set()
                await asyncio.Event().wait()

        with Session(app.state.engine) as session:
            task = asyncio.create_task(
                answer_question(
                    ChatRequest(**payload),
                    user_id=1,
                    request_id="cancelled-quota-request",
                    session=session,
                    settings=settings,
                    provider=BlockingProvider(),
                    rate_limiter=limiter,
                )
            )
            await asyncio.wait_for(started.wait(), timeout=2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(scenario())
    fresh = dict(payload, client_request_id=str(uuid4()))
    _error(chat_client.post("/api/chat", json=fresh), 429, "RATE_LIMITED")
    assert provider.calls == 0
    assert [turn.error_code for turn in _turns(app)] == ["AI_UNAVAILABLE", "RATE_LIMITED"]

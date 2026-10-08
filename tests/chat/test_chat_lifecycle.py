"""실제 임시 DB로 동시 요청·취소·저장 실패의 경계를 확인한다."""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, select

from app.chat.fake_provider import FakeAIProvider
from app.chat.schemas import ChatRequest
from app.chat.service import answer_question
from app.conversations import repository
from app.core.errors import AppError, ErrorCode
from app.db.models import ChatTurn, User


@pytest.fixture
def data(client, app):
    engine = app.state.engine
    with Session(engine) as session:
        users = [User(email=f"life-{i}@example.com", password_hash="test-only") for i in range(2)]
        session.add_all(users)
        session.commit()
        ids = [user.id for user in users]
        conversations = [
            repository.create_conversation(session, user_id, "테스트") for user_id in ids
        ]
        conversation_ids = [conversation.id for conversation in conversations]
    return engine, ids, conversation_ids


def _request(conversation_id):
    return ChatRequest(
        conversation_id=conversation_id,
        question="테스트 질문",
        level="easy",
        client_request_id=uuid4(),
    )


async def _ask(session, settings, request, user_id, provider):
    return await answer_question(
        request,
        user_id=user_id,
        request_id="lifecycle-test",
        session=session,
        settings=settings,
        provider=provider,
    )


def _stored(engine):
    with Session(engine) as session:
        return list(session.exec(select(ChatTurn).order_by(ChatTurn.id)).all())


def test_concurrent_user_is_busy_but_cached_answer_and_other_user_work(data, settings):
    engine, users, conversations = data

    async def scenario():
        started, release = asyncio.Event(), asyncio.Event()
        cached_request = _request(conversations[0])
        with Session(engine) as session:
            cached = await _ask(session, settings, cached_request, users[0], FakeAIProvider())

        with Session(engine) as first, Session(engine) as second:

            class BlockingProvider(FakeAIProvider):
                async def generate_reply(self, *args, **kwargs):
                    # pending은 다른 연결에서 보이고, AI를 기다릴 세션의 트랜잭션은 끝났다.
                    assert not first.in_transaction()
                    assert _stored(engine)[-1].status == "pending"
                    started.set()
                    await release.wait()
                    return await super().generate_reply(*args, **kwargs)

            task = asyncio.create_task(
                _ask(first, settings, _request(conversations[0]), users[0], BlockingProvider())
            )
            try:
                await asyncio.wait_for(started.wait(), timeout=2)
                with pytest.raises(AppError) as error:
                    await _ask(
                        second, settings, _request(conversations[0]), users[0], FakeAIProvider()
                    )
                assert (error.value.status_code, error.value.code) == (409, ErrorCode.CHAT_BUSY)
                replay = await _ask(second, settings, cached_request, users[0], FakeAIProvider())
                assert replay == cached
                other = await _ask(
                    second, settings, _request(conversations[1]), users[1], FakeAIProvider()
                )
                assert other.status == "completed"
            finally:
                release.set()
                await task

        with Session(engine) as session:
            assert (
                await _ask(
                    session, settings, _request(conversations[0]), users[0], FakeAIProvider()
                )
            ).status == "completed"

    asyncio.run(scenario())
    assert len(_stored(engine)) == 4  # 거절된 동시 질문은 저장하지 않았다.


def test_service_enforces_deadline_even_when_provider_does_not(data, settings):
    engine, users, conversations = data
    settings.ai_timeout_seconds = 0.02
    cancelled = []

    class SlowProvider(FakeAIProvider):
        async def generate_reply(self, *args, **kwargs):
            try:
                await asyncio.sleep(10)
            finally:
                cancelled.append(True)

    with Session(engine) as session, pytest.raises(AppError) as error:
        asyncio.run(_ask(session, settings, _request(conversations[0]), users[0], SlowProvider()))
    assert (error.value.status_code, error.value.code) == (504, ErrorCode.AI_TIMEOUT)
    assert cancelled == [True]
    turn = _stored(engine)[0]
    assert (turn.status, turn.error_code, turn.answer) == ("failed", "AI_TIMEOUT", None)


def test_cancelled_request_is_saved_and_releases_user_guard(data, settings):
    engine, users, conversations = data

    async def scenario():
        started = asyncio.Event()

        class BlockingProvider(FakeAIProvider):
            async def generate_reply(self, *args, **kwargs):
                started.set()
                await asyncio.Event().wait()

        with Session(engine) as session:
            task = asyncio.create_task(
                _ask(session, settings, _request(conversations[0]), users[0], BlockingProvider())
            )
            await asyncio.wait_for(started.wait(), timeout=2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert _stored(engine)[0].status == "failed"
        with Session(engine) as session:
            result = await _ask(
                session, settings, _request(conversations[0]), users[0], FakeAIProvider()
            )
            assert result.status == "completed"

    asyncio.run(scenario())


@pytest.mark.parametrize("mode, rejected_status", [("success", "completed"), ("timeout", "failed")])
def test_result_save_failure_returns_db_error_and_keeps_pending(
    data, settings, mode, rejected_status
):
    engine, users, conversations = data

    def reject_update(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE chat_turns") and rejected_status in parameters:
            raise OperationalError("UPDATE", {}, Exception("test-only write failure"))

    event.listen(engine, "before_cursor_execute", reject_update)
    try:
        with Session(engine) as session, pytest.raises(AppError) as error:
            asyncio.run(
                _ask(
                    session,
                    settings,
                    _request(conversations[0]),
                    users[0],
                    FakeAIProvider(mode=mode),
                )
            )
        assert (error.value.status_code, error.value.code) == (503, ErrorCode.DB_ERROR)
    finally:
        event.remove(engine, "before_cursor_execute", reject_update)
    turn = _stored(engine)[0]
    assert (turn.status, turn.answer, turn.error_code) == ("pending", None, None)


def test_context_read_failure_is_saved_without_ai_and_replays_db_error(data, settings, monkeypatch):
    engine, users, conversations = data
    calls = []

    class ObservedProvider(FakeAIProvider):
        async def generate_reply(self, *args, **kwargs):
            calls.append(True)
            return await super().generate_reply(*args, **kwargs)

    def unavailable(*args, **kwargs):
        raise AppError(503, ErrorCode.DB_ERROR, "테스트 DB 조회 실패")

    monkeypatch.setattr(repository, "get_recent_completed_turns", unavailable)
    request = _request(conversations[0])
    for _ in range(2):
        with Session(engine) as session, pytest.raises(AppError) as error:
            asyncio.run(_ask(session, settings, request, users[0], ObservedProvider()))
        assert (error.value.status_code, error.value.code) == (503, ErrorCode.DB_ERROR)
    assert calls == []
    turn = _stored(engine)[0]
    assert (turn.status, turn.error_code, turn.answer) == ("failed", "DB_ERROR", None)


def test_unexpected_provider_error_is_sanitized_saved_and_releases_guard(data, settings):
    engine, users, conversations = data

    class BrokenProvider(FakeAIProvider):
        async def generate_reply(self, *args, **kwargs):
            raise RuntimeError("private-provider-detail")

    with Session(engine) as session, pytest.raises(AppError) as error:
        asyncio.run(_ask(session, settings, _request(conversations[0]), users[0], BrokenProvider()))
    assert (error.value.status_code, error.value.code) == (500, ErrorCode.INTERNAL_ERROR)
    assert "private-provider-detail" not in error.value.message
    assert _stored(engine)[0].error_code == "INTERNAL_ERROR"
    with Session(engine) as session:
        result = asyncio.run(
            _ask(session, settings, _request(conversations[0]), users[0], FakeAIProvider())
        )
        assert result.status == "completed"

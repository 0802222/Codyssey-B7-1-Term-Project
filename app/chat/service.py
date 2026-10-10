"""소유권 확인 → pending 저장 → 문맥 → AI → 결과 저장. (EE-13)"""

import asyncio
import logging
from contextlib import contextmanager
from threading import Lock
from uuid import UUID

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import Session, select

from app.chat.context import HistoryTurn, build_messages
from app.chat.prompts import build_system_prompt
from app.chat.provider import (
    AIProvider,
    AIProviderError,
    AITimeoutError,
    AIUnavailableError,
    AIUpstreamError,
)
from app.chat.rate_limit import ChatRateLimiter
from app.chat.schemas import ChatRequest, ChatResponse
from app.conversations import repository
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.logging import log_event
from app.db.models import ChatTurn

# 첫 버전은 단일 서버 프로세스다. Lock은 집합을 바꿀 때만 잡고 AI 대기 중에는 놓는다.
# 엔진도 키에 넣어서 서로 다른 앱·테스트 DB의 사용자 번호가 충돌하지 않게 한다.
_active_users: set[tuple[object, int]] = set()
_active_users_lock = Lock()

_FAILURES = {
    ErrorCode.RATE_LIMITED: (429, "질문 요청 한도를 초과했어요. 잠시 후 다시 시도해 주세요."),
    ErrorCode.AI_TIMEOUT: (504, "응답이 지연되고 있어요. 잠시 후 다시 시도해 주세요."),
    ErrorCode.AI_UPSTREAM_ERROR: (502, "AI 응답을 받지 못했어요. 잠시 후 다시 시도해 주세요."),
    ErrorCode.AI_UNAVAILABLE: (503, "지금은 AI를 이용할 수 없어요. 잠시 후 다시 시도해 주세요."),
    ErrorCode.DB_ERROR: (503, "데이터베이스 오류가 발생했어요. 잠시 후 다시 시도해 주세요."),
    ErrorCode.INTERNAL_ERROR: (500, "일시적인 오류가 발생했어요. 잠시 후 다시 시도해 주세요."),
}


def _failure(code: str) -> AppError:
    # DB에 저장한 코드만으로 복원한다. 외부 API의 원문 오류는 저장하거나 반환하지 않는다.
    safe_code = ErrorCode(code) if code in _FAILURES else ErrorCode.INTERNAL_ERROR
    status, message = _FAILURES[safe_code]
    return AppError(status, safe_code, message)


def _busy() -> AppError:
    return AppError(409, ErrorCode.CHAT_BUSY, "이전 질문에 답하는 중이에요. 잠시 기다려 주세요.")


@contextmanager
def _one_request_at_a_time(session: Session, user_id: int):
    key = (session.get_bind(), user_id)
    with _active_users_lock:
        if key in _active_users:
            raise _busy()
        _active_users.add(key)
    try:
        yield
    finally:
        with _active_users_lock:
            _active_users.discard(key)


def _find_previous_turn(session: Session, user_id: int, client_request_id: UUID) -> ChatTurn | None:
    # EE-11의 저장·문맥 조회는 그대로 사용하고, 중복 키 조회만 이 서비스에서 보충한다.
    try:
        return session.exec(
            select(ChatTurn).where(
                ChatTurn.user_id == user_id,
                ChatTurn.client_request_id == client_request_id,
            )
        ).first()
    except SQLAlchemyError:
        session.rollback()
        raise AppError(
            503, ErrorCode.DB_ERROR, "데이터베이스 오류가 발생했어요. 잠시 후 다시 시도해 주세요."
        ) from None


def _response(turn: ChatTurn) -> ChatResponse:
    # ORM을 응답 밖으로 넘기지 않는다. rollback/commit 뒤의 자동 DB 재조회를 피한다.
    return ChatResponse(
        request_id=turn.request_id,
        turn_id=turn.id,
        conversation_id=turn.conversation_id,
        level=turn.level,
        question=turn.question,
        answer=turn.answer,
        status=turn.status,
        created_at=turn.created_at,
    )


def _replay(turn: ChatTurn, request: ChatRequest) -> ChatResponse:
    if (
        turn.conversation_id != request.conversation_id
        or turn.question != request.question
        or turn.level != request.level
    ):
        raise AppError(
            409, ErrorCode.REQUEST_CONFLICT, "같은 요청 번호로 다른 질문을 보낼 수 없어요."
        )
    if turn.status == "completed":
        return _response(turn)
    if turn.status == "pending":
        raise _busy()
    if turn.status == "interrupted":
        raise _failure(ErrorCode.AI_UNAVAILABLE)
    raise _failure(turn.error_code or ErrorCode.INTERNAL_ERROR)


def _history(session: Session, request: ChatRequest, user_id: int, limit: int) -> list[HistoryTurn]:
    turns = repository.get_recent_completed_turns(session, request.conversation_id, user_id, limit)
    return [
        HistoryTurn(
            id=turn.id,
            user_id=turn.user_id,
            conversation_id=turn.conversation_id,
            question=turn.question,
            answer=turn.answer,
            status=turn.status,
            created_at=turn.created_at,
        )
        for turn in turns
    ]


async def answer_question(
    request: ChatRequest,
    *,
    user_id: int,
    request_id: str,
    session: Session,
    settings: Settings,
    provider: AIProvider,
    rate_limiter: ChatRateLimiter,
) -> ChatResponse:
    conversation = repository.get_conversation_for_user(session, request.conversation_id, user_id)
    if conversation is None:
        raise AppError(404, ErrorCode.CONVERSATION_NOT_FOUND, "대화를 찾을 수 없어요.")

    # 완료된 요청의 재전송은 다른 질문이 진행 중이어도 저장된 결과를 돌려준다.
    previous = _find_previous_turn(session, user_id, request.client_request_id)
    if previous is not None:
        return _replay(previous, request)

    with _one_request_at_a_time(session, user_id):
        # 첫 조회와 처리 중 표시 사이에 앞선 요청이 끝났을 수도 있으므로 다시 확인한다.
        previous = _find_previous_turn(session, user_id, request.client_request_id)
        if previous is not None:
            return _replay(previous, request)
        try:
            pending = repository.create_pending_turn(
                session,
                request.conversation_id,
                user_id,
                request.client_request_id,
                request_id,
                request.level,
                request.question,
            )
        except AppError as exc:
            # 다른 프로세스가 같은 키를 먼저 저장했다면 DB 유일 제약의 결과를 재확인한다.
            if isinstance(exc.__cause__, IntegrityError):
                previous = _find_previous_turn(session, user_id, request.client_request_id)
                if previous is not None:
                    return _replay(previous, request)
            raise
        turn_id = pending.id
        try:
            history = _history(session, request, user_id, settings.context_turns)
        except AppError as exc:
            # pending 저장 뒤 문맥 조회가 실패하면 AI는 부르지 않고 실패를 기록한다.
            repository.fail_turn(session, turn_id, user_id, exc.code)
            raise
        messages = build_messages(
            history,
            user_id=user_id,
            conversation_id=request.conversation_id,
            question=request.question,
            max_turns=settings.context_turns,
            max_chars=settings.context_max_chars,
        )
        system = build_system_prompt(request.level)
        # pending은 이미 commit됐다. refresh·조회가 시작한 트랜잭션만 끝내고 AI를 기다린다.
        session.rollback()

        try:
            # 실제 AI 호출 직전에만 센다. 중복 응답·준비 단계 DB 실패는 횟수를 쓰지 않는다.
            rate_limiter.check_and_count(user_id)
        except AppError as exc:
            repository.fail_turn(session, turn_id, user_id, exc.code)
            log_event("chat_rate_limited", user_id=user_id, turn_id=turn_id)
            raise

        log_event("ai_call_start", user_id=user_id, turn_id=turn_id)
        try:
            async with asyncio.timeout(settings.ai_timeout_seconds):
                result = await provider.generate_reply(
                    messages,
                    system=system,
                    timeout_seconds=settings.ai_timeout_seconds,
                    max_output_tokens=settings.ai_max_output_tokens,
                )
            if not result.text.strip():
                raise AIUpstreamError()
        except (AIProviderError, TimeoutError) as exc:
            if isinstance(exc, (AITimeoutError, TimeoutError)):
                code = ErrorCode.AI_TIMEOUT
            elif isinstance(exc, AIUnavailableError):
                code = ErrorCode.AI_UNAVAILABLE
            else:
                code = ErrorCode.AI_UPSTREAM_ERROR
            log_event(
                "ai_call_failed",
                level=logging.WARNING,
                user_id=user_id,
                turn_id=turn_id,
                error_code=code,
            )
            repository.fail_turn(session, turn_id, user_id, code)
            raise _failure(code) from None
        except asyncio.CancelledError:
            # 연결 종료 등으로 취소됐어도, 저장된 pending을 다시 AI에 자동 전송하지 않는다.
            log_event(
                "ai_call_failed",
                level=logging.WARNING,
                user_id=user_id,
                turn_id=turn_id,
                error_code=ErrorCode.AI_UNAVAILABLE,
            )
            repository.fail_turn(session, turn_id, user_id, ErrorCode.AI_UNAVAILABLE)
            raise
        except Exception as exc:
            log_event(
                "ai_call_failed",
                level=logging.ERROR,
                user_id=user_id,
                turn_id=turn_id,
                error_code=ErrorCode.INTERNAL_ERROR,
                error_type=type(exc).__name__,
            )
            repository.fail_turn(session, turn_id, user_id, ErrorCode.INTERNAL_ERROR)
            raise _failure(ErrorCode.INTERNAL_ERROR) from None

        log_event("ai_call_success", user_id=user_id, turn_id=turn_id)
        completed = repository.complete_turn(session, turn_id, user_id, result.text)
        return _response(completed)

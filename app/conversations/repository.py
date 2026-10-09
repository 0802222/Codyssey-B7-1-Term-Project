"""대화 저장소. (A 담당, EE-11)"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select

from app.core.errors import AppError, ErrorCode
from app.core.logging import log_event
from app.db.models import ChatTurn, Conversation

_DB_ERROR_MESSAGE = "데이터베이스 오류가 발생했어요. 잠시 후 다시 시도해 주세요."
_DEFAULT_CONVERSATION_TITLE = "새 대화"
_CONVERSATION_TITLE_MAX_LENGTH = 30


def _title_from_question(question: str) -> str:
    title = (
        question.replace("\r\n", " ")
        .replace("\r", " ")
        .replace("\n", " ")
        .strip()
    )
    if len(title) > _CONVERSATION_TITLE_MAX_LENGTH:
        return f"{title[:_CONVERSATION_TITLE_MAX_LENGTH]}…"
    return title


def _db_error() -> AppError:
    return AppError(503, ErrorCode.DB_ERROR, _DB_ERROR_MESSAGE)


def create_conversation(
    session: Session,
    user_id: int,
    title: str,
) -> Conversation:
    conversation = Conversation(
        user_id=user_id,
        title=title,
    )

    try:
        session.add(conversation)
        session.commit()
        session.refresh(conversation)

        log_event(
            "db_save_success",
            user_id=user_id,
            entity="conversation",
        )
    except SQLAlchemyError as exc:
        session.rollback()

        log_event(
            "db_save_failed",
            level=logging.ERROR,
            user_id=user_id,
            entity="conversation",
            error_type=type(exc).__name__,
        )

        raise _db_error() from exc
    
    return conversation


def get_conversation_for_user(
    session: Session,
    conversation_id: UUID,
    user_id: int,
) -> Conversation | None:
    try:
        return session.exec(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        ).first()
    except SQLAlchemyError:
        session.rollback()

        raise _db_error() from None


def create_pending_turn(
    session: Session,
    conversation_id: UUID,
    user_id: int,
    client_request_id: UUID,
    request_id: str,
    level: str,
    question: str,
) -> ChatTurn:
    conversation = get_conversation_for_user(
        session,
        conversation_id,
        user_id,
    )

    if conversation is None:
        raise AppError(
            404,
            ErrorCode.CONVERSATION_NOT_FOUND,
            "대화를 찾을 수 없어요.",
        )

    turn = ChatTurn(
        conversation_id=conversation_id,
        user_id=user_id,
        client_request_id=client_request_id,
        request_id=request_id,
        level=level,
        question=question,
        status="pending",
    )
    try:
        has_existing_turn = session.exec(
            select(ChatTurn.id)
            .where(
                ChatTurn.conversation_id == conversation_id,
                ChatTurn.user_id == user_id,
            )
            .limit(1)
        ).first()
        if (
            conversation.title == _DEFAULT_CONVERSATION_TITLE
            and has_existing_turn is None
        ):
            title = _title_from_question(question)
            if title:
                conversation.title = title
        conversation.updated_at = datetime.now(UTC)

        session.add(turn)
        session.add(conversation)
        session.commit()
        session.refresh(turn)

        log_event(
            "db_save_success",
            user_id=user_id,
            entity="chat_turn",
            status="pending",
        )
    except SQLAlchemyError as exc:
        session.rollback()

        log_event(
            "db_save_failed",
            level=logging.ERROR,
            user_id=user_id,
            entity="chat_turn",
            status="pending",
            error_type=type(exc).__name__,
        )

        raise _db_error() from exc

    return turn


def complete_turn(
    session: Session,
    turn_id: int,
    user_id: int,
    answer: str,
) -> ChatTurn:
    try:
        turn = session.exec(
            select(ChatTurn).where(
                ChatTurn.id == turn_id,
                ChatTurn.user_id == user_id,
            )
        ).first()

        if turn is None:
            raise AppError(
                404,
                ErrorCode.CONVERSATION_NOT_FOUND,
                "대화를 찾을 수 없어요.",
            )

        turn.answer = answer
        turn.status = "completed"
        turn.completed_at = datetime.now(UTC)

        session.add(turn)
        session.commit()
        session.refresh(turn)

        log_event(
            "db_save_success",
            user_id=user_id,
            entity="chat_turn",
            status="completed",
        )
    except AppError:
        session.rollback()
        raise
    except SQLAlchemyError as exc:
        session.rollback()

        log_event(
            "db_save_failed",
            level=logging.ERROR,
            user_id=user_id,
            entity="chat_turn",
            status="completed",
            error_type=type(exc).__name__,
        )

        raise _db_error() from exc

    return turn


def fail_turn(
    session: Session,
    turn_id: int,
    user_id: int,
    error_code: str,
) -> ChatTurn:
    try:
        turn = session.exec(
            select(ChatTurn).where(
                ChatTurn.id == turn_id,
                ChatTurn.user_id == user_id,
            )
        ).first()

        if turn is None:
            raise AppError(
                404,
                ErrorCode.CONVERSATION_NOT_FOUND,
                "대화를 찾을 수 없어요.",
            )

        turn.status = "failed"
        turn.error_code = error_code
        turn.completed_at = datetime.now(UTC)

        session.add(turn)
        session.commit()
        session.refresh(turn)

        log_event(
            "db_save_success",
            user_id=user_id,
            entity="chat_turn",
            status="failed",
        )
    except AppError:
        session.rollback()
        raise
    except SQLAlchemyError as exc:
        session.rollback()

        log_event(
            "db_save_failed",
            level=logging.ERROR,
            user_id=user_id,
            entity="chat_turn",
            status="failed",
            error_type=type(exc).__name__,
        )

        raise _db_error() from exc

    return turn


def get_recent_completed_turns(
    session: Session,
    conversation_id: UUID,
    user_id: int,
    limit: int,
) -> list[ChatTurn]:
    conversation = get_conversation_for_user(
        session,
        conversation_id,
        user_id,
    )

    if conversation is None:
        raise AppError(
            404,
            ErrorCode.CONVERSATION_NOT_FOUND,
            "대화를 찾을 수 없어요.",
        )

    try:
        return list(
            session.exec(
                select(ChatTurn)
                .where(
                    ChatTurn.conversation_id == conversation_id,
                    ChatTurn.user_id == user_id,
                    ChatTurn.status == "completed",
                )
                .order_by(
                    ChatTurn.created_at.desc(),
                    ChatTurn.id.desc(),
                )
                .limit(limit)
            ).all()
        )
    except SQLAlchemyError:
        session.rollback()

        raise _db_error() from None


def list_conversations_for_user(
    session: Session,
    user_id: int,
    limit: int,
    offset: int,
) -> tuple[list[Conversation], bool]:
    try:
        conversations = list(
            session.exec(
                select(Conversation)
                .where(Conversation.user_id == user_id)
                .order_by(
                    Conversation.updated_at.desc(),
                    Conversation.id.desc(),
                )
                .offset(offset)
                .limit(limit + 1)
            ).all()
        )

        has_more = len(conversations) > limit

        return conversations[:limit], has_more

    except SQLAlchemyError:
        session.rollback()

        raise _db_error() from None


def get_conversation_turns_for_user(
    session: Session,
    conversation_id: UUID,
    user_id: int,
) -> tuple[Conversation, list[ChatTurn]]:
    conversation = get_conversation_for_user(
        session,
        conversation_id,
        user_id,
    )

    if conversation is None:
        raise AppError(
            404,
            ErrorCode.CONVERSATION_NOT_FOUND,
            "대화를 찾을 수 없어요.",
        )

    try:
        turns = list(
            session.exec(
                select(ChatTurn)
                .where(
                    ChatTurn.conversation_id == conversation_id,
                    ChatTurn.user_id == user_id,
                )
                .order_by(
                    ChatTurn.created_at.asc(),
                    ChatTurn.id.asc(),
                )
            ).all()
        )

        return conversation, turns

    except SQLAlchemyError:
        session.rollback()

        raise _db_error() from None


def list_chats_for_user(
    session: Session,
    user_id: int,
    limit: int,
    offset: int,
) -> tuple[list[ChatTurn], bool]:
    try:
        turns = list(
            session.exec(
                select(ChatTurn)
                .where(ChatTurn.user_id == user_id)
                .order_by(
                    ChatTurn.created_at.desc(),
                    ChatTurn.id.desc(),
                )
                .offset(offset)
                .limit(limit + 1)
            ).all()
        )

        has_more = len(turns) > limit

        return turns[:limit], has_more

    except SQLAlchemyError:
        session.rollback()

        raise _db_error() from None

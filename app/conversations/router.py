"""대화 생성·내 기록 조회 API. (A 담당, EE-11)"""

from uuid import UUID

from fastapi import APIRouter, Query

from app.auth.dependencies import CsrfDep, CurrentUserDep
from app.conversations.repository import (
    DEFAULT_CONVERSATION_TITLE,
    get_conversation_turns_for_user,
    list_chats_for_user,
    list_conversations_for_user,
)
from app.conversations.repository import (
    create_conversation as create_conversation_record,
)
from app.db.session import SessionDep

router = APIRouter(prefix="/api", tags=["conversations"])

# SQLite의 정수 범위를 넘는 offset으로 쿼리 실행이 실패하지 않도록 제한한다.
MAX_OFFSET = 1_000_000


@router.post("/conversations", status_code=201)
def create_conversation(
    user: CurrentUserDep,
    _csrf: CsrfDep,
    session: SessionDep,
):
    conversation = create_conversation_record(
        session=session,
        user_id=user.id,
        title=DEFAULT_CONVERSATION_TITLE,
    )

    return {
        "id": conversation.id,
        "title": conversation.title,
        "created_at": conversation.created_at,
    }


@router.get("/me/conversations")
def list_my_conversations(
    user: CurrentUserDep,
    session: SessionDep,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=MAX_OFFSET),
):
    conversations, has_more = list_conversations_for_user(
        session=session,
        user_id=user.id,
        limit=limit,
        offset=offset,
    )

    return {
        "items": [
            {
                "id": conversation.id,
                "title": conversation.title,
                "created_at": conversation.created_at,
                "updated_at": conversation.updated_at,
            }
            for conversation in conversations
        ],
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
    }


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: UUID,
    user: CurrentUserDep,
    session: SessionDep,
):
    conversation, turns = get_conversation_turns_for_user(
        session=session,
        conversation_id=conversation_id,
        user_id=user.id,
    )

    return {
        "conversation": {
            "id": conversation.id,
            "title": conversation.title,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
        },
        "turns": [
            {
                "id": turn.id,
                "conversation_id": turn.conversation_id,
                "level": turn.level,
                "question": turn.question,
                "answer": turn.answer,
                "status": turn.status,
                "error_code": turn.error_code,
                "created_at": turn.created_at,
            }
            for turn in turns
        ],
    }


@router.get("/me/chats")
def list_my_chats(
    user: CurrentUserDep,
    session: SessionDep,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=MAX_OFFSET),
):
    chats, has_more = list_chats_for_user(
        session=session,
        user_id=user.id,
        limit=limit,
        offset=offset,
    )

    return {
        "items": [
            {
                "id": turn.id,
                "conversation_id": turn.conversation_id,
                "level": turn.level,
                "question": turn.question,
                "answer": turn.answer,
                "status": turn.status,
                "error_code": turn.error_code,
                "created_at": turn.created_at,
            }
            for turn in chats
        ],
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
    }

"""대화 생성·내 기록 조회 API. (A 담당, EE-11)"""

from uuid import UUID

from fastapi import APIRouter

from app.core.errors import not_implemented

router = APIRouter(prefix="/api", tags=["conversations"])


@router.post("/conversations", status_code=201)
def create_conversation():
    raise not_implemented("EE-11")


@router.get("/me/conversations")
def list_my_conversations():
    raise not_implemented("EE-11")


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: UUID):
    raise not_implemented("EE-11")


@router.get("/me/chats")
def list_my_chats():
    raise not_implemented("EE-11")

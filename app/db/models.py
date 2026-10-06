"""DB 테이블 정의. (A 담당, EE-03)

docs/spec/db.md 의 users / auth_sessions / conversations / chat_turns 를 SQLModel 로 정의한다.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Index, UniqueConstraint
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(UTC)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(unique=True)
    password_hash: str
    created_at: datetime = Field(default_factory=utc_now)


class AuthSession(SQLModel, table=True):
    __tablename__ = "auth_sessions"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    token_hash: str = Field(unique=True)
    csrf_token: str
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime


class Conversation(SQLModel, table=True):
    __tablename__ = "conversations"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    title: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ChatTurn(SQLModel, table=True):
    __tablename__ = "chat_turns"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "client_request_id",
            name="uq_chat_turns_user_client_request",
        ),
        Index(
            "ix_chat_turns_conversation_created_id",
            "conversation_id",
            "created_at",
            "id",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    conversation_id: UUID = Field(foreign_key="conversations.id")
    user_id: int = Field(foreign_key="users.id")
    client_request_id: UUID
    request_id: str
    level: str
    question: str
    answer: str | None = None
    status: str
    error_code: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    
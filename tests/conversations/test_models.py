from uuid import uuid4

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, create_engine

from app.db.models import ChatTurn, Conversation, User
from app.db.session import init_db


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    init_db(engine)
    return engine


def test_init_db_creates_all_tables(engine):
    tables = set(inspect(engine).get_table_names())

    assert tables == {
        "users",
        "auth_sessions",
        "conversations",
        "chat_turns",
    }


def test_user_email_must_be_unique(engine):
    with Session(engine) as session:
        session.add(
            User(
                email="test@example.com",
                password_hash="hash1",
            )
        )
        session.commit()

        session.add(
            User(
                email="test@example.com",
                password_hash="hash2",
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()


def test_chat_turn_client_request_id_must_be_unique_per_user(engine):
    client_request_id = uuid4()

    with Session(engine) as session:
        user = User(
            email="test@example.com",
            password_hash="hash",
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        conversation = Conversation(
            user_id=user.id,
            title="테스트 대화",
        )
        session.add(conversation)
        session.commit()
        session.refresh(conversation)

        session.add(
            ChatTurn(
                conversation_id=conversation.id,
                user_id=user.id,
                client_request_id=client_request_id,
                request_id="request-1",
                level="easy",
                question="첫 번째 질문",
                status="pending",
            )
        )
        session.commit()

        session.add(
            ChatTurn(
                conversation_id=conversation.id,
                user_id=user.id,
                client_request_id=client_request_id,
                request_id="request-2",
                level="easy",
                question="중복 질문",
                status="pending",
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()
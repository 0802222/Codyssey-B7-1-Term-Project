from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlmodel import Session, create_engine

from app.conversations.repository import (
    complete_turn,
    create_conversation,
    create_pending_turn,
    fail_turn,
    get_conversation_for_user,
    get_conversation_turns_for_user,
    get_recent_completed_turns,
    list_chats_for_user,
    list_conversations_for_user,
)
from app.core.errors import AppError, ErrorCode
from app.db.models import ChatTurn, Conversation, User
from app.db.session import init_db

BASE_TIME = datetime(2020, 1, 1, tzinfo=UTC)


def _stamp(session, conversation, minutes):
    """정렬 결과가 항상 같도록 시각을 직접 지정한다."""
    moment = BASE_TIME + timedelta(minutes=minutes)
    conversation.created_at = moment
    conversation.updated_at = moment
    session.add(conversation)
    session.commit()


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    init_db(engine)
    return engine


@pytest.fixture
def user(engine):
    with Session(engine) as session:
        user = User(
            email="test@example.com",
            password_hash="hash",
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        return user


@pytest.fixture
def other_user(engine):
    with Session(engine) as session:
        other = User(email="other@example.com", password_hash="hash")
        session.add(other)
        session.commit()
        session.refresh(other)
        return other


def test_create_conversation_belongs_to_user(engine, user):
    with Session(engine) as session:
        conversation = create_conversation(
            session=session,
            user_id=user.id,
            title="테스트 대화",
        )

        assert conversation.id is not None
        assert conversation.user_id == user.id
        assert conversation.title == "테스트 대화"


def test_get_conversation_for_user_only_returns_owned_conversation(
    engine,
    user,
    other_user,
):
    with Session(engine) as session:
        conversation = create_conversation(
            session=session,
            user_id=user.id,
            title="사용자 1의 대화",
        )

        found = get_conversation_for_user(
            session=session,
            conversation_id=conversation.id,
            user_id=user.id,
        )

        not_found = get_conversation_for_user(
            session=session,
            conversation_id=conversation.id,
            user_id=other_user.id,
        )

        assert found is not None
        assert found.id == conversation.id
        assert not_found is None


def test_create_pending_turn_requires_conversation_owner(
    engine,
    user,
    other_user,
):
    with Session(engine) as session:
        conversation = create_conversation(
            session=session,
            user_id=user.id,
            title="테스트 대화",
        )

        with pytest.raises(AppError) as exc_info:
            create_pending_turn(
                session=session,
                conversation_id=conversation.id,
                user_id=other_user.id,
                client_request_id=uuid4(),
                request_id="request-1",
                level="easy",
                question="질문",
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.code == ErrorCode.CONVERSATION_NOT_FOUND


def test_first_pending_turn_sets_default_conversation_title(engine, user):
    with Session(engine) as session:
        conversation = create_conversation(
            session=session,
            user_id=user.id,
            title="새 대화",
        )

        turn = create_pending_turn(
            session=session,
            conversation_id=conversation.id,
            user_id=user.id,
            client_request_id=uuid4(),
            request_id="request-1",
            level="easy",
            question="첫 질문입니다",
        )

        session.expire_all()
        saved_conversation = session.get(Conversation, conversation.id)
        saved_turn = session.get(ChatTurn, turn.id)

        assert saved_conversation.title == "첫 질문입니다"
        assert saved_turn.status == "pending"


def test_second_pending_turn_keeps_first_question_title(engine, user):
    with Session(engine) as session:
        conversation = create_conversation(
            session=session,
            user_id=user.id,
            title="새 대화",
        )

        create_pending_turn(
            session=session,
            conversation_id=conversation.id,
            user_id=user.id,
            client_request_id=uuid4(),
            request_id="request-1",
            level="easy",
            question="첫 질문",
        )
        create_pending_turn(
            session=session,
            conversation_id=conversation.id,
            user_id=user.id,
            client_request_id=uuid4(),
            request_id="request-2",
            level="easy",
            question="두 번째 질문으로 바꾸면 안 됨",
        )

        assert session.get(Conversation, conversation.id).title == "첫 질문"


def test_second_pending_turn_keeps_default_title_if_first_question_matches_it(
    engine,
    user,
):
    with Session(engine) as session:
        conversation = create_conversation(
            session=session,
            user_id=user.id,
            title="새 대화",
        )

        for request_id, question in (
            ("request-1", "새 대화"),
            ("request-2", "두 번째 질문"),
        ):
            create_pending_turn(
                session=session,
                conversation_id=conversation.id,
                user_id=user.id,
                client_request_id=uuid4(),
                request_id=request_id,
                level="easy",
                question=question,
            )

        assert session.get(Conversation, conversation.id).title == "새 대화"


def test_whitespace_in_first_question_is_collapsed_in_title(engine, user):
    with Session(engine) as session:
        conversation = create_conversation(
            session=session,
            user_id=user.id,
            title="새 대화",
        )

        create_pending_turn(
            session=session,
            conversation_id=conversation.id,
            user_id=user.id,
            client_request_id=uuid4(),
            request_id="request-1",
            level="easy",
            question="첫 줄\r\n둘째\t 줄   셋째 줄",
        )

        assert session.get(Conversation, conversation.id).title == "첫 줄 둘째 줄 셋째 줄"


def test_long_first_question_is_truncated_with_ellipsis(engine, user):
    question = "가" * 31

    with Session(engine) as session:
        conversation = create_conversation(
            session=session,
            user_id=user.id,
            title="새 대화",
        )

        create_pending_turn(
            session=session,
            conversation_id=conversation.id,
            user_id=user.id,
            client_request_id=uuid4(),
            request_id="request-1",
            level="easy",
            question=question,
        )

        title = session.get(Conversation, conversation.id).title

        assert title == f"{'가' * 30}…"
        assert len(title) == 31
        assert "\n" not in title


def test_complete_turn_changes_status_and_saves_answer(
    engine,
    user,
):
    with Session(engine) as session:
        conversation = create_conversation(
            session=session,
            user_id=user.id,
            title="테스트 대화",
        )

        turn = create_pending_turn(
            session=session,
            conversation_id=conversation.id,
            user_id=user.id,
            client_request_id=uuid4(),
            request_id="request-1",
            level="easy",
            question="질문",
        )

        completed = complete_turn(
            session=session,
            turn_id=turn.id,
            user_id=user.id,
            answer="답변",
        )

        assert completed.status == "completed"
        assert completed.answer == "답변"
        assert completed.completed_at is not None


def test_fail_turn_changes_status_and_saves_error_code(
    engine,
    user,
):
    with Session(engine) as session:
        conversation = create_conversation(
            session=session,
            user_id=user.id,
            title="테스트 대화",
        )

        turn = create_pending_turn(
            session=session,
            conversation_id=conversation.id,
            user_id=user.id,
            client_request_id=uuid4(),
            request_id="request-1",
            level="easy",
            question="질문",
        )

        failed = fail_turn(
            session=session,
            turn_id=turn.id,
            user_id=user.id,
            error_code="AI_TIMEOUT",
        )

        assert failed.status == "failed"
        assert failed.error_code == "AI_TIMEOUT"
        assert failed.completed_at is not None


def test_get_recent_completed_turns_returns_newest_first(
    engine,
    user,
):
    with Session(engine) as session:
        conversation = create_conversation(
            session=session,
            user_id=user.id,
            title="테스트 대화",
        )

        first = create_pending_turn(
            session=session,
            conversation_id=conversation.id,
            user_id=user.id,
            client_request_id=uuid4(),
            request_id="request-1",
            level="easy",
            question="첫 번째 질문",
        )
        complete_turn(
            session=session,
            turn_id=first.id,
            user_id=user.id,
            answer="첫 번째 답변",
        )

        second = create_pending_turn(
            session=session,
            conversation_id=conversation.id,
            user_id=user.id,
            client_request_id=uuid4(),
            request_id="request-2",
            level="easy",
            question="두 번째 질문",
        )
        complete_turn(
            session=session,
            turn_id=second.id,
            user_id=user.id,
            answer="두 번째 답변",
        )

        turns = get_recent_completed_turns(
            session=session,
            conversation_id=conversation.id,
            user_id=user.id,
            limit=2,
        )

        assert len(turns) == 2
        assert turns[0].id == second.id
        assert turns[1].id == first.id


def test_get_recent_completed_turns_excludes_incomplete_turns(
    engine,
    user,
):
    with Session(engine) as session:
        conversation = create_conversation(
            session=session,
            user_id=user.id,
            title="테스트 대화",
        )

        completed = create_pending_turn(
            session=session,
            conversation_id=conversation.id,
            user_id=user.id,
            client_request_id=uuid4(),
            request_id="request-1",
            level="easy",
            question="완료 질문",
        )
        complete_turn(
            session=session,
            turn_id=completed.id,
            user_id=user.id,
            answer="완료 답변",
        )

        pending = create_pending_turn(
            session=session,
            conversation_id=conversation.id,
            user_id=user.id,
            client_request_id=uuid4(),
            request_id="request-2",
            level="easy",
            question="진행 중 질문",
        )

        turns = get_recent_completed_turns(
            session=session,
            conversation_id=conversation.id,
            user_id=user.id,
            limit=20,
        )

        assert len(turns) == 1
        assert turns[0].id == completed.id
        assert turns[0].status == "completed"
        assert turns[0].id != pending.id


def test_get_recent_completed_turns_respects_limit(
    engine,
    user,
):
    with Session(engine) as session:
        conversation = create_conversation(
            session=session,
            user_id=user.id,
            title="테스트 대화",
        )

        turns = []

        for index in range(3):
            turn = create_pending_turn(
                session=session,
                conversation_id=conversation.id,
                user_id=user.id,
                client_request_id=uuid4(),
                request_id=f"request-{index}",
                level="easy",
                question=f"{index}번째 질문",
            )
            complete_turn(
                session=session,
                turn_id=turn.id,
                user_id=user.id,
                answer=f"{index}번째 답변",
            )
            turns.append(turn)

        recent_turns = get_recent_completed_turns(
            session=session,
            conversation_id=conversation.id,
            user_id=user.id,
            limit=2,
        )

        assert len(recent_turns) == 2
        assert recent_turns[0].id == turns[2].id
        assert recent_turns[1].id == turns[1].id


def test_list_conversations_returns_newest_first_with_pagination(
    engine,
    user,
):
    with Session(engine) as session:
        first = create_conversation(
            session=session,
            user_id=user.id,
            title="첫 번째 대화",
        )
        second = create_conversation(
            session=session,
            user_id=user.id,
            title="두 번째 대화",
        )
        third = create_conversation(
            session=session,
            user_id=user.id,
            title="세 번째 대화",
        )

        _stamp(session, first, 1)
        _stamp(session, second, 2)
        _stamp(session, third, 3)

        conversations, has_more = list_conversations_for_user(
            session=session,
            user_id=user.id,
            limit=2,
            offset=0,
        )

        assert len(conversations) == 2
        assert has_more is True
        assert conversations[0].id == third.id
        assert conversations[1].id == second.id

        conversations, has_more = list_conversations_for_user(
            session=session,
            user_id=user.id,
            limit=2,
            offset=2,
        )

        assert len(conversations) == 1
        assert has_more is False
        assert conversations[0].id == first.id


def test_new_turn_moves_conversation_to_top_of_list(engine, user):
    with Session(engine) as session:
        older = create_conversation(session=session, user_id=user.id, title="A")
        newer = create_conversation(session=session, user_id=user.id, title="B")
        _stamp(session, older, 1)
        _stamp(session, newer, 2)

        before, _ = list_conversations_for_user(
            session=session, user_id=user.id, limit=20, offset=0
        )
        assert [c.id for c in before] == [newer.id, older.id]

        create_pending_turn(
            session=session,
            conversation_id=older.id,
            user_id=user.id,
            client_request_id=uuid4(),
            request_id="request-1",
            level="easy",
            question="질문",
        )

        after, _ = list_conversations_for_user(
            session=session, user_id=user.id, limit=20, offset=0
        )
        assert [c.id for c in after] == [older.id, newer.id]


def test_list_conversations_only_returns_current_user_records(
    engine,
    user,
    other_user,
):
    with Session(engine) as session:
        own_conversation = create_conversation(
            session=session,
            user_id=user.id,
            title="내 대화",
        )

        other_conversation = create_conversation(
            session=session,
            user_id=other_user.id,
            title="다른 사용자 대화",
        )

        conversations, has_more = list_conversations_for_user(
            session=session,
            user_id=user.id,
            limit=20,
            offset=0,
        )

        assert has_more is False
        assert len(conversations) == 1
        assert conversations[0].id == own_conversation.id
        assert conversations[0].id != other_conversation.id


def test_get_conversation_turns_returns_oldest_first(
    engine,
    user,
):
    with Session(engine) as session:
        conversation = create_conversation(
            session=session,
            user_id=user.id,
            title="테스트 대화",
        )

        first = create_pending_turn(
            session=session,
            conversation_id=conversation.id,
            user_id=user.id,
            client_request_id=uuid4(),
            request_id="request-1",
            level="easy",
            question="첫 번째 질문",
        )
        complete_turn(
            session=session,
            turn_id=first.id,
            user_id=user.id,
            answer="첫 번째 답변",
        )

        second = create_pending_turn(
            session=session,
            conversation_id=conversation.id,
            user_id=user.id,
            client_request_id=uuid4(),
            request_id="request-2",
            level="easy",
            question="두 번째 질문",
        )
        complete_turn(
            session=session,
            turn_id=second.id,
            user_id=user.id,
            answer="두 번째 답변",
        )

        conversation_result, result = get_conversation_turns_for_user(
            session=session,
            conversation_id=conversation.id,
            user_id=user.id,
        )

        assert conversation_result.id == conversation.id
        assert len(result) == 2
        assert result[0].id == first.id
        assert result[1].id == second.id


def test_get_conversation_turns_returns_404_for_other_user(
    engine,
    user,
    other_user,
):
    with Session(engine) as session:
        conversation = create_conversation(
            session=session,
            user_id=user.id,
            title="내 대화",
        )

        with pytest.raises(AppError) as exc_info:
            get_conversation_turns_for_user(
                session=session,
                conversation_id=conversation.id,
                user_id=other_user.id,
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.code == ErrorCode.CONVERSATION_NOT_FOUND


def test_get_conversation_turns_returns_404_for_nonexistent_conversation(
    engine,
    user,
):
    with Session(engine) as session:
        with pytest.raises(AppError) as exc_info:
            get_conversation_turns_for_user(
                session=session,
                conversation_id=uuid4(),
                user_id=user.id,
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.code == ErrorCode.CONVERSATION_NOT_FOUND


def test_list_chats_returns_newest_first_with_pagination(
    engine,
    user,
):
    with Session(engine) as session:
        conversation = create_conversation(
            session=session,
            user_id=user.id,
            title="테스트 대화",
        )

        first = create_pending_turn(
            session=session,
            conversation_id=conversation.id,
            user_id=user.id,
            client_request_id=uuid4(),
            request_id="request-1",
            level="easy",
            question="첫 번째 질문",
        )
        complete_turn(
            session=session,
            turn_id=first.id,
            user_id=user.id,
            answer="첫 번째 답변",
        )

        second = create_pending_turn(
            session=session,
            conversation_id=conversation.id,
            user_id=user.id,
            client_request_id=uuid4(),
            request_id="request-2",
            level="easy",
            question="두 번째 질문",
        )
        complete_turn(
            session=session,
            turn_id=second.id,
            user_id=user.id,
            answer="두 번째 답변",
        )

        chats, has_more = list_chats_for_user(
            session=session,
            user_id=user.id,
            limit=1,
            offset=0,
        )

        assert len(chats) == 1
        assert has_more is True
        assert chats[0].id == second.id

        chats, has_more = list_chats_for_user(
            session=session,
            user_id=user.id,
            limit=1,
            offset=1,
        )

        assert len(chats) == 1
        assert has_more is False
        assert chats[0].id == first.id


def test_list_chats_only_returns_current_user_records(
    engine,
    user,
    other_user,
):
    with Session(engine) as session:
        own_conversation = create_conversation(
            session=session,
            user_id=user.id,
            title="내 대화",
        )

        other_conversation = create_conversation(
            session=session,
            user_id=other_user.id,
            title="다른 사용자 대화",
        )

        own_turn = create_pending_turn(
            session=session,
            conversation_id=own_conversation.id,
            user_id=user.id,
            client_request_id=uuid4(),
            request_id="request-1",
            level="easy",
            question="내 질문",
        )
        complete_turn(
            session=session,
            turn_id=own_turn.id,
            user_id=user.id,
            answer="내 답변",
        )

        other_turn = create_pending_turn(
            session=session,
            conversation_id=other_conversation.id,
            user_id=other_user.id,
            client_request_id=uuid4(),
            request_id="request-2",
            level="easy",
            question="다른 사용자 질문",
        )
        complete_turn(
            session=session,
            turn_id=other_turn.id,
            user_id=other_user.id,
            answer="다른 사용자 답변",
        )

        chats, has_more = list_chats_for_user(
            session=session,
            user_id=user.id,
            limit=20,
            offset=0,
        )

        assert has_more is False
        assert len(chats) == 1
        assert chats[0].id == own_turn.id
        assert chats[0].user_id == user.id

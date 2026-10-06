from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.chat.context import HistoryTurn, build_messages
from app.chat.provider import ChatMessage
from app.core.config import Settings

CONVERSATION_ID = UUID("00000000-0000-0000-0000-000000000001")
OTHER_CONVERSATION_ID = UUID("00000000-0000-0000-0000-000000000002")
START = datetime(2026, 10, 6, tzinfo=UTC)


def make_turn(
    turn_id,
    question="이전 질문",
    answer="이전 답변",
    *,
    user_id=1,
    conversation_id=CONVERSATION_ID,
    status="completed",
    created_at=None,
):
    return HistoryTurn(
        id=turn_id,
        user_id=user_id,
        conversation_id=conversation_id,
        question=question,
        answer=answer,
        status=status,
        created_at=created_at or START + timedelta(minutes=turn_id),
    )


def test_new_conversation_has_only_the_current_user_message():
    messages = build_messages(
        (), user_id=1, conversation_id=CONVERSATION_ID, question="첫 질문",
        max_turns=5,
        max_chars=12_000,
    )

    assert messages == [ChatMessage(role="user", content="첫 질문")]


def test_completed_turn_becomes_a_whole_question_answer_pair():
    history = [make_turn(1, "  이전 질문\n", "이전 답변\t ")]

    messages = build_messages(
        history, user_id=1, conversation_id=CONVERSATION_ID, question="더 쉽게",
        max_turns=5,
        max_chars=12_000,
    )

    assert messages == [
        ChatMessage(role="user", content="  이전 질문\n"),
        ChatMessage(role="assistant", content="이전 답변\t "),
        ChatMessage(role="user", content="더 쉽게"),
    ]


def test_history_is_sorted_by_time_before_id():
    earliest = make_turn(30, "처음 질문", "처음 답변", created_at=START)
    middle = make_turn(10, "다음 질문", "다음 답변", created_at=START + timedelta(minutes=1))
    latest = make_turn(20, "마지막 질문", "마지막 답변", created_at=START + timedelta(minutes=2))

    messages = build_messages(
        [latest, earliest, middle],
        user_id=1,
        conversation_id=CONVERSATION_ID,
        question="현재 질문",
        max_turns=5,
        max_chars=12_000,
    )

    assert [message.content for message in messages] == [
        "처음 질문", "처음 답변", "다음 질문", "다음 답변",
        "마지막 질문", "마지막 답변", "현재 질문",
    ]


def test_equal_timestamps_are_sorted_by_turn_id():
    history = [
        make_turn(turn_id, f"질문 {turn_id}", f"답변 {turn_id}", created_at=START)
        for turn_id in [3, 1, 2]
    ]

    messages = build_messages(
        history, user_id=1, conversation_id=CONVERSATION_ID, question="현재 질문",
        max_turns=5,
        max_chars=12_000,
    )

    assert [message.content for message in messages] == [
        "질문 1", "답변 1", "질문 2", "답변 2", "질문 3", "답변 3", "현재 질문"
    ]


def test_only_the_five_latest_completed_turns_are_kept():
    history = [
        make_turn(turn_id, f"질문 {turn_id}", f"답변 {turn_id}")
        for turn_id in [7, 1, 6, 2, 8, 5, 3, 4]
    ]

    messages = build_messages(
        history, user_id=1, conversation_id=CONVERSATION_ID, question="현재 질문",
        max_turns=5,
        max_chars=12_000,
    )

    assert [message.content for message in messages] == [
        "질문 4", "답변 4", "질문 5", "답변 5", "질문 6", "답변 6",
        "질문 7", "답변 7", "질문 8", "답변 8", "현재 질문",
    ]
    assert [message.role for message in messages] == ["user", "assistant"] * 5 + ["user"]
    assert all(isinstance(message, ChatMessage) for message in messages)


def test_other_owners_and_unfinished_turns_do_not_use_the_five_turn_budget():
    history = [make_turn(i, f"질문 {i}", f"답변 {i}") for i in range(1, 7)]
    history += [
        make_turn(7, "다른 사용자 질문", "다른 사용자 답변", user_id=2),
        make_turn(8, "다른 대화 질문", "다른 대화 답변", conversation_id=OTHER_CONVERSATION_ID),
        make_turn(9, status="pending"),
        make_turn(10, status="failed"),
        make_turn(11, status="interrupted"),
    ]

    messages = build_messages(
        history, user_id=1, conversation_id=CONVERSATION_ID, question="현재 질문",
        max_turns=5,
        max_chars=12_000,
    )

    assert [message.content for message in messages] == [
        "질문 2", "답변 2", "질문 3", "답변 3", "질문 4", "답변 4",
        "질문 5", "답변 5", "질문 6", "답변 6", "현재 질문",
    ]


@pytest.mark.parametrize(
    ("user_id", "conversation_id"),
    [(2, CONVERSATION_ID), (1, OTHER_CONVERSATION_ID)],
)
def test_a_different_user_or_conversation_cannot_reuse_the_history(user_id, conversation_id):
    messages = build_messages(
        [make_turn(1)], user_id=user_id, conversation_id=conversation_id, question="새 질문",
        max_turns=5,
        max_chars=12_000,
    )

    assert messages == [ChatMessage(role="user", content="새 질문")]


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        ("", "답변"),
        (" \t\n", "답변"),
        ("질문", None),
        ("질문", ""),
        ("질문", " \t\n"),
    ],
)
def test_missing_or_blank_history_content_is_excluded(question, answer):
    history = [make_turn(1, question, answer), make_turn(2, "유효 질문", "유효 답변")]

    messages = build_messages(
        history, user_id=1, conversation_id=CONVERSATION_ID, question="현재 질문",
        max_turns=5,
        max_chars=12_000,
    )

    assert messages == [
        ChatMessage(role="user", content="유효 질문"),
        ChatMessage(role="assistant", content="유효 답변"),
        ChatMessage(role="user", content="현재 질문"),
    ]


def test_exactly_12000_history_characters_are_kept_without_counting_the_current_question():
    previous_question = "가" * 6000
    previous_answer = "나" * 6000
    current_question = "현재 질문" * 1000

    messages = build_messages(
        [make_turn(1, previous_question, previous_answer)],
        user_id=1,
        conversation_id=CONVERSATION_ID,
        question=current_question,
        max_turns=5,
        max_chars=12_000,
    )

    assert messages == [
        ChatMessage(role="user", content=previous_question),
        ChatMessage(role="assistant", content=previous_answer),
        ChatMessage(role="user", content=current_question),
    ]


def test_one_character_over_budget_drops_the_oldest_whole_pair():
    history = [make_turn(1, "가" * 5999, "나" * 6000), make_turn(2, "Q", "A")]

    messages = build_messages(
        history, user_id=1, conversation_id=CONVERSATION_ID, question="현재 질문",
        max_turns=5,
        max_chars=12_000,
    )

    assert messages == [
        ChatMessage(role="user", content="Q"),
        ChatMessage(role="assistant", content="A"),
        ChatMessage(role="user", content="현재 질문"),
    ]


def test_budget_keeps_the_newest_whole_pairs():
    history = [
        make_turn(1, "가" * 3000, "나" * 3000),
        make_turn(2, "다" * 3000, "라" * 3000),
        make_turn(3, "마" * 3000, "바" * 3000),
        make_turn(4, "사" * 3000, "아" * 3000),
    ]

    messages = build_messages(
        history, user_id=1, conversation_id=CONVERSATION_ID, question="현재 질문",
        max_turns=5,
        max_chars=12_000,
    )

    assert messages == [
        ChatMessage(role="user", content="마" * 3000),
        ChatMessage(role="assistant", content="바" * 3000),
        ChatMessage(role="user", content="사" * 3000),
        ChatMessage(role="assistant", content="아" * 3000),
        ChatMessage(role="user", content="현재 질문"),
    ]


def test_an_oversized_latest_pair_leaves_only_the_current_question():
    history = [make_turn(1), make_turn(2, "가" * 6001, "나" * 6000)]

    messages = build_messages(
        history, user_id=1, conversation_id=CONVERSATION_ID, question="핵심만",
        max_turns=5,
        max_chars=12_000,
    )

    assert messages == [ChatMessage(role="user", content="핵심만")]


def test_other_users_large_content_does_not_use_the_character_budget():
    history = [make_turn(1), make_turn(2, "가" * 12000, "나" * 12000, user_id=2)]

    messages = build_messages(
        history, user_id=1, conversation_id=CONVERSATION_ID, question="현재 질문",
        max_turns=5,
        max_chars=12_000,
    )

    assert messages == [
        ChatMessage(role="user", content="이전 질문"),
        ChatMessage(role="assistant", content="이전 답변"),
        ChatMessage(role="user", content="현재 질문"),
    ]


@pytest.mark.parametrize("question", [" \n더 쉽게\t ", "긴 질문" * 4000])
def test_current_question_is_preserved_without_trimming_or_truncation(question):
    messages = build_messages(
        (), user_id=1, conversation_id=CONVERSATION_ID, question=question,
        max_turns=5,
        max_chars=12_000,
    )

    assert messages == [ChatMessage(role="user", content=question)]


def test_building_messages_does_not_change_the_input_order_or_turns():
    history = [make_turn(2), make_turn(1)]
    original = list(history)

    build_messages(
        history, user_id=1, conversation_id=CONVERSATION_ID, question="현재 질문",
        max_turns=5,
        max_chars=12_000,
    )

    assert history == original
    assert [turn.id for turn in history] == [2, 1]
    with pytest.raises(FrozenInstanceError):
        history[0].question = "바뀐 질문"


def test_sequential_calls_do_not_share_a_message_list():
    first = build_messages(
        [make_turn(1)], user_id=1, conversation_id=CONVERSATION_ID, question="첫 사용자 질문",
        max_turns=5,
        max_chars=12_000,
    )
    first.append(ChatMessage(role="assistant", content="호출 이후 덧붙인 답변"))

    second = build_messages(
        (), user_id=2, conversation_id=OTHER_CONVERSATION_ID, question="다른 사용자 질문",
        max_turns=5,
        max_chars=12_000,
    )
    third = build_messages(
        [make_turn(1)], user_id=1, conversation_id=CONVERSATION_ID, question="다음 질문",
        max_turns=5,
        max_chars=12_000,
    )

    assert second == [ChatMessage(role="user", content="다른 사용자 질문")]
    assert third == [
        ChatMessage(role="user", content="이전 질문"),
        ChatMessage(role="assistant", content="이전 답변"),
        ChatMessage(role="user", content="다음 질문"),
    ]
    assert first is not second
    assert first is not third


@pytest.mark.parametrize(
    ("max_turns", "expected_turn_ids"),
    [(1, [6]), (2, [5, 6]), (6, [1, 2, 3, 4, 5, 6])],
)
def test_the_requested_turn_limit_can_be_smaller_or_larger_than_five(
    max_turns, expected_turn_ids
):
    history = [make_turn(i, f"질문 {i}", f"답변 {i}") for i in range(1, 7)]

    messages = build_messages(
        history,
        user_id=1,
        conversation_id=CONVERSATION_ID,
        question="현재 질문",
        max_turns=max_turns,
        max_chars=12_000,
    )

    expected = []
    for turn_id in expected_turn_ids:
        expected.append(ChatMessage(role="user", content=f"질문 {turn_id}"))
        expected.append(ChatMessage(role="assistant", content=f"답변 {turn_id}"))
    expected.append(ChatMessage(role="user", content="현재 질문"))
    assert messages == expected


@pytest.mark.parametrize(
    ("max_chars", "expected_content"),
    [
        (6, ["가", "나", "다다", "라라", "현재 질문"]),
        (5, ["다다", "라라", "현재 질문"]),
        (4, ["다다", "라라", "현재 질문"]),
        (3, ["현재 질문"]),
    ],
)
def test_the_requested_character_budget_keeps_complete_pairs_at_its_boundary(
    max_chars, expected_content
):
    history = [make_turn(1, "가", "나"), make_turn(2, "다다", "라라")]

    messages = build_messages(
        history,
        user_id=1,
        conversation_id=CONVERSATION_ID,
        question="현재 질문",
        max_turns=5,
        max_chars=max_chars,
    )

    assert [message.content for message in messages] == expected_content
    assert [message.role for message in messages] == (
        ["user", "assistant"] * ((len(expected_content) - 1) // 2) + ["user"]
    )


@pytest.mark.parametrize(
    ("max_turns", "max_chars"),
    [(0, 12_000), (5, 0), (0, 0)],
)
def test_zero_turns_or_character_budget_keeps_only_the_current_question(max_turns, max_chars):
    question = " \n현재 질문\t "

    messages = build_messages(
        [make_turn(1), make_turn(2)],
        user_id=1,
        conversation_id=CONVERSATION_ID,
        question=question,
        max_turns=max_turns,
        max_chars=max_chars,
    )

    assert messages == [ChatMessage(role="user", content=question)]


@pytest.mark.parametrize(
    ("max_turns", "max_chars"),
    [(-1, 12_000), (5, -1), (0, -1), (-1, 0)],
)
def test_negative_limits_are_rejected_even_if_the_other_limit_is_zero(max_turns, max_chars):
    with pytest.raises(ValueError):
        build_messages(
            (),
            user_id=1,
            conversation_id=CONVERSATION_ID,
            question="현재 질문",
            max_turns=max_turns,
            max_chars=max_chars,
        )


@pytest.mark.parametrize(
    ("context_turns", "context_max_chars", "expected_content"),
    [
        (1, 100, ["Q3", "A3", "현재 질문"]),
        (3, 8, ["Q2", "A2", "Q3", "A3", "현재 질문"]),
    ],
)
def test_environment_settings_change_selection_when_the_caller_passes_them(
    monkeypatch, context_turns, context_max_chars, expected_content
):
    monkeypatch.setenv("CONTEXT_TURNS", str(context_turns))
    monkeypatch.setenv("CONTEXT_MAX_CHARS", str(context_max_chars))
    settings = Settings(_env_file=None, app_env="test", ai_provider="fake")
    history = [make_turn(i, f"Q{i}", f"A{i}") for i in range(1, 4)]

    messages = build_messages(
        history,
        user_id=1,
        conversation_id=CONVERSATION_ID,
        question="현재 질문",
        max_turns=settings.context_turns,
        max_chars=settings.context_max_chars,
    )

    assert settings.context_turns == context_turns
    assert settings.context_max_chars == context_max_chars
    assert [message.content for message in messages] == expected_content

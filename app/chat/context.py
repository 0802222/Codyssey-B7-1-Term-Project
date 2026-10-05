"""같은 사용자·대화의 최근 문맥을 AI 메시지로 구성한다. (EE-10)"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from app.chat.provider import ChatMessage

MAX_HISTORY_TURNS = 5
MAX_HISTORY_CHARACTERS = 12_000


@dataclass(frozen=True)
class HistoryTurn:
    """DB 모델 대신 함수에 전달하는 읽기 전용 Q/A 자료. 시각은 UTC를 사용한다."""

    id: int
    user_id: int
    conversation_id: UUID
    question: str
    answer: str | None
    status: Literal["pending", "completed", "failed", "interrupted"]
    created_at: datetime


def build_messages(
    history: Sequence[HistoryTurn],
    *,
    user_id: int,
    conversation_id: UUID,
    question: str,
) -> list[ChatMessage]:
    """과거 Q/A와 현재 질문을 반환한다. 입력 자료를 바꾸거나 보관하지 않는다.

    user_id는 서버 인증 결과, conversation_id는 소유권 확인을 마친 대화 ID여야 한다.
    현재 질문의 공백 제거·길이 검증과 DB 조회·소유권 검사는 호출하는 서비스가 맡는다.
    """
    # 1. 범위와 완료 여부부터 확인해야 다른 사람·실패 턴이 최근 5턴을 차지하지 않는다.
    completed_turns = []
    for turn in history:
        if (
            turn.user_id == user_id
            and turn.conversation_id == conversation_id
            and turn.status == "completed"
            and turn.question.strip()
            and turn.answer is not None
            and turn.answer.strip()
        ):
            completed_turns.append(turn)

    # 2. 같은 시각이면 ID로 순서를 정하고, 가장 최근 5턴을 과거순으로 사용한다.
    completed_turns.sort(key=lambda turn: (turn.created_at, turn.id))
    messages = []
    for turn in completed_turns[-MAX_HISTORY_TURNS:]:
        messages.append(ChatMessage(role="user", content=turn.question))
        messages.append(ChatMessage(role="assistant", content=turn.answer or ""))

    # 3. 예산은 과거 대화의 문자 수다. 질문·답변을 한 쌍씩 제거해 대화 순서를 지킨다.
    while sum(len(message.content) for message in messages) > MAX_HISTORY_CHARACTERS:
        del messages[:2]

    # 현재 질문은 과거 문맥 예산 때문에 제거하지 않는다. system 지침은 별도 인자다.
    messages.append(ChatMessage(role="user", content=question))
    return messages

"""채팅 API의 입력·출력 형식. (EE-13)"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.chat.prompts import ExplanationLevel


class ChatRequest(BaseModel):
    # user_id처럼 약속하지 않은 필드는 받지 않는다. 사용자는 로그인 결과로 결정한다.
    model_config = ConfigDict(extra="forbid")

    conversation_id: UUID
    question: str = Field(min_length=1, max_length=2000)
    level: ExplanationLevel
    client_request_id: UUID

    @field_validator("question", mode="before")
    @classmethod
    def trim_question(cls, value: object) -> object:
        # 공백을 먼저 빼야 "   "도 빈 질문으로 거부한다.
        return value.strip() if isinstance(value, str) else value


class ChatResponse(BaseModel):
    request_id: str
    turn_id: int
    conversation_id: UUID
    level: ExplanationLevel
    question: str
    answer: str
    status: Literal["completed"]
    created_at: datetime

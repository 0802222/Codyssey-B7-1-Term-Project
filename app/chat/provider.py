"""AI provider 경계. (B 담당, EE-05)

채팅 서비스는 이 인터페이스만 알고, 실제 API(Anthropic) 와 FakeAIProvider 가 이를 구현한다.
provider 는 실패 시 아래 AIProviderError 하위 예외만 raise 하고, HTTP 오류 변환은 서비스에서 한다.
    AITimeoutError     -> 504 AI_TIMEOUT
    AIUpstreamError    -> 502 AI_UPSTREAM_ERROR  (연결 실패, 상위 5xx, 빈 응답)
    AIUnavailableError -> 503 AI_UNAVAILABLE     (이용 한도, 인증·설정 문제)
"""

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class AIResult:
    text: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class AIProviderError(Exception):
    pass


class AITimeoutError(AIProviderError):
    pass


class AIUpstreamError(AIProviderError):
    pass


class AIUnavailableError(AIProviderError):
    pass


class AIProvider(Protocol):
    async def generate_reply(
        self,
        messages: list[ChatMessage],
        *,
        system: str,
        timeout_seconds: float,
        max_output_tokens: int,
    ) -> AIResult:
        """messages 는 과거순 [user, assistant, ..., user(현재 질문)].

        system 은 Anthropic 규격처럼 messages 와 분리해서 전달한다.
        """
        ...

"""외부 API 없이 정상·실패를 재현하는 AI provider. (B 담당, EE-05)

모드는 개발·테스트 코드에서 객체를 만들 때만 지정한다. 공개 요청으로 선택하지 않는다.
실제 지연이나 네트워크 호출 없이 실패를 재현하며, 질문·답변·시스템 지침을 기록하지 않는다.
"""

from enum import StrEnum

from app.chat.provider import (
    AIResult,
    AITimeoutError,
    AIUnavailableError,
    AIUpstreamError,
    ChatMessage,
)


class FakeMode(StrEnum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    UPSTREAM_ERROR = "upstream_error"
    UNAVAILABLE = "unavailable"
    EMPTY = "empty"


class FakeAIProvider:
    def __init__(
        self,
        *,
        mode: FakeMode | str = FakeMode.SUCCESS,
        reply: str = "[모의 응답] 외부 AI 호출 없이 반환한 테스트 답변입니다.",
    ) -> None:
        self.mode = FakeMode(mode)
        self.reply = reply

    async def generate_reply(
        self,
        messages: list[ChatMessage],
        *,
        system: str,
        timeout_seconds: float,
        max_output_tokens: int,
    ) -> AIResult:
        """실제 provider와 같은 호출 계약. 입력 문맥을 수정하거나 보관하지 않는다.

        시간·토큰 인자는 호출 계약을 유지한다. Fake는 기다리거나 토큰 사용량을 추정하지 않는다.
        빈 응답도 계약에 맞게 AIUpstreamError로 알린다. HTTP 변환은 후속 채팅 서비스의 책임이다.
        """
        if self.mode == FakeMode.TIMEOUT:
            raise AITimeoutError("모의 AI 응답 대기 시간이 초과됐습니다.")
        if self.mode == FakeMode.UPSTREAM_ERROR:
            raise AIUpstreamError("모의 AI 연결 또는 상위 서버 오류입니다.")
        if self.mode == FakeMode.UNAVAILABLE:
            raise AIUnavailableError("모의 AI를 이용할 수 없습니다.")

        text = "" if self.mode == FakeMode.EMPTY else self.reply
        if not text.strip():
            raise AIUpstreamError("모의 AI 응답이 비어 있습니다.")
        return AIResult(text=text, model="fake")

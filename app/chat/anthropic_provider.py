"""코디세이 게이트웨이를 통해 Anthropic Messages API를 호출한다. (B, EE-13)"""

import asyncio

from anthropic import APIError, APIStatusError, APITimeoutError, AsyncAnthropic

from app.chat.provider import (
    AIResult,
    AITimeoutError,
    AIUnavailableError,
    AIUpstreamError,
    ChatMessage,
)
from app.core.config import Settings


class AnthropicProvider:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def generate_reply(
        self,
        messages: list[ChatMessage],
        *,
        system: str,
        timeout_seconds: float,
        max_output_tokens: int,
    ) -> AIResult:
        settings = self._settings
        key = settings.anthropic_api_key
        if key is None or not key.get_secret_value().strip() or not settings.ai_model.strip():
            raise AIUnavailableError("AI 설정을 확인해 주세요.")

        try:
            # SDK의 구간별 제한과 별도로, 연결부터 응답까지 전체 대기 시간을 제한한다.
            async with asyncio.timeout(timeout_seconds):
                async with AsyncAnthropic(
                    api_key=key.get_secret_value(),
                    base_url=settings.anthropic_base_url,
                    timeout=timeout_seconds,
                    max_retries=0,  # 같은 질문으로 비용이 중복 발생하지 않게 자동 재시도를 끈다.
                ) as client:
                    response = await client.messages.create(
                        model=settings.ai_model,
                        system=system,
                        messages=[
                            {"role": item.role, "content": item.content} for item in messages
                        ],
                        max_tokens=max_output_tokens,
                    )
        except (APITimeoutError, TimeoutError):
            raise AITimeoutError("AI 응답 시간이 초과되었어요.") from None
        except APIStatusError as exc:
            if exc.status_code in {401, 403, 404, 429}:
                raise AIUnavailableError("현재 AI를 이용할 수 없어요.") from None
            raise AIUpstreamError("AI 서버에서 오류가 발생했어요.") from None
        except (APIError, ValueError):
            # SDK 예외 원문에는 요청 내용이나 인증 정보가 섞일 수 있어 전달하지 않는다.
            raise AIUpstreamError("AI 응답을 받지 못했어요.") from None

        content = getattr(response, "content", None)
        model = getattr(response, "model", None)
        if not isinstance(content, list) or not isinstance(model, str) or not model.strip():
            raise AIUpstreamError("AI 응답 형식이 올바르지 않아요.")

        parts = []
        for block in content:
            if getattr(block, "type", None) == "text":
                text = getattr(block, "text", None)
                if not isinstance(text, str):
                    raise AIUpstreamError("AI 응답 형식이 올바르지 않아요.")
                parts.append(text)
        answer = "".join(parts).strip()
        if not answer:
            raise AIUpstreamError("AI가 빈 응답을 반환했어요.")

        usage = getattr(response, "usage", None)
        return AIResult(
            text=answer,
            model=model,
            input_tokens=_token_count(getattr(usage, "input_tokens", None)),
            output_tokens=_token_count(getattr(usage, "output_tokens", None)),
        )


def _token_count(value: object) -> int | None:
    """게이트웨이가 사용량을 생략하면 답변은 유지하고 사용량만 None으로 둔다."""
    return value if type(value) is int and value >= 0 else None

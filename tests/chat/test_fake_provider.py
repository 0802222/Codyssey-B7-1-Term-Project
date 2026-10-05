import asyncio
import gc
import time
import weakref

import httpx
import pytest

from app.chat.fake_provider import FakeAIProvider, FakeMode
from app.chat.provider import (
    AIResult,
    AITimeoutError,
    AIUnavailableError,
    AIUpstreamError,
    ChatMessage,
)


@pytest.fixture(autouse=True)
def reject_http_calls_and_delays(monkeypatch):
    def reject(*args, **kwargs):
        pytest.fail("가짜 AI 는 HTTP 요청이나 실제 대기를 하지 않아야 합니다.")

    monkeypatch.setattr(httpx.Client, "send", reject)
    monkeypatch.setattr(httpx.AsyncClient, "send", reject)
    monkeypatch.setattr(asyncio, "sleep", reject)
    monkeypatch.setattr(time, "sleep", reject)


def generate_reply(provider, messages=None):
    if messages is None:
        messages = [ChatMessage(role="user", content="API 를 설명해 주세요.")]
    return asyncio.run(
        provider.generate_reply(
            messages,
            system="한국어로 설명합니다.",
            timeout_seconds=0.01,
            max_output_tokens=40,
        )
    )


def test_default_reply_has_fake_result_contract_without_api_key():
    result = generate_reply(FakeAIProvider())

    assert isinstance(result, AIResult)
    assert result.text.startswith("[모의 응답]")
    assert result.model == "fake"
    assert result.input_tokens is None
    assert result.output_tokens is None


@pytest.mark.parametrize("mode", [FakeMode.SUCCESS, "success"])
def test_custom_nonempty_reply_is_returned_unchanged(mode):
    reply = "  테스트용 답변입니다.\n"

    result = generate_reply(FakeAIProvider(mode=mode, reply=reply))

    assert result == AIResult(text=reply, model="fake")


@pytest.mark.parametrize(
    ("mode", "error_type"),
    [
        ("timeout", AITimeoutError),
        ("upstream_error", AIUpstreamError),
        ("unavailable", AIUnavailableError),
        ("empty", AIUpstreamError),
    ],
)
def test_failure_modes_raise_the_provider_contract_error(mode, error_type):
    with pytest.raises(error_type):
        generate_reply(FakeAIProvider(mode=mode))


@pytest.mark.parametrize("reply", ["", " ", "\t\n", "\u2003"])
def test_empty_or_whitespace_reply_is_an_upstream_error(reply):
    with pytest.raises(AIUpstreamError):
        generate_reply(FakeAIProvider(reply=reply))


def test_invalid_mode_fails_when_the_provider_is_configured():
    with pytest.raises(ValueError):
        FakeAIProvider(mode="unknown")


def test_concurrent_requests_do_not_mutate_or_mix_messages():
    provider = FakeAIProvider(reply="고정된 모의 답변")
    first = [
        ChatMessage(role="user", content="첫 번째 질문"),
        ChatMessage(role="assistant", content="이전 답변"),
        ChatMessage(role="user", content="추가 질문"),
    ]
    second = [ChatMessage(role="user", content="다른 사용자의 질문")]
    original_first = list(first)
    original_second = list(second)

    async def concurrent_replies():
        return await asyncio.gather(
            provider.generate_reply(
                first, system="첫 사용자", timeout_seconds=0.01, max_output_tokens=40
            ),
            provider.generate_reply(
                second, system="다른 사용자", timeout_seconds=0.01, max_output_tokens=40
            ),
        )

    results = asyncio.run(concurrent_replies())

    assert first == original_first
    assert second == original_second
    assert results == [AIResult(text="고정된 모의 답변", model="fake")] * 2


def test_provider_does_not_retain_a_previous_requests_message():
    provider = FakeAIProvider()
    messages = [ChatMessage(role="user", content="이 요청에만 속하는 질문")]
    message_reference = weakref.ref(messages[0])

    generate_reply(provider, messages)
    del messages
    gc.collect()

    assert message_reference() is None

import asyncio
import json
import time

import httpx2
import pytest
from anthropic import AsyncAnthropic
from pydantic import SecretStr

from app.chat.anthropic_provider import AnthropicProvider
from app.chat.provider import (
    AIResult,
    AITimeoutError,
    AIUnavailableError,
    AIUpstreamError,
    ChatMessage,
)
from app.core.config import Settings


@pytest.fixture
def provider():
    return AnthropicProvider(
        Settings(
            _env_file=None,
            app_env="test",
            ai_provider="anthropic",
            anthropic_api_key=SecretStr("unused-test-placeholder"),
            anthropic_base_url="https://gateway.example.test",
            ai_model="configured-model",
        )
    )


@pytest.fixture
def mock_sdk(monkeypatch):
    """실제 SDK를 사용하되 HTTP 전송만 가짜로 바꿔 유료 호출을 막는다."""

    def install(handler):
        requests, clients, options = [], [], []

        async def transport(request):
            requests.append(request)
            response = handler(request)
            if asyncio.iscoroutine(response):
                response = await response
            return response

        def make_client(**kwargs):
            options.append(kwargs)
            http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(transport))
            client = AsyncAnthropic(**kwargs, http_client=http_client)
            clients.append(client)
            return client

        monkeypatch.setattr("app.chat.anthropic_provider.AsyncAnthropic", make_client)
        return requests, clients, options

    return install


def response_body(**overrides):
    return {
        "id": "test-message",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "첫 문장. "}, {"type": "text", "text": "둘째 문장."}],
        "model": "response-model",
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 12, "output_tokens": 8},
        **overrides,
    }


def generate(provider, *, timeout_seconds=1):
    return asyncio.run(
        provider.generate_reply(
            [ChatMessage(role="user", content="질문")],
            system="시스템 안내",
            timeout_seconds=timeout_seconds,
            max_output_tokens=77,
        )
    )


def test_sends_messages_to_configured_gateway_and_closes_client(provider, mock_sdk):
    requests, clients, options = mock_sdk(
        lambda request: httpx2.Response(200, json=response_body())
    )
    messages = [
        ChatMessage(role="user", content="이전 질문"),
        ChatMessage(role="assistant", content="이전 답변"),
        ChatMessage(role="user", content="현재 질문"),
    ]

    result = asyncio.run(
        provider.generate_reply(
            messages, system="별도의 시스템 안내", timeout_seconds=1, max_output_tokens=77
        )
    )

    assert result == AIResult("첫 문장. 둘째 문장.", "response-model", 12, 8)
    assert len(requests) == 1
    assert str(requests[0].url) == "https://gateway.example.test/v1/messages"
    assert json.loads(requests[0].content) == {
        "model": "configured-model",
        "system": "별도의 시스템 안내",
        "messages": [{"role": message.role, "content": message.content} for message in messages],
        "max_tokens": 77,
    }
    assert options[0]["max_retries"] == 0
    assert options[0]["timeout"] == 1
    assert clients[0].is_closed()


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, AIUnavailableError),
        (403, AIUnavailableError),
        (404, AIUnavailableError),
        (429, AIUnavailableError),
        (400, AIUpstreamError),
        (500, AIUpstreamError),
        (502, AIUpstreamError),
    ],
)
def test_translates_status_errors_without_retry_or_raw_message(
    provider, mock_sdk, status, expected
):
    requests, clients, _ = mock_sdk(
        lambda request: httpx2.Response(
            status,
            json={"type": "error", "error": {"type": "api_error", "message": "private detail"}},
        )
    )

    with pytest.raises(expected) as caught:
        generate(provider)

    assert "private detail" not in str(caught.value)
    assert caught.value.__suppress_context__
    assert len(requests) == 1
    assert clients[0].is_closed()


@pytest.mark.parametrize(
    ("transport_error", "expected"),
    [(httpx2.ReadTimeout, AITimeoutError), (httpx2.ConnectError, AIUpstreamError)],
)
def test_translates_sdk_network_errors(provider, mock_sdk, transport_error, expected):
    def error_response(request):
        raise transport_error("private connection detail", request=request)

    requests, clients, _ = mock_sdk(error_response)
    with pytest.raises(expected) as caught:
        generate(provider)

    assert "private connection detail" not in str(caught.value)
    assert len(requests) == 1
    assert clients[0].is_closed()


def test_limits_total_wait_even_when_transport_does_not_apply_socket_timeout(provider, mock_sdk):
    async def slow_response(request):
        await asyncio.sleep(1)
        return httpx2.Response(200, json=response_body())

    requests, clients, _ = mock_sdk(slow_response)
    started = time.monotonic()
    with pytest.raises(AITimeoutError):
        generate(provider, timeout_seconds=0.02)

    assert time.monotonic() - started < 0.5
    assert len(requests) == 1
    assert clients[0].is_closed()


@pytest.mark.parametrize(
    "body",
    [
        response_body(content=[]),
        response_body(content=[{"type": "text", "text": "  "}]),
        response_body(content=None),
        response_body(content="bad content"),
        response_body(content=[{"type": "text", "text": 123}]),
        response_body(model=None),
        {"unexpected": "response"},
    ],
)
def test_rejects_empty_or_invalid_response(provider, mock_sdk, body):
    requests, clients, _ = mock_sdk(lambda request: httpx2.Response(200, json=body))

    with pytest.raises(AIUpstreamError):
        generate(provider)

    assert len(requests) == 1
    assert clients[0].is_closed()


def test_rejects_invalid_json(provider, mock_sdk):
    mock_sdk(lambda request: httpx2.Response(200, text="invalid JSON"))

    with pytest.raises(AIUpstreamError):
        generate(provider)


def test_usage_is_optional(provider, mock_sdk):
    body = response_body()
    del body["usage"]
    mock_sdk(lambda request: httpx2.Response(200, json=body))

    result = generate(provider)

    assert result.text == "첫 문장. 둘째 문장."
    assert result.input_tokens is None
    assert result.output_tokens is None

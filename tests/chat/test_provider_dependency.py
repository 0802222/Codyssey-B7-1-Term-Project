import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.chat.anthropic_provider import AnthropicProvider
from app.chat.fake_provider import FakeAIProvider, FakeMode
from app.chat.provider import (
    AIProviderDep,
    AIProviderError,
    AIResult,
    ChatMessage,
    get_ai_provider,
)
from app.core.config import Settings
from app.main import create_app

PROBE_PATH = "/_test/ai-provider"


def add_provider_probe(app):
    # 채팅 처리와 별도로 FastAPI의 provider 의존성 연결만 검증한다.
    @app.post(PROBE_PATH)
    async def provider_probe(provider: AIProviderDep) -> AIResult | dict[str, str]:
        try:
            return await provider.generate_reply(
                [ChatMessage(role="user", content="테스트 질문")],
                system="테스트용 시스템 프롬프트",
                timeout_seconds=0.01,
                max_output_tokens=40,
            )
        except AIProviderError as exc:
            # HTTP 오류 매핑(EE-16) 대신 주입한 provider 의 예외 종류만 관찰한다.
            return {"provider_error": type(exc).__name__}


@pytest.fixture
def provider_app(app):
    add_provider_probe(app)
    return app


def test_app_settings_select_fake_provider(provider_app):
    assert provider_app.state.settings.ai_provider == "fake"
    assert provider_app.state.settings.anthropic_api_key is None

    with TestClient(provider_app) as client:
        response = client.post(PROBE_PATH)

    assert response.status_code == 200
    result = response.json()
    assert result["text"].startswith("[모의 응답]")
    assert result["model"] == "fake"
    assert result["input_tokens"] is None
    assert result["output_tokens"] is None


def test_dependency_override_injects_another_provider(provider_app):
    class TestProvider:
        async def generate_reply(self, messages, *, system, timeout_seconds, max_output_tokens):
            assert messages == [ChatMessage(role="user", content="테스트 질문")]
            assert system == "테스트용 시스템 프롬프트"
            return AIResult(
                text="주입한 답변", model="test-provider", input_tokens=12, output_tokens=8
            )

    provider_app.dependency_overrides[get_ai_provider] = TestProvider

    with TestClient(provider_app) as client:
        response = client.post(PROBE_PATH)

    assert response.status_code == 200
    assert response.json() == {
        "text": "주입한 답변",
        "model": "test-provider",
        "input_tokens": 12,
        "output_tokens": 8,
    }


def test_dependency_override_can_inject_a_timeout(provider_app):
    provider_app.dependency_overrides[get_ai_provider] = lambda: FakeAIProvider(
        mode=FakeMode.TIMEOUT
    )

    with TestClient(provider_app) as client:
        response = client.post(PROBE_PATH)

    assert response.status_code == 200
    assert response.json() == {"provider_error": "AITimeoutError"}


def test_request_cannot_select_a_provider_or_fake_failure_mode(provider_app):
    with TestClient(provider_app) as client:
        response = client.post(
            f"{PROBE_PATH}?ai_provider=anthropic&provider=anthropic&mode=timeout"
        )

    assert response.status_code == 200
    assert response.json()["model"] == "fake"
    assert response.json()["text"].startswith("[모의 응답]")


def test_dependency_does_not_expose_provider_or_mode_in_openapi(provider_app):
    operation = provider_app.openapi()["paths"][PROBE_PATH]["post"]

    assert operation.get("parameters", []) == []
    assert "requestBody" not in operation


def test_app_settings_select_anthropic_provider(settings, monkeypatch):
    anthropic_settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=settings.database_url,
        ai_provider="anthropic",
        anthropic_api_key=SecretStr("unused-test-placeholder"),
    )
    app = create_app(anthropic_settings)
    add_provider_probe(app)
    calls = []

    async def reply(self, messages, **kwargs):
        assert self._settings is anthropic_settings
        calls.append(messages)
        return AIResult(text="게이트웨이 응답", model=anthropic_settings.ai_model)

    monkeypatch.setattr(AnthropicProvider, "generate_reply", reply)
    assert isinstance(get_ai_provider(anthropic_settings), AnthropicProvider)

    with TestClient(app) as client:
        response = client.post(PROBE_PATH)

    assert response.status_code == 200
    assert response.json()["text"] == "게이트웨이 응답"
    assert response.json()["model"] == anthropic_settings.ai_model
    assert len(calls) == 1

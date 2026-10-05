import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_defaults_use_fake_provider():
    settings = Settings(_env_file=None)

    assert settings.ai_provider == "fake"
    assert settings.anthropic_api_key is None


@pytest.mark.parametrize("app_env", ["development", "production"])
@pytest.mark.parametrize("api_key", [None, "", "   "])
def test_anthropic_provider_requires_non_blank_key(app_env, api_key):
    # .env.example 을 그대로 복사하면 ANTHROPIC_API_KEY= (빈 값)이 된다.
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env=app_env,
            ai_provider="anthropic",
            anthropic_api_key=api_key,
            cookie_secure=True,
        )


def test_production_rejects_fake_provider():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", ai_provider="fake", cookie_secure=True)


def test_production_requires_secure_cookie():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="production",
            ai_provider="anthropic",
            anthropic_api_key="test-key",
            cookie_secure=False,
        )


def test_api_key_is_hidden_in_repr():
    settings = Settings(_env_file=None, ai_provider="anthropic", anthropic_api_key="test-key")

    assert "test-key" not in repr(settings)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ai_timeout_seconds", 0),
        ("ai_max_output_tokens", 0),
        ("context_turns", -1),
        ("context_max_chars", -1),
        ("session_ttl_seconds", 0),
        ("user_requests_per_minute", 0),
        ("daily_request_limit", 0),
    ],
)
def test_numeric_settings_out_of_range_are_rejected_at_startup(field, value):
    # 잘못된 값으로 서버가 켜진 뒤 요청마다 실패하지 않도록, 시작할 때 막는다.
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


def test_zero_context_is_allowed_to_disable_history():
    settings = Settings(_env_file=None, context_turns=0, context_max_chars=0)

    assert settings.context_turns == 0
    assert settings.context_max_chars == 0

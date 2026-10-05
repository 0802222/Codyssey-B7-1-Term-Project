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

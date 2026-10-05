"""환경 변수(.env) 설정. 값은 코드에 쓰지 않고 여기서만 읽는다."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 환경 변수 이름은 대소문자를 구분하지 않는다. (APP_ENV == app_env)
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./data/easyexplain.db"
    site_origin: str = "http://localhost:8000"
    log_level: str = "INFO"

    # AI
    ai_provider: Literal["fake", "anthropic"] = "fake"
    anthropic_base_url: str = "https://copa.codyssey.kr"
    anthropic_api_key: SecretStr | None = None
    ai_model: str = "claude-sonnet-4"
    ai_timeout_seconds: float = 30.0
    ai_max_output_tokens: int = 800
    context_turns: int = 5
    context_max_chars: int = 12_000

    # 인증
    session_ttl_seconds: int = 7_200
    cookie_secure: bool = False

    # 요청 한도
    user_requests_per_minute: int = 10
    daily_request_limit: int = 200

    @model_validator(mode="after")
    def _check_consistency(self) -> "Settings":
        if self.ai_provider == "anthropic" and self.anthropic_api_key is None:
            raise ValueError("AI_PROVIDER=anthropic 이면 ANTHROPIC_API_KEY 가 필요합니다.")
        if self.app_env == "production":
            if self.ai_provider == "fake":
                raise ValueError("production 에서는 AI_PROVIDER=fake 로 기동할 수 없습니다.")
            if not self.cookie_secure:
                raise ValueError("production 에서는 COOKIE_SECURE=true 가 필요합니다.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

"""공통 테스트 환경. (L 담당)

- 테스트마다 임시 SQLite 파일을 쓴다. 로컬 .env 와 실제 DB 는 읽지 않는다.
- AI 는 항상 fake. 실제 키 없이 돈다.
- 로그인이 필요한 API 는 `logged_in_client` 로 테스트한다. (A 의 EE-08 을 기다리지 않기 위해)
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import CurrentUser, get_current_user, get_optional_user, require_csrf
from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        ai_provider="fake",
    )


@pytest.fixture
def app(settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app):
    # raise_server_exceptions=False: 500 응답 형식까지 확인하기 위해
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def current_user() -> CurrentUser:
    return CurrentUser(id=1, email="tester@example.com")


@pytest.fixture
def logged_in_client(app, current_user):
    """로그인·CSRF 검사를 통과한 것으로 치는 client.

    get_current_user·get_optional_user·require_csrf 를 가짜로 바꿔 끼운다.
    인증 자체를 검증하는 테스트(A)는 이 fixture 대신 client 로 실제 가입·로그인을 거친다.
    users 테이블에 이 사용자 행은 없으므로, user_id 외래키가 걸린 행을 저장하는 테스트는
    EE-03 이후 사용자를 먼저 만들어야 한다.
    """
    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_optional_user] = lambda: current_user
    app.dependency_overrides[require_csrf] = lambda: None
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()

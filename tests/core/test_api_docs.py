"""운영 서버에서는 API 문서(/docs)를 열지 않는다. (L, EE-24)"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

DOC_PATHS = ["/docs", "/redoc", "/openapi.json"]


@pytest.mark.parametrize("path", DOC_PATHS)
def test_api_docs_are_open_outside_production(client, path):
    assert client.get(path).status_code == 200


@pytest.mark.parametrize("path", DOC_PATHS)
def test_api_docs_are_hidden_in_production(tmp_path, path):
    settings = Settings(
        _env_file=None,
        app_env="production",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        ai_provider="anthropic",
        anthropic_api_key="dummy-key-for-test",
        cookie_secure=True,
    )
    client = TestClient(create_app(settings), raise_server_exceptions=False)

    assert client.get(path).status_code == 404

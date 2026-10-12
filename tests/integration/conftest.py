"""통합 테스트 공통 도구. (L 담당, EE-18)

영역별 테스트는 `logged_in_client` 로 로그인을 건너뛰지만, 통합 테스트는 실제로
가입 → 로그인 → 세션 쿠키 → CSRF 토큰을 거친다. AI 는 항상 가짜(fake)다.
"""

from dataclasses import dataclass
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

PASSWORD = "integration-pass-1"


@dataclass
class LoggedInUser:
    """실제로 로그인한 사용자 한 명. 쿠키는 client 가, CSRF 토큰은 여기서 들고 있다."""

    client: TestClient
    email: str
    password: str
    csrf_token: str

    def post(self, path: str, **kwargs):
        headers = {"X-CSRF-Token": self.csrf_token, **kwargs.pop("headers", {})}
        return self.client.post(path, headers=headers, **kwargs)

    def ask(self, conversation_id: str, question: str, level: str = "easy"):
        return self.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "question": question,
                "level": level,
                "client_request_id": str(uuid4()),
            },
        )


def sign_up_and_log_in(client: TestClient, settings, email: str) -> LoggedInUser:
    origin = {"Origin": settings.site_origin}
    body = {"email": email, "password": PASSWORD}

    assert client.post("/api/auth/signup", headers=origin, json=body).status_code == 201
    login = client.post("/api/auth/login", headers=origin, json=body)
    assert login.status_code == 200
    assert "session" in login.cookies
    return LoggedInUser(
        client=client, email=email, password=PASSWORD, csrf_token=login.json()["csrf_token"]
    )


@pytest.fixture
def user(client, settings) -> LoggedInUser:
    return sign_up_and_log_in(client, settings, "alice@example.com")


@pytest.fixture
def other_user(app, settings):
    # 쿠키가 섞이지 않도록 다른 사람은 별도 client 로 로그인한다.
    with TestClient(app, raise_server_exceptions=False) as other_client:
        yield sign_up_and_log_in(other_client, settings, "bob@example.com")

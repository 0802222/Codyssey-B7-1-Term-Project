from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def create_test_app(tmp_path: Path):
    database_url = f"sqlite:///{tmp_path / 'test.db'}"

    settings = Settings(
        database_url=database_url,
    )

    return create_app(settings)


def test_signup_success(tmp_path):
    app = create_test_app(tmp_path)

    with TestClient(app) as client:
        response = client.post(
            "/api/auth/signup",
            json={
                "email": "test@example.com",
                "password": "1234567890",
            },
        )

    assert response.status_code == 201
    assert response.json()["email"] == "test@example.com"
    assert "password" not in response.json()
    assert "password_hash" not in response.json()


def test_signup_duplicate_email(tmp_path):
    app = create_test_app(tmp_path)

    with TestClient(app) as client:
        data = {
            "email": "test@example.com",
            "password": "1234567890",
        }

        first_response = client.post("/api/auth/signup", json=data)
        second_response = client.post("/api/auth/signup", json=data)

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["error"]["code"] == "ACCOUNT_EXISTS"


def test_signup_invalid_email(tmp_path):
    app = create_test_app(tmp_path)

    with TestClient(app) as client:
        response = client.post(
            "/api/auth/signup",
            json={
                "email": "invalid-email",
                "password": "1234567890",
            },
        )

    assert response.status_code == 422


def test_signup_password_too_short(tmp_path):
    app = create_test_app(tmp_path)

    with TestClient(app) as client:
        response = client.post(
            "/api/auth/signup",
            json={
                "email": "test@example.com",
                "password": "123456789",
            },
        )

    assert response.status_code == 422


def test_signup_password_too_long(tmp_path):
    app = create_test_app(tmp_path)

    with TestClient(app) as client:
        response = client.post(
            "/api/auth/signup",
            json={
                "email": "test@example.com",
                "password": "a" * 129,
            },
        )

    assert response.status_code == 422


def test_signup_email_is_normalized(tmp_path):
    app = create_test_app(tmp_path)

    with TestClient(app) as client:
        response = client.post(
            "/api/auth/signup",
            json={
                "email": "  TEST@EXAMPLE.COM  ",
                "password": "1234567890",
            },
        )

    assert response.status_code == 201
    assert response.json()["email"] == "test@example.com"
    
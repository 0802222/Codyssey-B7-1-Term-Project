import sqlite3
from unittest.mock import MagicMock

from pwdlib import PasswordHash
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, create_engine, select

from app.db.models import User
from app.db.session import get_session


def test_signup_success(client, settings):
    response = client.post(
        "/api/auth/signup",
        headers={"Origin": settings.site_origin},
        json={
            "email": "test@example.com",
            "password": "1234567890",
        },
    )

    assert response.status_code == 201
    assert response.json()["email"] == "test@example.com"
    assert "password" not in response.json()
    assert "password_hash" not in response.json()


def test_signup_duplicate_email(client, settings):
    data = {
        "email": "test@example.com",
        "password": "1234567890",
    }
    headers = {"Origin": settings.site_origin}

    first_response = client.post(
        "/api/auth/signup",
        headers=headers,
        json=data,
    )
    second_response = client.post(
        "/api/auth/signup",
        headers=headers,
        json=data,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["error"]["code"] == "ACCOUNT_EXISTS"


def test_signup_invalid_email(client, settings):
    response = client.post(
        "/api/auth/signup",
        headers={"Origin": settings.site_origin},
        json={
            "email": "invalid-email",
            "password": "1234567890",
        },
    )

    assert response.status_code == 422


def test_signup_email_with_empty_domain_section(client, settings):
    response = client.post(
        "/api/auth/signup",
        headers={"Origin": settings.site_origin},
        json={
            "email": "user@example..com",
            "password": "1234567890",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    engine = create_engine(settings.database_url)

    with Session(engine) as session:
        user = session.exec(
            select(User).where(User.email == "user@example..com")
        ).first()

    assert user is None


def test_signup_rejects_other_origin(client, settings):
    response = client.post(
        "/api/auth/signup",
        headers={"Origin": "https://attacker.invalid"},
        json={
            "email": "attacker@example.com",
            "password": "1234567890",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_REJECTED"

    engine = create_engine(settings.database_url)

    with Session(engine) as session:
        user = session.exec(
            select(User).where(User.email == "attacker@example.com")
        ).first()

    assert user is None


def test_signup_password_too_short(client, settings):
    response = client.post(
        "/api/auth/signup",
        headers={"Origin": settings.site_origin},
        json={
            "email": "test@example.com",
            "password": "1234567",
        },
    )

    assert response.status_code == 422


def test_signup_password_too_long(client, settings):
    response = client.post(
        "/api/auth/signup",
        headers={"Origin": settings.site_origin},
        json={
            "email": "test@example.com",
            "password": "a" * 65,
        },
    )

    assert response.status_code == 422


def test_signup_password_length_boundaries_are_accepted(client, settings):
    for email, password in [
        ("min-length@example.com", "a" * 8),
        ("max-length@example.com", "a" * 64),
    ]:
        response = client.post(
            "/api/auth/signup",
            headers={"Origin": settings.site_origin},
            json={
                "email": email,
                "password": password,
            },
        )

        assert response.status_code == 201


def test_signup_rejects_non_english_password(client, settings):
    for password in ["비밀번호12345678", "password🙂12", "pässword12"]:
        response = client.post(
            "/api/auth/signup",
            headers={"Origin": settings.site_origin},
            json={
                "email": "test@example.com",
                "password": password,
            },
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_signup_keeps_spaces_and_symbols_in_password(client, settings):
    password = " p@ss w0rd! "

    response = client.post(
        "/api/auth/signup",
        headers={"Origin": settings.site_origin},
        json={
            "email": "space@example.com",
            "password": password,
        },
    )

    assert response.status_code == 201

    engine = create_engine(settings.database_url)

    with Session(engine) as session:
        user = session.exec(
            select(User).where(User.email == "space@example.com")
        ).first()

    assert user is not None
    assert PasswordHash.recommended().verify(password, user.password_hash)
    assert not PasswordHash.recommended().verify(password.strip(), user.password_hash)


def test_signup_email_length_boundary(client, settings):
    domain = "@example.com"
    email_100 = "a" * (100 - len(domain)) + domain
    email_101 = "b" * (101 - len(domain)) + domain

    accepted = client.post(
        "/api/auth/signup",
        headers={"Origin": settings.site_origin},
        json={
            "email": email_100,
            "password": "1234567890",
        },
    )
    rejected = client.post(
        "/api/auth/signup",
        headers={"Origin": settings.site_origin},
        json={
            "email": email_101,
            "password": "1234567890",
        },
    )

    assert accepted.status_code == 201
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "VALIDATION_ERROR"


def test_signup_email_is_normalized(client, settings):
    response = client.post(
        "/api/auth/signup",
        headers={"Origin": settings.site_origin},
        json={
            "email": "  TEST@EXAMPLE.COM  ",
            "password": "1234567890",
        },
    )

    assert response.status_code == 201
    assert response.json()["email"] == "test@example.com"


def test_signup_password_is_stored_as_argon2_hash(client, settings):
    password = "1234567890"

    response = client.post(
        "/api/auth/signup",
        headers={"Origin": settings.site_origin},
        json={
            "email": "hash-test@example.com",
            "password": password,
        },
    )

    assert response.status_code == 201

    engine = create_engine(settings.database_url)

    with Session(engine) as session:
        user = session.exec(
            select(User).where(User.email == "hash-test@example.com")
        ).first()

    assert user is not None
    assert user.password_hash != password
    assert user.password_hash.startswith("$argon2")
    assert PasswordHash.recommended().verify(password, user.password_hash)


def test_signup_db_query_error(client, app, settings):
    session = MagicMock()
    session.exec.side_effect = SQLAlchemyError("database error")

    app.dependency_overrides[get_session] = lambda: session

    try:
        response = client.post(
            "/api/auth/signup",
            headers={"Origin": settings.site_origin},
            json={
                "email": "query-error@example.com",
                "password": "1234567890",
            },
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DB_ERROR"
    session.rollback.assert_called_once()


def test_signup_db_commit_error(client, app, settings):
    session = MagicMock()
    session.exec.return_value.first.return_value = None
    session.commit.side_effect = SQLAlchemyError("database error")

    app.dependency_overrides[get_session] = lambda: session

    try:
        response = client.post(
            "/api/auth/signup",
            headers={"Origin": settings.site_origin},
            json={
                "email": "commit-error@example.com",
                "password": "1234567890",
            },
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DB_ERROR"
    session.rollback.assert_called_once()


def test_signup_db_refresh_error(client, app, settings):
    session = MagicMock()
    session.exec.return_value.first.return_value = None
    session.refresh.side_effect = SQLAlchemyError("database error")

    app.dependency_overrides[get_session] = lambda: session

    try:
        response = client.post(
            "/api/auth/signup",
            headers={"Origin": settings.site_origin},
            json={
                "email": "refresh-error@example.com",
                "password": "1234567890",
            },
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DB_ERROR"
    session.rollback.assert_called_once()


def test_signup_locked_database_returns_db_error(client, settings):
    engine = create_engine(settings.database_url)
    database_path = engine.url.database
    lock_connection = sqlite3.connect(database_path, timeout=0)

    try:
        lock_cursor = lock_connection.cursor()
        lock_cursor.execute("BEGIN EXCLUSIVE")

        response = client.post(
            "/api/auth/signup",
            headers={"Origin": settings.site_origin},
            json={
                "email": "locked@example.com",
                "password": "1234567890",
            },
        )
    finally:
        lock_connection.rollback()
        lock_connection.close()

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DB_ERROR"
    
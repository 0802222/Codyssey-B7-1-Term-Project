from datetime import UTC, datetime, timedelta

from sqlmodel import Session, create_engine, select

from app.db.models import AuthSession, User


def _signup(client, settings, email="test@example.com"):
    return client.post(
        "/api/auth/signup",
        headers={"Origin": settings.site_origin},
        json={
            "email": email,
            "password": "1234567890",
        },
    )


def _login(client, settings, email="test@example.com"):
    return client.post(
        "/api/auth/login",
        headers={"Origin": settings.site_origin},
        json={
            "email": email,
            "password": "1234567890",
        },
    )


def test_login_success(client, settings):
    _signup(client, settings)

    response = _login(client, settings)

    assert response.status_code == 200

    data = response.json()

    assert data["user"]["email"] == "test@example.com"
    assert data["csrf_token"]
    assert "session" in response.cookies

    engine = create_engine(settings.database_url)

    with Session(engine) as session:
        user = session.exec(
            select(User).where(User.email == "test@example.com")
        ).first()

        auth_session = session.exec(
            select(AuthSession).where(
                AuthSession.user_id == user.id
            )
        ).first()

    assert user is not None
    assert auth_session is not None
    assert auth_session.token_hash != response.cookies["session"]
    assert auth_session.csrf_token == data["csrf_token"]


def test_login_wrong_password(client, settings):
    _signup(client, settings)

    response = client.post(
        "/api/auth/login",
        headers={"Origin": settings.site_origin},
        json={
            "email": "test@example.com",
            "password": "wrongpassword",
        },
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_nonexistent_email(client, settings):
    response = client.post(
        "/api/auth/login",
        headers={"Origin": settings.site_origin},
        json={
            "email": "not-found@example.com",
            "password": "1234567890",
        },
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_rejects_other_origin(client, settings):
    _signup(client, settings)

    response = client.post(
        "/api/auth/login",
        headers={"Origin": "https://attacker.invalid"},
        json={
            "email": "test@example.com",
            "password": "1234567890",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_REJECTED"


def test_login_email_is_normalized(client, settings):
    _signup(client, settings)

    response = client.post(
        "/api/auth/login",
        headers={"Origin": settings.site_origin},
        json={
            "email": "  TEST@EXAMPLE.COM  ",
            "password": "1234567890",
        },
    )

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "test@example.com"


def test_login_rejects_invalid_password_length(client, settings):
    _signup(client, settings)

    response = client.post(
        "/api/auth/login",
        headers={"Origin": settings.site_origin},
        json={
            "email": "test@example.com",
            "password": "1234567",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_login_rejects_too_long_password(client, settings):
    _signup(client, settings)

    response = client.post(
        "/api/auth/login",
        headers={"Origin": settings.site_origin},
        json={
            "email": "test@example.com",
            "password": "a" * 65,
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_login_rejects_too_long_email(client, settings):
    response = client.post(
        "/api/auth/login",
        headers={"Origin": settings.site_origin},
        json={
            "email": ("a" * 89) + "@example.com",
            "password": "1234567890",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_login_accepts_8_char_password(client, settings):
    client.post(
        "/api/auth/signup",
        headers={"Origin": settings.site_origin},
        json={
            "email": "short@example.com",
            "password": "abcd1234",
        },
    )

    response = client.post(
        "/api/auth/login",
        headers={"Origin": settings.site_origin},
        json={
            "email": "short@example.com",
            "password": "abcd1234",
        },
    )

    assert response.status_code == 200


def test_login_rejects_non_english_password(client, settings):
    _signup(client, settings)

    response = client.post(
        "/api/auth/login",
        headers={"Origin": settings.site_origin},
        json={
            "email": "test@example.com",
            "password": "비밀번호1234",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_me_success(client, settings):
    _signup(client, settings)
    login_response = _login(client, settings)

    csrf_token = login_response.json()["csrf_token"]

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json() == {
        "user": {
            "id": 1,
            "email": "test@example.com",
        },
        "csrf_token": csrf_token,
    }


def test_me_without_login(client):
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_expired_session_returns_auth_required(client, settings):
    _signup(client, settings)
    _login(client, settings)

    engine = create_engine(settings.database_url)

    with Session(engine) as session:
        auth_session = session.exec(
            select(AuthSession)
        ).first()

        auth_session.expires_at = (
            datetime.now(UTC) - timedelta(seconds=1)
        )
        session.add(auth_session)
        session.commit()

    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_logout_success(client, settings):
    _signup(client, settings)
    login_response = _login(client, settings)

    csrf_token = login_response.json()["csrf_token"]

    response = client.post(
        "/api/auth/logout",
        headers={
            "X-CSRF-Token": csrf_token,
        },
    )

    assert response.status_code == 204

    engine = create_engine(settings.database_url)

    with Session(engine) as session:
        auth_session = session.exec(
            select(AuthSession)
        ).first()

    assert auth_session is None


def test_logout_blocks_access_after_logout(client, settings):
    _signup(client, settings)
    login_response = _login(client, settings)

    csrf_token = login_response.json()["csrf_token"]

    response = client.post(
        "/api/auth/logout",
        headers={
            "X-CSRF-Token": csrf_token,
        },
    )

    assert response.status_code == 204

    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_logout_without_csrf(client, settings):
    _signup(client, settings)
    _login(client, settings)

    response = client.post("/api/auth/logout")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_REJECTED"


def test_logout_with_wrong_csrf(client, settings):
    _signup(client, settings)
    _login(client, settings)

    response = client.post(
        "/api/auth/logout",
        headers={
            "X-CSRF-Token": "wrong-token",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_REJECTED"


def test_login_cookie_attributes(client, settings):
    _signup(client, settings)

    response = _login(client, settings)

    assert response.status_code == 200

    set_cookie = response.headers["set-cookie"]

    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert ("Secure" in set_cookie) == settings.cookie_secure


def test_login_session_ttl(client, settings):
    _signup(client, settings)

    response = _login(client, settings)

    assert response.status_code == 200

    engine = create_engine(settings.database_url)

    with Session(engine) as session:
        auth_session = session.exec(
            select(AuthSession)
        ).first()

    assert auth_session is not None

    now = datetime.now(UTC)

    expected_min = now + timedelta(
        seconds=settings.session_ttl_seconds - 2
    )
    expected_max = now + timedelta(
        seconds=settings.session_ttl_seconds + 2
    )

    assert expected_min <= auth_session.expires_at <= expected_max


def test_login_does_not_read_user_after_commit(
    client,
    settings,
    monkeypatch,
):
    _signup(client, settings)

    original_commit = Session.commit
    original_execute = Session.execute

    state = {
        "committed": False,
        "user_selects_after_commit": 0,
    }

    def track_commit(self):
        original_commit(self)
        state["committed"] = True

    def track_execute(self, statement, *args, **kwargs):
        if state["committed"] and hasattr(statement, "get_final_froms"):
            if User.__table__ in statement.get_final_froms():
                state["user_selects_after_commit"] += 1

        return original_execute(self, statement, *args, **kwargs)

    monkeypatch.setattr(Session, "commit", track_commit)
    monkeypatch.setattr(Session, "execute", track_execute)

    response = _login(client, settings)

    assert response.status_code == 200
    assert response.json()["user"] == {
        "id": 1,
        "email": "test@example.com",
    }
    assert state["user_selects_after_commit"] == 0

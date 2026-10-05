import pytest

from app.core.errors import AppError, ErrorCode


def assert_error(response, status_code: int, code: str) -> dict:
    assert response.status_code == status_code
    error = response.json()["error"]
    assert error["code"] == code
    assert error["message"]
    assert error["request_id"] == response.headers["X-Request-ID"]
    return error


def test_unknown_path_returns_404_in_common_format(client):
    assert_error(client.get("/no-such-path"), 404, "NOT_FOUND")


def test_wrong_method_returns_405(client):
    assert_error(client.delete("/health"), 405, "METHOD_NOT_ALLOWED")


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/auth/signup"),
        ("post", "/api/auth/login"),
        ("get", "/api/me/conversations"),
        ("get", "/api/me/chats"),
        ("post", "/api/chat"),
        ("get", "/"),
    ],
)
def test_unimplemented_routes_do_not_fake_success(client, method, path):
    assert_error(getattr(client, method)(path), 501, "NOT_IMPLEMENTED")


def test_validation_error_uses_common_format(app, client):
    @app.get("/_test/validate")
    def validate(n: int):
        return {"n": n}

    assert_error(client.get("/_test/validate?n=abc"), 422, "VALIDATION_ERROR")


def test_app_error_uses_given_status_and_code(app, client):
    @app.get("/_test/app-error")
    def app_error():
        raise AppError(504, ErrorCode.AI_TIMEOUT, "응답이 지연되고 있어요.")

    error = assert_error(client.get("/_test/app-error"), 504, "AI_TIMEOUT")
    assert error["message"] == "응답이 지연되고 있어요."


def test_unexpected_error_hides_internal_details(app, client):
    @app.get("/_test/boom")
    def boom():
        raise RuntimeError("secret internal detail")

    response = client.get("/_test/boom")

    assert_error(response, 500, "INTERNAL_ERROR")
    assert "secret internal detail" not in response.text

"""화면의 입력 규칙(AUTH_INPUT_RULES)이 서버 검사와 같은지 확인한다. (C 담당, EE-09)

화면이 받는 끝값은 서버도 받고, 화면이 막는 값은 서버도 막아야 한다. 둘이 어긋나면 화면 안내대로
입력했는데 서버가 "입력값을 확인해 주세요." 로 거절하거나, 화면이 막는 값을 서버는 받게 된다.
규칙 값을 바꿀 때 화면(app/web/router.py)과 서버(app/auth/router.py) 중 한쪽만 고치면
여기서 실패한다.
"""

import pytest

from app.web.router import AUTH_INPUT_RULES as RULES

DOMAIN = "@example.com"


def email_of_length(length: int) -> str:
    return "a" * (length - len(DOMAIN)) + DOMAIN


def post(client, settings, path: str, email: str, password: str):
    return client.post(
        path,
        headers={"Origin": settings.site_origin},
        json={"email": email, "password": password},
    )


@pytest.mark.parametrize(
    ("email", "password"),
    [
        (email_of_length(RULES.email_max_length), "a" * RULES.password_min_length),
        ("max-password@example.com", "b" * RULES.password_max_length),
    ],
)
def test_server_accepts_what_the_page_allows(client, settings, email, password):
    signup = post(client, settings, "/api/auth/signup", email, password)
    login = post(client, settings, "/api/auth/login", email, password)

    assert signup.status_code == 201
    assert login.status_code == 200


@pytest.mark.parametrize("path", ["/api/auth/signup", "/api/auth/login"])
@pytest.mark.parametrize(
    ("email", "password"),
    [
        (email_of_length(RULES.email_max_length + 1), "a" * RULES.password_min_length),
        ("short@example.com", "a" * (RULES.password_min_length - 1)),
        ("long@example.com", "a" * (RULES.password_max_length + 1)),
    ],
)
def test_server_rejects_what_the_page_blocks(client, settings, path, email, password):
    response = post(client, settings, path, email, password)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_server_treats_non_english_password_like_the_page(client, settings):
    # 길이는 맞고 글자 종류만 다른 비밀번호. 화면이 영어만 받으면 서버도 막고, 아니면 서버도 받는다
    password = "가" + "a" * (RULES.password_min_length - 1)

    response = post(client, settings, "/api/auth/signup", "korean@example.com", password)

    assert response.status_code == (422 if RULES.password_ascii_only else 201)

"""헤더 메뉴가 로그인 상태를 따르는지 테스트. (C 담당, EE-12)

모든 페이지 라우터가 OptionalUserDep 로 로그인 여부를 받아 base.html 에 logged_in 으로 넘긴다.
로그인하지 않았으면 "로그인" 링크, 로그인했으면 그 자리에 "로그아웃" 버튼이 보여야 한다.
(로그아웃 버튼을 눌렀을 때의 동작은 EE-14)
"""

from html.parser import HTMLParser

import pytest

PUBLIC_PAGES = ["/", "/signup", "/login"]
LOGGED_IN_PAGES = [*PUBLIC_PAGES, "/chat"]


class _NavItems(HTMLParser):
    """<nav class="site-nav"> 바로 안의 링크·버튼을 (태그, 속성, 글자) 로 모은다."""

    def __init__(self) -> None:
        super().__init__()
        self.in_nav = False
        self.current: list | None = None
        self.items: list[tuple[str, dict[str, str | None], str]] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "nav" and attrs.get("class") == "site-nav":
            self.in_nav = True
        elif self.in_nav and tag in ("a", "button"):
            self.current = [tag, attrs, ""]

    def handle_data(self, data):
        if self.current is not None:
            self.current[2] += data

    def handle_endtag(self, tag):
        if tag == "nav":
            self.in_nav = False
        elif self.current is not None and tag == self.current[0]:
            tag_name, attrs, text = self.current
            self.items.append((tag_name, attrs, text.strip()))
            self.current = None


def nav_items(html: str) -> list[tuple[str, dict[str, str | None], str]]:
    parser = _NavItems()
    parser.feed(html)
    return parser.items


def labels(html: str) -> list[str]:
    return [f"{tag}:{text}" for tag, _, text in nav_items(html)]


@pytest.mark.parametrize("path", PUBLIC_PAGES)
def test_logged_out_header_shows_login_link(client, path):
    html = client.get(path).text

    assert labels(html) == ["a:채팅", "a:내 기록", "a:로그인"]
    assert 'id="logout-button"' not in html


@pytest.mark.parametrize("path", LOGGED_IN_PAGES)
def test_logged_in_header_shows_logout_button_instead_of_login(logged_in_client, path):
    html = logged_in_client.get(path).text

    assert labels(html) == ["a:채팅", "a:내 기록", "button:로그아웃"]
    logout = nav_items(html)[2][1]
    assert logout["id"] == "logout-button"  # EE-14 의 스크립트가 이 id 로 찾는다
    assert logout["type"] == "button"  # 폼 안에 들어가도 제출 버튼이 되지 않게


def test_header_follows_real_login_session(client, settings):
    # 의존성을 바꿔 끼우지 않고, A 의 실제 가입·로그인 API 로 받은 세션 쿠키로 확인한다
    account = {"email": "header@example.com", "password": "1234567890"}
    headers = {"Origin": settings.site_origin}
    assert client.post("/api/auth/signup", headers=headers, json=account).status_code == 201
    assert labels(client.get("/").text)[-1] == "a:로그인"  # 가입만으로는 로그인되지 않는다

    assert client.post("/api/auth/login", headers=headers, json=account).status_code == 200

    assert labels(client.get("/").text)[-1] == "button:로그아웃"
    assert labels(client.get("/chat").text)[-1] == "button:로그아웃"

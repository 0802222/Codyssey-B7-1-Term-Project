"""소개 페이지(/)와 공통 틀·정적 파일 테스트. (C 담당, EE-04)"""

import pytest

MENU = [("/chat", "채팅"), ("/history", "내 기록"), ("/login", "로그인")]


def hero_actions(html: str) -> str:
    """첫 화면 본문의 버튼 묶음(<div class="hero-actions">) HTML 만 잘라 낸다.

    헤더 메뉴에도 /chat·/history·/login 링크가 있으므로, 섞이지 않게 본문 버튼만 본다.
    """
    start = html.index('<div class="hero-actions">')
    return html[start : html.index("</div>", start)]


def test_index_returns_html(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_index_has_common_frame(client):
    html = client.get("/").text

    assert "EasyExplain" in html
    for href, label in MENU:
        assert f'href="{href}"' in html
        assert label in html
    assert "AI 설명은 틀릴 수 있어요" in html


def test_index_shows_three_levels(client):
    html = client.get("/").text

    for level in ("아주 쉽게", "입문자", "전공자"):
        assert level in html


def test_index_links_signup_and_login(client):
    actions = hero_actions(client.get("/").text)

    assert 'href="/signup"' in actions
    assert 'href="/login"' in actions


def test_logged_in_index_links_chat_and_history_instead(logged_in_client):
    # 로그인했는데 [시작하기]·[로그인]을 보여 주면 로그인한 채 로그인 화면에 다시 들어가게 된다
    actions = hero_actions(logged_in_client.get("/").text)

    assert 'href="/chat"' in actions
    assert "채팅 시작하기" in actions
    assert 'href="/history"' in actions
    assert 'href="/signup"' not in actions
    assert 'href="/login"' not in actions


def test_index_links_stylesheet_and_it_is_served(client):
    assert 'href="/static/css/style.css"' in client.get("/").text

    response = client.get("/static/css/style.css")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")


def test_mascot_image_is_served(client):
    response = client.get("/static/img/mascot.svg")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")


@pytest.mark.parametrize("path", ["/", "/login", "/signup"])
def test_pages_have_description_and_open_graph(client, path):
    html = client.get(path).text

    assert '<meta name="description" content="' in html
    for prop in ("og:type", "og:site_name", "og:title", "og:description", "og:locale"):
        assert f'<meta property="{prop}" content="' in html

"""소개 페이지(/)와 공통 틀·정적 파일 테스트. (C 담당, EE-04)"""

MENU = [("/chat", "채팅"), ("/history", "내 기록"), ("/login", "로그인")]


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
    html = client.get("/").text

    assert 'href="/signup"' in html
    assert 'href="/login"' in html


def test_index_links_stylesheet_and_it_is_served(client):
    assert 'href="/static/css/style.css"' in client.get("/").text

    response = client.get("/static/css/style.css")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")


def test_mascot_image_is_served(client):
    response = client.get("/static/img/mascot.svg")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")

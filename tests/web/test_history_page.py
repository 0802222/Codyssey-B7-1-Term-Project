"""내 기록 화면(/history) 테스트. (C 담당, EE-17)

HTML 은 test_chat_page.py 의 HTMLParser 도우미로 태그·속성·글자를 읽어 검사한다.
"""


# ── 접근 (이슈 #24 완료 조건: 비로그인 303, 로그인 200) ──


def test_history_redirects_to_login_when_logged_out(client):
    response = client.get("/history", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_history_detail_address_also_redirects_when_logged_out(client):
    response = client.get(
        "/history?conversation=9b1c4da5-7a74-4f97-88cb-1b2790e510a9", follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_history_returns_html_when_logged_in(logged_in_client):
    response = logged_in_client.get("/history")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")

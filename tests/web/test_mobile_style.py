"""모든 페이지의 휴대폰 화면 스타일 테스트. (C 담당, EE-17)

배포 주소를 휴대폰 폭(375·320px)으로 보고 고친 두 가지가 그대로인지 CSS 를 읽어 확인한다.
실제 화면(가로 넘침·누르는 곳 크기·낱말 중간 줄바꿈)은 헤드리스 Chrome 으로 따로 쟀다.
"""

from pathlib import Path

CSS = (Path(__file__).parents[2] / "app" / "static" / "css" / "style.css").read_text(
    encoding="utf-8"
)


def rule(selector: str) -> str:
    """`selector {` 로 시작하는 첫 규칙의 선언들"""
    begin = CSS.index(f"\n{selector} {{") + len(selector) + 3
    return CSS[begin : CSS.index("}", begin)]


def test_korean_text_breaks_only_between_words():
    # 브라우저 기본은 한글 글자 사이 어디서나 줄을 바꿔 "결/과를"·"주세/요." 처럼 갈라진다
    body = rule("body")

    assert "word-break: keep-all;" in body
    assert "overflow-wrap: break-word;" in body  # 띄어쓰기 없이 긴 글은 넘치지 않게


def test_header_menu_and_logo_are_44px_to_tap():
    # 메뉴 항목·로그아웃 버튼·로고 — 다른 버튼(.btn)과 같은 손가락으로 누르기 편한 크기
    menu = rule(".site-nav a,\n.site-nav button")

    assert "min-height: 44px;" in menu
    assert "align-items: center;" in menu  # 커진 높이 안에서 글자는 가운데
    assert "min-height: 44px;" in rule(".logo")
    assert "min-height: 44px;" in rule(".btn")


def test_signup_login_switch_link_is_44px_to_tap():
    # 글자 높이(0.875rem × 1.6 = 22.4px) + 위아래 11px = 44.4px,
    # 좌우 4px 로 짧은 "로그인" 도 44px 폭
    assert "padding: 11px 4px;" in rule(".auth-switch a")

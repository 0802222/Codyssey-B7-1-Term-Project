"""글자·배경 색 대비 테스트. (C 담당, EE-21)

style.css 맨 위 :root 의 색 값을 읽어, 화면에 실제로 함께 쓰이는 글자색·바탕색 조합의 대비를
WCAG 2.x 식(상대 휘도)으로 계산한다. 기준은 WCAG AA — 보통 글자 4.5:1, 큰 글자(24px 이상)와
구성 요소의 경계·포커스 테두리 3:1. 색 값을 바꿔 기준 아래로 내려가면 실패한다.
조합 목록은 헤드리스 Chrome 으로 화면마다 보이는 모든 글자의 실제 색을 재서 만든 것이다
(tests/web/README.md 의 대비 표). 새 색을 글자에 쓰면 아래 목록에도 넣어야 통과한다.
"""

import re
from pathlib import Path

import pytest

CSS = (Path(__file__).parents[2] / "app" / "static" / "css" / "style.css").read_text(
    encoding="utf-8"
)
ROOT = CSS[CSS.index(":root {") : CSS.index("}", CSS.index(":root {"))]
TOKENS = dict(re.findall(r"--([a-z-]+): (#[0-9A-Fa-f]{6});", ROOT))

TEXT = 4.5  # 보통 글자
LARGE = 3.0  # 큰 글자 (24px 이상)
UI = 3.0  # 구성 요소의 경계·포커스 테두리

# (글자 또는 테두리 색, 바탕색, 기준, 쓰는 곳)
PAIRS = [
    ("text", "bg", TEXT, "본문 글자 — 채팅 첫 안내, 내 기록 제목, 소개의 특징"),
    ("text", "surface", TEXT, "흰 바탕 글자 — 로고, 가입·로그인 카드, 답변 말풍선, 기록 카드 제목"),
    ("text", "accent-soft", TEXT, "마우스를 올린 보조 버튼·기록 카드"),
    ("text", "level-easy", TEXT, "소개의 수준 카드 설명 (아주 쉽게)"),
    ("text", "level-beginner", TEXT, "소개의 수준 카드 설명 (입문자)"),
    ("text", "level-advanced", TEXT, "소개의 수준 카드 설명 (전공자)"),
    ("text", "highlight", LARGE, "소개 큰 제목(44px)의 형광펜 부분"),
    ("text-muted", "bg", TEXT, "보조 글자 — 소개 문구, 기록 안내, 말풍선 아래 수준·시각"),
    ("text-muted", "surface", TEXT, "흰 바탕 보조 글자 — 메뉴, 푸터, 입력칸 안내·자리 표시"),
    ("text-muted", "accent-soft", TEXT, "마우스를 올린 기록 카드의 시각"),
    ("text-muted", "line", TEXT, "잠긴 버튼·후속 버튼 (WCAG 예외지만 읽히게 4.5:1 이상)"),
    ("accent-text", "bg", TEXT, "소개의 작은 제목 (AI 개념 설명 챗봇)"),
    ("accent-text", "surface", TEXT, "수준 이름표, 후속 버튼, 가입·로그인 전환 링크"),
    ("accent-text", "accent-soft", TEXT, "메뉴의 지금 위치, 가입 직후·로그인 풀림 안내"),
    ("on-accent", "accent", TEXT, "주요 버튼, 내 질문 말풍선, 고른 수준, 건너뛰기 링크"),
    ("on-accent", "accent-hover", TEXT, "마우스를 올린 주요 버튼"),
    ("error-text", "error-bg", TEXT, "오류 안내와 다시 보내기 버튼"),
    ("error-text", "surface", TEXT, "마우스를 올린 다시 보내기 버튼"),
    ("line-strong", "surface", UI, "입력칸·질문 상자·보조 버튼 테두리"),
    ("line-strong", "bg", UI, "질문 상자·접힌 실패 묶음 테두리 (연보라 바탕 위)"),
    ("accent", "bg", UI, "포커스 테두리 (연보라 바탕)"),
    ("accent", "surface", UI, "포커스 테두리 (흰 헤더·카드), 고른 수준과 고르지 않은 수준의 차이"),
    ("accent", "error-bg", UI, "오류 칸 안 다시 보내기 버튼의 포커스 테두리"),
]

# 테두리에 쓰지만 대비 기준이 없는 색: 글자가 이름인 버튼·카드의 옅은 테두리와 구분선(--line),
# 기록 카드 오른쪽 꺾쇠 꾸밈(--text-muted). 알아보는 데 필요한 것은 글자다
DECORATIVE_BORDERS = {"line", "text-muted"}


def luminance(hex_color: str) -> float:
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(foreground: str, background: str) -> float:
    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def test_contrast_formula_matches_wcag_examples():
    assert contrast("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert contrast("#777777", "#FFFFFF") == pytest.approx(4.48, abs=0.01)  # 기준에 조금 못 미침
    assert contrast("#FFFFFF", "#FFFFFF") == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("foreground", "background", "minimum", "where"),
    PAIRS,
    ids=[f"{f}/{b}" for f, b, _, _ in PAIRS],
)
def test_colour_pair_meets_wcag_aa(foreground, background, minimum, where):
    ratio = contrast(TOKENS[foreground], TOKENS[background])
    assert ratio >= minimum, (
        f"{where}: --{foreground} {TOKENS[foreground]} / --{background} {TOKENS[background]}"
        f" = {ratio:.2f}:1 (기준 {minimum}:1)"
    )


def test_every_text_colour_used_in_css_is_checked():
    used = set(re.findall(r"(?<![-\w])color: var\(--([a-z-]+)\)", CSS))
    checked = {f for f, _, minimum, _ in PAIRS if minimum != UI}
    assert used <= checked, f"대비를 확인하지 않은 글자색: {used - checked}"


def test_every_background_colour_used_in_css_is_checked():
    used = set(re.findall(r"background(?:-color)?: var\(--([a-z-]+)\)", CSS))
    checked = {b for _, b, _, _ in PAIRS}
    assert used <= checked, f"대비를 확인하지 않은 바탕색: {used - checked}"


def test_every_border_and_outline_colour_is_checked_or_decorative():
    pattern = r"(?:border(?:-[a-z]+)*|outline(?:-color)?): [^;]*var\(--([a-z-]+)\)"
    used = set(re.findall(pattern, CSS))
    used -= {name for name in used if name.startswith("radius")}  # 모서리 값
    checked = {f for f, _, minimum, _ in PAIRS if minimum == UI}
    assert used <= checked | DECORATIVE_BORDERS, f"대비를 확인하지 않은 테두리 색: {used - checked}"

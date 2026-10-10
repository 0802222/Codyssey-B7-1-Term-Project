"""모든 화면의 접근성 구조 테스트. (C 담당, EE-21)

키보드·스크린리더로 쓸 수 있게 화면마다 지켜야 할 뼈대를 HTML 로 확인한다 — 언어(lang),
문서 제목, 제목(h1~h3) 순서, 랜드마크(header·nav·main·footer), 본문으로 건너뛰기 링크,
입력칸 이름(label), aria 참조, 중복 id, 그림 대체 텍스트, 버튼·링크 이름, 오류·상태 칸의 역할.
HTML 은 다른 화면 테스트처럼 표준 라이브러리 HTMLParser 로 읽는다. 스크립트가 나중에 붙이는
요소(말풍선·목록 항목)와 실제 Tab 순서·포커스 테두리·글자 대비는 헤드리스 Chrome 으로 따로 쟀다
(tests/web/README.md 의 화면 검증 기록). 글자 대비 계산은 test_contrast.py.
"""

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

CSS = (Path(__file__).parents[2] / "app" / "static" / "css" / "style.css").read_text(
    encoding="utf-8"
)
VOID_TAGS = {"area", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}
FOCUSABLE = {"a", "button", "input", "select", "textarea", "summary"}
CONVERSATION = "9b1c4da5-7a74-4f97-88cb-1b2790e510a9"

# (로그인 여부, 주소) — 화면이 그리는 모든 페이지와 상태
LOGGED_OUT_PAGES = ["/", "/signup", "/login", "/login?joined=1", "/login?expired=1"]
LOGGED_IN_PAGES = ["/", "/chat", f"/chat?conversation={CONVERSATION}", "/history",
                   f"/history?conversation={CONVERSATION}"]
PAGES = [("비로그인", path) for path in LOGGED_OUT_PAGES] + [
    ("로그인", path) for path in LOGGED_IN_PAGES
]


class Node:
    def __init__(self, tag: str, attrs: dict[str, str | None], parent: "Node | None") -> None:
        self.tag = tag
        self.attrs = attrs
        self.parent = parent
        self.children: list[Node | str] = []

    def walk(self):
        for child in self.children:
            if isinstance(child, Node):
                yield child
                yield from child.walk()

    def text(self) -> str:
        """안의 글자 (꾸밈 svg 는 빼고)"""
        parts = []
        for child in self.children:
            if isinstance(child, str):
                parts.append(child)
            elif child.tag != "svg":
                parts.append(child.text())
        return " ".join(" ".join(parts).split())

    def ancestors(self):
        node = self.parent
        while node is not None:
            yield node
            node = node.parent


class _Tree(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.root = Node("#document", {}, None)
        self.current = self.root

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs), self.current)
        self.current.children.append(node)
        if tag not in VOID_TAGS:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.current.children.append(Node(tag, dict(attrs), self.current))

    def handle_endtag(self, tag):
        node = self.current
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self.current = node.parent

    def handle_data(self, data):
        self.current.children.append(data)


def tree(html: str) -> Node:
    parser = _Tree()
    parser.feed(html)
    return parser.root


def all_nodes(root: Node, tag: str | None = None) -> list[Node]:
    return [node for node in root.walk() if tag is None or node.tag == tag]


def by_id(root: Node, element_id: str) -> Node | None:
    found = [node for node in root.walk() if node.attrs.get("id") == element_id]
    return found[0] if found else None


@pytest.fixture(params=PAGES, ids=[f"{who}:{path}" for who, path in PAGES])
def page(request) -> tuple[str, Node]:
    who, path = request.param
    client = request.getfixturevalue("client" if who == "비로그인" else "logged_in_client")
    response = client.get(path)
    assert response.status_code == 200, path
    return path, tree(response.text)


# ── 문서 ──


def test_page_language_and_title(page):
    path, root = page
    html = all_nodes(root, "html")[0]
    assert html.attrs.get("lang") == "ko"  # 스크린리더가 한국어로 읽는다
    title = all_nodes(root, "title")[0].text()
    assert "EasyExplain" in title and title != "", path


def test_viewport_does_not_block_zoom(page):
    _, root = page
    viewport = [m for m in all_nodes(root, "meta") if m.attrs.get("name") == "viewport"][0]
    content = viewport.attrs["content"]
    assert "width=device-width" in content
    # 손가락으로 확대하는 것을 막지 않는다 (글자를 키워 읽는 사람)
    assert "user-scalable" not in content and "maximum-scale" not in content


# ── 제목·랜드마크 ──


def test_one_h1_and_heading_levels_do_not_skip(page):
    path, root = page
    headings = [node for node in root.walk() if re.fullmatch(r"h[1-6]", node.tag)]
    levels = [int(node.tag[1]) for node in headings]
    assert levels.count(1) == 1, f"{path}: h1 이 {levels.count(1)}개"
    assert levels[0] == 1, f"{path}: 첫 제목이 h1 이 아님"
    for before, after in zip(levels, levels[1:], strict=False):
        assert after <= before + 1, f"{path}: h{before} 다음에 h{after} (단계 건너뜀)"


def test_headings_have_text_or_are_hidden_while_empty(page):
    path, root = page
    for node in root.walk():
        if re.fullmatch(r"h[1-6]", node.tag) and node.text() == "":
            # 스크립트가 채우는 제목은 비어 있는 동안 CSS 가 숨겨야 한다 (빈 "제목 2" 를 읽지 않게)
            css_class = (node.attrs.get("class") or "").split()[0]
            assert re.search(rf"\.{css_class}:empty \{{\s*display: none;", CSS), (
                f"{path}: 빈 제목 {node.tag}.{css_class} 을 숨기는 규칙이 없다"
            )


def test_landmarks_appear_once_each(page):
    path, root = page
    assert len(all_nodes(root, "header")) == 1, path
    assert len(all_nodes(root, "footer")) == 1, path
    navs = all_nodes(root, "nav")
    assert len(navs) == 1 and navs[0].attrs.get("aria-label") == "주 메뉴", path
    mains = all_nodes(root, "main")
    assert len(mains) == 1, path


# ── 본문으로 건너뛰기 ──


def focusables(root: Node) -> list[Node]:
    found = []
    for node in root.walk():
        if node.tag == "a" and "href" not in node.attrs:
            continue
        if node.tag == "input" and node.attrs.get("type") == "hidden":
            continue
        if node.tag in FOCUSABLE or node.attrs.get("tabindex") not in (None, "-1"):
            found.append(node)
    return found


def test_skip_link_is_the_first_stop_and_goes_to_main(page):
    path, root = page
    first = focusables(root)[0]
    assert first.tag == "a" and "skip-link" in first.attrs.get("class", ""), path
    assert first.text() == "본문으로 건너뛰기"
    assert first.attrs["href"] == "#main"
    main = all_nodes(root, "main")[0]
    assert main.attrs.get("id") == "main"
    # 링크로 오면 포커스를 받아 다음 Tab 이 본문의 첫 컨트롤로 간다. Tab 순서에는 들어가지 않는다
    assert main.attrs.get("tabindex") == "-1"


def rule(selector: str) -> str:
    """`selector {` 로 시작하는 첫 규칙의 선언들"""
    begin = CSS.index(f"\n{selector} {{") + len(selector) + 3
    return CSS[begin : CSS.index("}", begin)]


def test_skip_link_is_off_screen_until_focused_and_44px():
    link = rule(".skip-link")
    assert "position: absolute;" in link
    assert "transform: translateY(" in link  # 화면 위쪽 밖 (display: none 이면 Tab 으로 못 간다)
    assert "display: none" not in link and "visibility: hidden" not in link
    assert "min-height: 44px;" in link
    assert "transform: none;" in rule(".skip-link:focus")


# ── 입력칸·aria 참조·id ──


def label_text_for(root: Node, field: Node) -> str:
    if field.attrs.get("aria-label"):
        return field.attrs["aria-label"]
    if field.attrs.get("aria-labelledby"):
        return " ".join(by_id(root, i).text() for i in field.attrs["aria-labelledby"].split())
    field_id = field.attrs.get("id")
    if field_id:
        for label in all_nodes(root, "label"):
            if label.attrs.get("for") == field_id:
                return label.text()
    for ancestor in field.ancestors():
        if ancestor.tag == "label":
            return ancestor.text()
    return ""


def test_every_form_field_has_a_name(page):
    path, root = page
    fields = [
        node
        for node in root.walk()
        if node.tag in ("input", "textarea", "select") and node.attrs.get("type") != "hidden"
    ]
    for field in fields:
        assert label_text_for(root, field), f"{path}: 이름(label) 없는 입력칸 {field.attrs}"


def test_aria_and_label_references_point_to_existing_ids(page):
    path, root = page
    ids = {node.attrs["id"] for node in root.walk() if node.attrs.get("id")}
    for node in root.walk():
        for attr in ("for", "aria-describedby", "aria-labelledby", "aria-controls"):
            for target in (node.attrs.get(attr) or "").split():
                assert target in ids, f"{path}: {node.tag} {attr}={target} 가 없는 id"


def test_ids_are_unique(page):
    path, root = page
    ids = [node.attrs["id"] for node in root.walk() if node.attrs.get("id")]
    duplicated = {i for i in ids if ids.count(i) > 1}
    assert not duplicated, f"{path}: 같은 id 가 둘 이상 {duplicated}"


def test_level_choices_are_a_named_radio_group(logged_in_client):
    # 채팅의 수준 선택: 라디오 묶음(fieldset)의 이름 = legend, 각 라디오의 이름 = 감싼 label 의 글
    root = tree(logged_in_client.get("/chat").text)
    fieldset = all_nodes(root, "fieldset")[0]
    assert all_nodes(fieldset, "legend")[0].text() == "설명 수준"
    radios = [node for node in all_nodes(fieldset, "input") if node.attrs.get("type") == "radio"]
    assert [label_text_for(root, radio) for radio in radios] == ["아주 쉽게", "입문자", "전공자"]
    assert {radio.attrs["name"] for radio in radios} == {"level"}  # 한 묶음 — 화살표 키로 고른다


# ── 그림·버튼·링크 이름 ──


def test_images_have_alt_and_icons_are_hidden(page):
    path, root = page
    for img in all_nodes(root, "img"):
        assert "alt" in img.attrs, f"{path}: alt 없는 그림 {img.attrs}"
    for svg in all_nodes(root, "svg"):
        hidden = svg.attrs.get("aria-hidden") == "true" or any(
            a.attrs.get("aria-hidden") == "true" for a in svg.ancestors()
        )
        assert hidden, f"{path}: 꾸밈 아이콘 svg 를 스크린리더가 읽는다"


def test_buttons_and_links_have_names(page):
    path, root = page
    for node in root.walk():
        if node.tag in ("a", "button", "summary"):
            name = node.attrs.get("aria-label") or node.text()
            assert name, f"{path}: 이름 없는 {node.tag} {node.attrs}"


# ── 오류·상태 칸 ──


def test_error_boxes_are_alerts_and_loading_lines_are_status(page):
    path, root = page
    for node in root.walk():
        classes = (node.attrs.get("class") or "").split()
        if "form-error" in classes:
            # 오류가 나타나면 스크린리더가 바로 읽고, 스크립트가 포커스를 옮길 수 있다
            assert node.attrs.get("role") == "alert", path
            assert node.attrs.get("tabindex") == "-1", path
        if "history-status" in classes or node.attrs.get("id") == "chat-loading":
            assert node.attrs.get("role") == "status", path


# ── 포커스 테두리·움직임·고대비 (CSS) ──


def test_focus_outline_is_only_removed_where_another_one_is_drawn():
    # outline 을 없애는 곳은 질문 칸 하나 — 대신 입력 상자 전체(.composer:focus-within)에 그린다
    removed = re.findall(r"\n([^\n{}]+) \{[^}]*outline: (?:none|0);", CSS)
    assert removed == [".composer textarea:focus-visible"]
    assert "outline: 3px solid var(--accent);" in rule(".composer:focus-within")
    assert "outline: 3px solid var(--accent);" in rule(":focus-visible")


def test_reduced_motion_stops_every_animation():
    reduced = CSS[CSS.index("@media (prefers-reduced-motion: reduce)") :]
    reduced = reduced[: reduced.index("\n}\n")]
    for selector, body in re.findall(r"\n([^\n{}@]+) \{([^}]*)\}", CSS):
        if re.search(r"\banimation: (?!none)", body):
            assert f"{selector.strip()} {{\n    animation: none;" in reduced, (
                f"{selector.strip()} 의 움직임을 움직임 줄이기 설정에서 멈추지 않는다"
            )


def test_current_menu_item_is_marked_by_more_than_colour():
    current = rule('.site-nav a[aria-current="page"]')
    assert "text-decoration: underline;" in current  # 색을 구분하기 어려워도 밑줄로 안다


def test_selected_level_stays_visible_in_forced_colours():
    forced = CSS[CSS.index("@media (forced-colors: active)") :]
    assert ".level-option input:checked + span {" in forced
    assert "background: Highlight;" in forced and "color: HighlightText;" in forced

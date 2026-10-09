"""내 기록 화면(/history) 테스트. (C 담당, EE-17)

EE-12·EE-14 의 화면 테스트와 같은 방식이다. HTML 은 표준 라이브러리 HTMLParser 로
태그·속성을 읽고, JS 는 pytest 로 실행하지 못해서 정한 방식(textContent, 한국 시간 변환,
대화 id 모양 검사)을 쓰는지 소스를 본다. 목록·더 보기·제목 대체·상세·이어서 질문의 실제 동작은
js/history.test.mjs 와 js/chat_resume.test.mjs 가 Node 로 실행해 확인하고
(test_chat_js_behavior.py 가 부른다), 화면이 기대는 서버 동작은
test_history_rules_match_server.py 가 본다.
"""

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from app.web import router as web_router
from app.web.router import CHAT_INPUT_RULES, HISTORY_RULES, HistoryRules

JS_DIR = Path(__file__).parents[2] / "app" / "static" / "js"
VOID_TAGS = {"area", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}
CONVERSATION = "9b1c4da5-7a74-4f97-88cb-1b2790e510a9"


class _Elements(HTMLParser):
    """요소마다 [태그, 속성, 안의 글자, 바깥 요소들의 id] 를 문서 순서대로 모은다.

    값 없는 속성(hidden 등)은 None.
    """

    def __init__(self) -> None:
        super().__init__()
        self.elements: list[list] = []
        self.open: list[list] = []

    def handle_starttag(self, tag, attrs):
        parents = [element[1].get("id") for element in self.open if element[1].get("id")]
        element = [tag, dict(attrs), "", parents]
        self.elements.append(element)
        if tag not in VOID_TAGS:
            self.open.append(element)

    def handle_data(self, data):
        for element in self.open:
            element[2] += data

    def handle_endtag(self, tag):
        for index in range(len(self.open) - 1, -1, -1):
            if self.open[index][0] == tag:
                del self.open[index:]
                break


def elements(html: str) -> list[list]:
    parser = _Elements()
    parser.feed(html)
    return [
        [tag, attrs, " ".join(text.split()), parents]
        for tag, attrs, text, parents in parser.elements
    ]


def by_id(html: str, element_id: str) -> list:
    """[태그, 속성, 글자, 바깥 id들]"""
    found = [element for element in elements(html) if element[1].get("id") == element_id]
    assert len(found) == 1, f"id={element_id} 가 1개가 아니라 {len(found)}개"
    return found[0]


def find_all(html: str, tag: str, **attrs: str) -> list[list]:
    return [
        element
        for element in elements(html)
        if element[0] == tag and all(element[1].get(key) == value for key, value in attrs.items())
    ]


def script(name: str) -> str:
    return (JS_DIR / name).read_text(encoding="utf-8")


def between(source: str, start: str, end: str) -> str:
    """source 에서 start 부터 end 앞까지 (함수 하나를 잘라 볼 때)"""
    begin = source.index(start)
    return source[begin : source.index(end, begin)]


@pytest.fixture
def list_html(logged_in_client) -> str:
    return logged_in_client.get("/history").text


@pytest.fixture
def detail_html(logged_in_client) -> str:
    return logged_in_client.get(f"/history?conversation={CONVERSATION}").text


# ── 접근 (이슈 #24 완료 조건: 비로그인 303, 로그인 200) ──


def test_history_redirects_to_login_when_logged_out(client):
    response = client.get("/history", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_history_detail_address_also_redirects_when_logged_out(client):
    response = client.get(f"/history?conversation={CONVERSATION}", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_history_returns_html_when_logged_in(logged_in_client):
    response = logged_in_client.get("/history")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


# ── 공통 틀·스크립트 ──


def test_history_uses_common_frame_and_marks_history_menu(list_html):
    assert find_all(list_html, "link", rel="stylesheet", href="/static/css/style.css")
    menu = find_all(list_html, "a", href="/history", **{"aria-current": "page"})
    assert [text for _, _, text, _ in menu] == ["내 기록"]
    tag, attrs, text, _ = by_id(list_html, "history-heading")
    assert (tag, text) == ("h1", "내 기록")
    # 화면 안에서 목록으로 돌아올 때 포커스를 둘 곳 (Tab 순서에는 없다)
    assert attrs["tabindex"] == "-1"
    assert "AI 설명은 틀릴 수 있어요" in list_html


def test_history_script_is_a_module(list_html):
    (tag,) = find_all(list_html, "script", src="/static/js/history.js")

    assert tag[1]["type"] == "module"  # api.js 를 import 한다. HTML 을 다 읽은 뒤 실행된다
    assert find_all(list_html, "script", src="/static/js/chat.js") == []


@pytest.mark.parametrize("name", ["history.js"])
def test_history_script_is_served(client, name):
    response = client.get(f"/static/js/{name}")

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]


# ── 화면 값 (한곳: app/web/router.py 의 HISTORY_RULES) ──


def test_history_rules_are_the_agreed_values():
    # 한 번에 20개(API limit 기본값), 서버가 붙이는 기본 제목 "새 대화",
    # 첫 질문 제목은 30자까지 (#49 에서 서버가 채울 제목의 예시 길이와 같게)
    assert HISTORY_RULES == HistoryRules(page_size=20, untitled="새 대화", title_max_length=30)
    assert 1 <= HISTORY_RULES.page_size <= 100  # API 명세 2장: limit 최대 100


def test_page_passes_rule_values_to_the_script(list_html):
    _, attrs, _, _ = by_id(list_html, "history")

    assert attrs["data-page-size"] == "20"
    assert attrs["data-untitled"] == "새 대화"
    assert attrs["data-title-max-length"] == "30"


def test_page_follows_rule_values(logged_in_client, monkeypatch):
    # 값을 바꾸면 화면이 함께 바뀐다 (템플릿·스크립트에 숫자·제목을 따로 적지 않았다)
    rules = HistoryRules(page_size=7, untitled="제목 없음", title_max_length=12)
    monkeypatch.setattr(web_router, "HISTORY_RULES", rules)
    _, attrs, _, _ = by_id(logged_in_client.get("/history").text, "history")

    assert (attrs["data-page-size"], attrs["data-untitled"], attrs["data-title-max-length"]) == (
        "7",
        "제목 없음",
        "12",
    )


def test_level_names_come_from_chat_rules(list_html):
    _, attrs, _, _ = by_id(list_html, "level-names")
    assert "hidden" in attrs  # 스크립트가 읽는 이름표라 화면에는 안 보인다

    names = [
        (item[1]["data-level"], item[2])
        for item in find_all(list_html, "li")
        if "level-names" in item[3]
    ]
    assert names == [(level.value, level.label) for level in CHAT_INPUT_RULES.levels]


# ── 목록 칸 ──


def test_list_view_is_shown_first_without_conversation_in_address(list_html):
    assert "hidden" not in by_id(list_html, "list-view")[1]
    assert "hidden" in by_id(list_html, "detail-view")[1]
    tag, attrs, text, _ = by_id(list_html, "list-status")
    assert (tag, attrs["role"], text) == ("p", "status", "기록을 불러오는 중이에요.")


def test_conversation_list_is_a_labelled_list_filled_by_script(list_html):
    tag, attrs, text, parents = by_id(list_html, "conversation-list")

    assert tag == "ul"
    assert attrs["aria-label"] == "대화 목록"
    assert "hidden" in attrs and text == ""  # 항목은 스크립트가 붙이고, 대화가 있으면 보인다
    assert "list-view" in parents


def test_more_button_is_hidden_until_there_are_more(list_html):
    tag, attrs, text, _ = by_id(list_html, "list-more")

    assert (tag, attrs["type"], text) == ("button", "button", "더 보기")
    assert "hidden" in attrs
    assert attrs["data-busy-label"] == "불러오는 중…"


def test_empty_state_links_to_chat(list_html):
    _, attrs, text, _ = by_id(list_html, "list-empty")
    assert "hidden" in attrs
    assert "아직 대화가 없어요" in text

    links = [item for item in find_all(list_html, "a", href="/chat") if "list-empty" in item[3]]
    assert [item[2] for item in links] == ["질문하러 가기"]


@pytest.mark.parametrize("view", ["list", "detail"])
def test_error_boxes_are_hidden_alerts_with_retry(list_html, view):
    _, attrs, _, _ = by_id(list_html, f"{view}-error")
    assert attrs["role"] == "alert"
    assert attrs["tabindex"] == "-1"  # 오류가 나면 포커스를 옮길 수 있게
    assert "hidden" in attrs

    for part in ("error-text", "error-note", "retry"):
        assert f"{view}-error" in by_id(list_html, f"{view}-{part}")[3]
    tag, retry, text, _ = by_id(list_html, f"{view}-retry")
    assert (tag, retry["type"], text) == ("button", "button", "다시 시도")
    assert "hidden" in retry


# ── 상세 칸 ──


def test_detail_view_is_shown_first_with_conversation_in_address(detail_html):
    # 스크립트가 고르기 전에 목록이 잠깐 보이지 않게 서버가 처음부터 상세 칸을 보이게 그린다
    assert "hidden" in by_id(detail_html, "list-view")[1]
    assert "hidden" not in by_id(detail_html, "detail-view")[1]
    assert by_id(detail_html, "detail-status")[2] == "대화를 불러오는 중이에요."
    assert by_id(detail_html, "list-status")[2] == ""


def test_detail_has_back_link_title_and_thread(list_html):
    tag, attrs, text, parents = by_id(list_html, "back-to-list")
    assert (tag, attrs["href"], text) == ("a", "/history", "목록으로")
    assert "detail-view" in parents

    tag, attrs, _, _ = by_id(list_html, "detail-title")
    assert tag == "h2"  # 내 기록(h1) 아래의 대화 제목
    assert attrs["tabindex"] == "-1"  # 화면 안에서 상세로 넘어오면 포커스를 여기로

    tag, attrs, text, _ = by_id(list_html, "detail-thread")
    assert (tag, attrs["aria-label"], text) == ("ol", "대화 내용", "")
    assert by_id(list_html, "detail-status")[1]["role"] == "status"


@pytest.mark.parametrize("element_id", ["continue-top", "continue-bottom"])
def test_continue_links_are_hidden_until_a_conversation_is_loaded(list_html, element_id):
    tag, attrs, text, parents = by_id(list_html, element_id)

    # 채팅 화면으로 가는 링크 (주소는 스크립트가 대화 id 로 채운다)
    assert (tag, text) == ("a", "이어서 질문")
    assert attrs["href"] == "/chat"
    assert "hidden" in attrs
    assert "detail-view" in parents


# ── 스크립트 (정한 방식을 쓰는지) ──


@pytest.mark.parametrize("name", ["history.js", "chat.js", "api.js"])
def test_scripts_never_parse_server_text_as_html(name):
    # 제목·질문·답변을 HTML 로 해석하면 그 안의 <script>·<img onerror> 가 실행될 수 있다
    source = script(name)

    for unsafe in (".innerHTML", ".outerHTML", ".insertAdjacentHTML(", "document.write("):
        assert unsafe not in source, f"{name} 에 {unsafe}"


def test_history_script_puts_server_text_in_as_text():
    source = script("history.js")

    assert "element.textContent = text;" in between(source, "function bubble", "\n}\n")
    assert "text.textContent = message;" in between(source, "function panel", "\n}\n")  # 오류 문구
    title = between(source, "function setTitle", "\n}\n")
    assert "if (element) element.textContent = title;" in title


def test_history_script_shows_times_in_korea_time():
    # 이슈 #24: API 의 UTC 시각을 이 식 그대로 바꿔 보여 준다 (DB·API 는 UTC 그대로)
    expression = 'new Date(t).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })'

    assert expression in script("history.js")
    assert "time.dateTime = t;" in script("history.js")  # <time datetime> 에는 원래 UTC


def test_conversation_id_is_checked_before_it_goes_into_a_request():
    # 주소의 대화 id 는 사용자가 바꿀 수 있다 — "../me/chats" 같은 값이 다른 API 를 부르지 않게
    api = script("api.js")
    assert (
        "const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;"
        in api
    )

    detail = between(script("history.js"), "async function showDetail", "\n}\n")
    assert detail.index("if (isUuid(id)) {") < detail.index("apiGet(`/api/conversations/${id}`)")
    title = between(script("history.js"), "async function loadTitle", "\n}\n")
    assert title.index("!isUuid(id)") < title.index("apiGet(`/api/conversations/${id}`)")
    opening = between(script("chat.js"), "async function openConversation", "\n}\n")
    assert opening.index("if (!isUuid(id)) {") < opening.index("apiGet(`/api/conversations/${id}`)")


def test_get_requests_send_no_csrf_token_and_follow_401_to_login():
    get = between(script("api.js"), "export async function apiGet", "\n}\n")

    assert 'fetch(url, { credentials: "same-origin", cache: "no-store" })' in get
    assert "X-CSRF-Token" not in get  # 읽기만 하는 요청
    assert get.index("response.status === 401") < get.index("goToLogin();")


def test_not_found_message_matches_the_server_wording():
    # 주소의 id 모양이 틀려 묻지 않았을 때도 서버의 404 와 같은 말 (서버 문구는 교차 테스트가 본다)
    assert 'CONVERSATION_NOT_FOUND_MESSAGE = "대화를 찾을 수 없어요.";' in script("api.js")


def test_messages_the_history_screen_adds_use_the_team_tone():
    # 화면이 덧붙이는 안내는 "~해요"/"~주세요".
    # 서버 문구(error.message)는 바꾸지 않고 그대로 보여 준다
    added = [
        "기록을 불러오는 중이에요.",
        "대화를 불러오는 중이에요.",
        "이 대화에는 아직 질문이 없어요.",
        "목록에서 다시 골라 주세요.",
        "아직 답을 만드는 중이에요. 잠시 뒤 다시 열어 보세요.",
        "답을 만드는 중에 멈춰서 답이 없어요.",
        "응답이 늦어져 답을 받지 못했어요.",
        "질문 한도에 걸려 답을 받지 못했어요.",
        "오류가 나서 답을 받지 못했어요.",
    ]
    source = script("history.js")

    for message in added:
        assert message in source, message
        assert re.search(r"(요|세요)\.$", message), message


def test_messages_the_chat_screen_adds_when_opening_a_conversation_use_the_team_tone():
    added = [
        "지난 대화를 불러오는 중이에요.",
        "새 대화로 시작해요.",
        "지난 대화를 불러오지 못해 새 대화로 시작해요. 내 기록에서 다시 열 수 있어요.",
    ]
    source = script("chat.js")

    for message in added:
        assert message in source, message
        assert re.search(r"(요|세요)\.$", message), message


# ── 스타일 (휴대폰에서 누르기·좁은 폭) ──

CSS = (JS_DIR.parent / "css" / "style.css").read_text(encoding="utf-8")


def rule(selector: str, css: str = CSS) -> str:
    """css 에서 `selector {` 로 시작하는 첫 규칙의 선언들"""
    begin = css.index(f"\n{selector} {{") + len(selector) + 3
    return css[begin : css.index("}", begin)]


def mobile_css() -> str:
    return between(CSS, "@media (max-width: 520px) {", "\n}\n")


def test_touch_targets_are_at_least_44px():
    # 손가락으로 누르기 편한 크기 — 목록 카드는 넉넉하게, 접힌 실패 묶음 버튼은 다른 버튼과 같게
    item = int(re.search(r"min-height: (\d+)px;", rule(".history-item")).group(1))
    assert item >= 44
    assert "min-height: 44px;" in rule(".missing-group summary")


def test_long_titles_wrap_instead_of_overflowing():
    # 끊을 곳이 없는 긴 제목(주소·영문)이 좁은 화면에서 가로로 넘치지 않게
    for selector in (".history-item-title", ".detail-title"):
        assert "overflow-wrap: anywhere;" in rule(selector), selector
        # 한국어는 낱말 중간에서 줄을 바꾸지 않는다
        assert "word-break: keep-all;" in rule(selector), selector


def test_empty_status_line_takes_no_space():
    # 상태 줄은 스크린리더가 읽도록 늘 두지만, 비어 있으면 자리를 차지하지 않는다
    assert "margin-bottom: 0;" in rule(".history-status:empty")


def test_unanswered_turns_look_different_from_answers():
    assert "border-style: dashed;" in rule(".msg-missing .bubble")


def test_narrow_screens_fill_width_with_the_main_buttons():
    mobile = mobile_css()

    assert ".history-more .btn,\n  .detail-end .btn {\n    width: 100%;" in mobile
    assert ".history-item {" in mobile

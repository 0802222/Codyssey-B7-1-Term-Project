"""채팅 화면(/chat) 테스트. (C 담당, EE-12)

HTML 은 표준 라이브러리 HTMLParser 로 태그·속성·글자를 읽어 검사한다(속성 순서와 무관).
질문을 보내는 동작(fetch, 기다리는 동안 잠금, 답변 표시, 오류, 후속 버튼, 로그아웃)은 JS 라서
pytest 로는 실행하지 않고 브라우저에서 확인한다. 여기서는 스크립트가 연결돼 있고, 정해 둔 방식
(textContent, 한국 시간 변환, 요청마다 새 UUID, CSRF 헤더, 명세의 API 주소)을 쓰는지 본다.
"""

from html.parser import HTMLParser
from pathlib import Path

import pytest

from app.web import router as web_router
from app.web.router import CHAT_INPUT_RULES, ChatInputRules, LevelOption

JS_DIR = Path(__file__).parents[2] / "app" / "static" / "js"
VOID_TAGS = {"area", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}


class _Elements(HTMLParser):
    """요소마다 (태그 이름, 속성 dict, 안의 글자) 를 문서 순서대로 모은다. 값 없는 속성은 None."""

    def __init__(self) -> None:
        super().__init__()
        self.elements: list[list] = []
        self.open: list[list] = []

    def handle_starttag(self, tag, attrs):
        element = [tag, dict(attrs), ""]
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


def elements(html: str) -> list[tuple[str, dict[str, str | None], str]]:
    parser = _Elements()
    parser.feed(html)
    return [(tag, attrs, " ".join(text.split())) for tag, attrs, text in parser.elements]


def find_all(html: str, tag: str, **attrs: str) -> list[tuple[dict[str, str | None], str]]:
    """tag 중에서 attrs 의 속성 값이 모두 같은 것들의 (속성, 글자)"""
    return [
        (found, text)
        for name, found, text in elements(html)
        if name == tag and all(found.get(key) == value for key, value in attrs.items())
    ]


def find_one(html: str, tag: str, **attrs: str) -> tuple[dict[str, str | None], str]:
    found = find_all(html, tag, **attrs)
    assert len(found) == 1, f"<{tag} {attrs}> 가 1개가 아니라 {len(found)}개"
    return found[0]


@pytest.fixture
def chat_html(logged_in_client) -> str:
    return logged_in_client.get("/chat").text


def script(name: str) -> str:
    return (JS_DIR / name).read_text(encoding="utf-8")


# ── 접근 ──


def test_chat_redirects_to_login_when_logged_out(client):
    response = client.get("/chat", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_chat_returns_html_when_logged_in(logged_in_client):
    response = logged_in_client.get("/chat")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_chat_uses_common_frame_and_marks_chat_menu(chat_html):
    find_one(chat_html, "link", rel="stylesheet", href="/static/css/style.css")
    _, text = find_one(chat_html, "a", href="/chat", **{"aria-current": "page"})
    assert text == "채팅"
    _, heading = find_one(chat_html, "h1")
    assert heading == "채팅"  # 화면에는 숨긴 제목. 스크린리더가 페이지 제목으로 읽는다
    assert "AI 설명은 틀릴 수 있어요" in chat_html


# ── 수준 선택 ──


def test_three_levels_are_radio_buttons_in_a_labelled_group(chat_html):
    find_one(chat_html, "fieldset", **{"class": "level-picker"})
    _, legend = find_one(chat_html, "legend")
    assert legend == "설명 수준"

    radios = find_all(chat_html, "input", type="radio", name="level")
    assert [(attrs["value"], attrs["data-label"]) for attrs, _ in radios] == [
        ("easy", "아주 쉽게"),
        ("beginner", "입문자"),
        ("advanced", "전공자"),
    ]
    # 라디오 버튼마다 화면에 보이는 이름이 label 안에 있다 (아이콘은 aria-hidden)
    labels = [text for attrs, text in find_all(chat_html, "label", **{"class": "level-option"})]
    assert labels == ["아주 쉽게", "입문자", "전공자"]


def test_easy_is_selected_when_page_opens(chat_html):
    radios = find_all(chat_html, "input", name="level")
    checked = [attrs["value"] for attrs, _ in radios if "checked" in attrs]

    assert checked == ["easy"]


# ── 질문 입력 ──


def test_question_box_has_label_limit_and_descriptions(chat_html):
    form, _ = find_one(chat_html, "form", id="chat-form")
    assert form["method"] == "post"  # 스크립트가 뜨기 전에 보내져도 질문이 주소에 붙지 않게
    assert "novalidate" in form  # 브라우저 말풍선 대신 오류 칸에 안내 문구

    question, _ = find_one(chat_html, "textarea", id="question")
    assert question["name"] == "question"
    assert question["maxlength"] == "2000"
    assert "required" in question
    assert question["enterkeyhint"] == "send"  # 휴대폰 자판의 Enter 가 "보내기" 모양
    _, label = find_one(chat_html, "label", **{"for": "question"})
    assert label == "질문"

    page_ids = {attrs["id"] for _, attrs, _ in elements(chat_html) if attrs.get("id")}
    described_by = question["aria-describedby"].split()
    assert {"question-count", "question-keys", "chat-error"} <= set(described_by)
    assert set(described_by) <= page_ids, "aria-describedby 가 없는 id 를 가리킴"
    _, keys = find_one(chat_html, "p", id="question-keys")
    assert "Enter" in keys and "Shift" in keys


def test_character_count_starts_at_zero_of_max(chat_html):
    _, count = find_one(chat_html, "span", id="question-count")

    assert count == "0 / 2000"


def test_send_button_has_label_for_waiting(chat_html):
    button, text = find_one(chat_html, "button", type="submit")

    assert text == "보내기"
    assert button["data-busy-label"] == "기다리는 중…"


# ── 대화·오류·후속 버튼·새 대화 ──


def test_thread_announces_new_messages(chat_html):
    thread, text = find_one(chat_html, "ol", id="thread")

    assert thread["aria-live"] == "polite"  # 새 답변을 스크린리더가 읽는다
    assert text == ""  # 말풍선은 스크립트가 붙인다
    find_one(chat_html, "div", id="chat-empty")  # 첫 질문 전 안내


def test_error_box_is_hidden_alert(chat_html):
    error_box, _ = find_one(chat_html, "div", id="chat-error")

    assert error_box["role"] == "alert"
    assert error_box["tabindex"] == "-1"
    assert "hidden" in error_box
    find_one(chat_html, "span", id="chat-error-text")


def test_follow_up_buttons_send_prompt_phrases(chat_html):
    group, _ = find_one(chat_html, "div", id="follow-ups")
    assert "hidden" in group  # 첫 답을 받은 뒤에 보인다
    assert group["role"] == "group"

    buttons = find_all(chat_html, "button", **{"class": "chip"})
    assert [(attrs["type"], attrs["data-question"], text) for attrs, text in buttons] == [
        ("button", "더 쉽게", "더 쉽게"),
        ("button", "예시 하나 더", "예시 하나 더"),
        ("button", "핵심만", "핵심만"),
    ]


def test_new_chat_button(chat_html):
    button, text = find_one(chat_html, "button", id="new-chat")

    assert button["type"] == "button"
    assert text == "새 대화"


def test_chat_script_is_a_module(chat_html):
    tag, _ = find_one(chat_html, "script", src="/static/js/chat.js")

    assert tag["type"] == "module"  # api.js 를 import 한다. HTML 을 다 읽은 뒤 실행된다


# ── 입력 규칙 값 (한곳: app/web/router.py 의 CHAT_INPUT_RULES) ──


def test_chat_rules_are_the_agreed_values():
    # API 명세 3장(질문 1~2,000자, level 3가지)·시안(처음 수준 = 아주 쉽게)·prompts.py(후속 문구)
    assert CHAT_INPUT_RULES == ChatInputRules(
        question_max_length=2000,
        levels=(
            LevelOption("easy", "아주 쉽게"),
            LevelOption("beginner", "입문자"),
            LevelOption("advanced", "전공자"),
        ),
        default_level="easy",
        follow_ups=("더 쉽게", "예시 하나 더", "핵심만"),
    )


def test_page_follows_rule_values(logged_in_client, monkeypatch):
    # 값을 바꾸면 화면이 함께 바뀐다 (템플릿에 숫자·이름을 따로 적지 않았다)
    rules = ChatInputRules(
        question_max_length=123,
        levels=(LevelOption("easy", "쉬움"), LevelOption("advanced", "어려움")),
        default_level="advanced",
        follow_ups=("다시",),
    )
    monkeypatch.setattr(web_router, "CHAT_INPUT_RULES", rules)
    html = logged_in_client.get("/chat").text

    assert find_one(html, "textarea", id="question")[0]["maxlength"] == "123"
    assert find_one(html, "span", id="question-count")[1] == "0 / 123"
    radios = find_all(html, "input", name="level")
    assert [(a["value"], a["data-label"], "checked" in a) for a, _ in radios] == [
        ("easy", "쉬움", False),
        ("advanced", "어려움", True),
    ]
    chips = find_all(html, "button", **{"class": "chip"})
    assert [attrs["data-question"] for attrs, _ in chips] == ["다시"]


# ── 스크립트 (pytest 로 실행하지 않고, 정한 방식을 쓰는지 본다) ──


@pytest.mark.parametrize("name", ["chat.js", "api.js", "logout.js"])
def test_scripts_are_served(client, name):
    response = client.get(f"/static/js/{name}")

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]


@pytest.mark.parametrize("name", ["chat.js", "api.js", "logout.js"])
def test_scripts_never_parse_text_as_html(name):
    # 답변·서버 문구를 HTML 로 해석하면 그 안의 <script>·<img onerror> 가 실행될 수 있다.
    # (주석의 "innerHTML 이 아니라…" 설명은 괜찮다 — 속성·함수로 쓰는 곳을 찾는다)
    source = script(name)

    for unsafe in (".innerHTML", ".outerHTML", ".insertAdjacentHTML(", "document.write("):
        assert unsafe not in source, f"{name} 에 {unsafe}"


def test_chat_script_puts_messages_in_as_text():
    source = script("chat.js")
    bubble = source[source.index("function createBubble") : source.index("function addQuestion")]

    assert "bubble.textContent = text;" in bubble
    assert "errorText.textContent = message;" in source  # 오류 문구도 글자로


def test_chat_script_shows_times_in_korea_time():
    # 이슈 #19: API 의 UTC 시각을 그대로 이 코드로 바꿔 보여 준다 (DB·API 는 UTC 그대로)
    assert 'new Date(t).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })' in script("chat.js")


def test_chat_script_makes_new_uuid_for_every_request():
    source = script("chat.js")
    ask = source[source.index("async function askServer") : source.index("/* ── 화면에 그리기")]

    # crypto.randomUUID 가 없으면(HTTP 주소) getRandomValues 로 UUID v4 를 만든다
    assert 'typeof crypto.randomUUID === "function"' in source
    assert "crypto.getRandomValues(new Uint8Array(16))" in source
    assert "(bytes[6] & 0x0f) | 0x40" in source  # 버전 4
    assert "(bytes[8] & 0x3f) | 0x80" in source  # 변형 10xx
    # 질문 요청을 만들 때마다 새로 만든다 (한 번 만든 값을 다시 쓰지 않는다)
    assert "client_request_id: newRequestId()," in ask


def test_chat_script_calls_the_spec_apis_in_order():
    source = script("chat.js")
    ask = source[source.index("async function askServer") : source.index("/* ── 화면에 그리기")]

    assert 'apiPost("/api/conversations", {})' in ask  # 첫 질문이면 대화부터 (명세: 본문 {})
    assert 'apiPost("/api/chat", {' in ask
    assert ask.index("/api/conversations") < ask.index("/api/chat")
    for field in ("conversation_id: conversationId", "question,", "level,", "client_request_id:"):
        assert field in ask  # 명세 3장의 요청 필드 4개


def test_chat_script_checks_question_before_sending():
    source = script("chat.js")
    submit = source[source.index('form.addEventListener("submit"') :]

    assert 'if (question === "") return "질문을 입력해 주세요.";' in source
    assert "질문은 ${questionInput.maxLength}자 이하로 입력해 주세요." in source
    assert "질문은 ${questionInput.maxLength}자까지 입력할 수 있어요." in source  # 붙여 넣기
    assert submit.index("findQuestionProblem(question)") < submit.index("sendQuestion(question")
    assert "questionInput.value.trim()" in submit  # 앞뒤 공백을 뺀 길이로 본다 (명세 3장)


def test_chat_script_sends_on_enter_but_not_while_composing_korean():
    source = script("chat.js")

    assert 'event.key !== "Enter" || event.shiftKey || event.isComposing' in source
    assert "form.requestSubmit();" in source


def test_chat_script_locks_buttons_while_waiting():
    source = script("chat.js")
    waiting = source[source.index("function setWaiting") : source.index("/* ── 질문 보내기")]

    for locked in ("sendButton", "newChatButton", "button"):
        assert f"{locked}.disabled = on;" in waiting
    assert "questionInput.readOnly = on;" in waiting  # 보낸 질문은 지우지 않고 남겨 둔다
    assert "if (waiting) return;" in source


def test_follow_up_sends_button_phrase_to_same_conversation():
    source = script("chat.js")

    assert "sendQuestion(button.dataset.question, { fromInput: false })" in source


def test_api_script_sends_csrf_token_and_refetches_it():
    source = script("api.js")

    assert 'headers["X-CSRF-Token"] = csrfToken;' in source
    assert "sessionStorage.getItem(CSRF_TOKEN_KEY)" in source  # 로그인 화면이 보관한 값
    assert 'fetch("/api/auth/me"' in source  # 없으면 다시 받는다
    assert 'credentials: "same-origin"' in source
    # 서버가 보낸 문구, 없으면 대체 문구
    assert "result.data?.error?.message || UNKNOWN_ERROR_MESSAGE" in source


def test_api_script_shares_token_name_and_fallback_messages_with_auth_script():
    # 로그인 화면(auth.js)이 넣은 이름으로 꺼내고, 못 받은 서버 문구는 같은 대체 문구로 보여 준다
    api, auth = script("api.js"), script("auth.js")

    for line in (
        'CSRF_TOKEN_KEY = "csrf_token";',
        'NETWORK_ERROR_MESSAGE = "서버에 연결하지 못했어요. '
        '인터넷 연결을 확인하고 다시 시도해 주세요.";',
        'UNKNOWN_ERROR_MESSAGE = "일시적인 오류가 발생했어요. 잠시 후 다시 시도해 주세요.";',
    ):
        assert line in api and line in auth


def test_logout_script_ends_session_and_goes_home():
    source = script("logout.js")

    # X-CSRF-Token 은 apiPost 가 붙인다. 401 은 로그인 화면이 아니라 아래에서 / 로 (이슈 #21)
    assert 'apiPost("/api/auth/logout", undefined, LOGOUT_OPTIONS)' in source
    assert "LOGOUT_OPTIONS = { redirectOn401: false };" in source
    assert "result.status === 204 || result.status === 401" in source  # 401 = 이미 세션이 끝남
    assert "forgetCsrfToken();" in source
    assert 'location.replace("/")' in source


def test_logout_script_is_not_loaded_when_logged_out(client):
    assert find_all(client.get("/").text, "script", src="/static/js/logout.js") == []


def test_logout_script_is_loaded_when_logged_in(logged_in_client):
    tag, _ = find_one(logged_in_client.get("/").text, "script", src="/static/js/logout.js")

    assert tag["type"] == "module"

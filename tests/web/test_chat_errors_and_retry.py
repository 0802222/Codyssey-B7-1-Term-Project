"""채팅 화면의 API 연결 — 답변을 만드는 중·오류·다시 보내기·401·429 테스트. (C 담당, EE-14)

EE-12 의 test_chat_page.py 와 같은 방식이다. HTML 은 표준 라이브러리 HTMLParser 로
태그·속성을 읽고, JS 는 pytest 로 실행하지 못해서 정한 방식을 쓰는지 소스를 본다.
실제 동작은 헤드리스 Chrome 으로 실제 서버에서 확인했고,
화면 규칙이 서버 동작과 맞는지는 test_chat_retry_rules_match_server.py 가 본다.
"""

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

STATIC = Path(__file__).parents[2] / "app" / "static"
VOID_TAGS = {"area", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}


class _Elements(HTMLParser):
    """요소마다 (태그, 속성, 안의 글자, 바깥 요소들의 id) 를 문서 순서대로 모은다."""

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
    return parser.elements


def by_id(html: str, element_id: str) -> tuple[int, list]:
    """(문서 순서, [태그, 속성, 글자, 바깥 id들])"""
    found = [(i, e) for i, e in enumerate(elements(html)) if e[1].get("id") == element_id]
    assert len(found) == 1, f"id={element_id} 가 1개가 아니라 {len(found)}개"
    return found[0]


def script(name: str) -> str:
    return (STATIC / "js" / name).read_text(encoding="utf-8")


def between(source: str, start: str, end: str) -> str:
    """source 에서 start 부터 end 앞까지 (함수 하나를 잘라 볼 때)"""
    begin = source.index(start)
    return source[begin : source.index(end, begin)]


def flat(text: str) -> str:
    """줄바꿈·들여쓰기를 공백 하나로 (여러 줄에 걸친 식을 찾을 때)"""
    return " ".join(text.split())


@pytest.fixture
def chat_html(logged_in_client) -> str:
    return logged_in_client.get("/chat").text


# ── 템플릿: 답변을 만드는 중 · 다시 보내기 ──


def test_loading_region_is_an_empty_status_region_in_the_answer_place(chat_html):
    order, (tag, attrs, text, _) = by_id(chat_html, "chat-loading")

    assert tag == "div"
    assert attrs["role"] == "status"  # 안에 말풍선이 들어오면 스크린리더가 한 번 읽는다
    assert attrs["aria-live"] == "polite"
    assert "hidden" not in attrs  # 숨겼다 보이는 상태 칸은 못 읽을 수 있어서 칸은 늘 둔다
    assert text.strip() == ""  # 말풍선은 스크립트가 넣는다
    # 대화 목록 바로 다음, 오류 칸 앞 = 다음 답변이 붙을 자리
    assert by_id(chat_html, "thread")[0] < order < by_id(chat_html, "chat-error")[0]


def test_error_box_has_a_hidden_retry_button_and_a_note_line(chat_html):
    _, (tag, attrs, text, parents) = by_id(chat_html, "chat-retry")

    assert tag == "button"
    assert attrs["type"] == "button"  # 폼 제출 버튼이 아니다
    assert "hidden" in attrs  # 요청이 실패했을 때만 보인다
    assert text.strip() == "다시 보내기"
    assert "chat-error" in parents  # 시안처럼 오류 칸 안 오른쪽
    note_tag, _, note_text, note_parents = by_id(chat_html, "chat-error-note")[1]
    assert note_tag == "p" and note_text == "" and "chat-error" in note_parents
    _, (_, box, _, _) = by_id(chat_html, "chat-error")
    assert box["role"] == "alert" and "hidden" in box  # EE-12 그대로: 나타나면 읽힌다


# ── api.js: 401 이면 로그인 화면, 낡은 CSRF 토큰은 한 번만 다시 ──


def test_api_script_goes_to_login_on_401():
    source = script("api.js")
    go = between(source, "export function goToLogin", "}")
    post = between(source, "export async function apiPost", "\n}\n")

    assert 'LOGIN_AGAIN_URL = "/login?expired=1";' in source  # 로그인 화면이 안내를 띄우는 주소
    assert go.index("forgetCsrfToken();") < go.index("location.replace(LOGIN_AGAIN_URL);")
    assert "{ redirectOn401 = true } = {}" in post  # 기본은 이동, 로그아웃만 끈다
    assert "if (result.status === 401 && redirectOn401) {" in post
    assert "goToLogin();" in post
    assert "return new Promise(() => {});" in post  # 이동하는 동안 화면은 기다리는 모습 그대로


def test_api_script_resends_once_with_a_new_token_when_csrf_is_rejected():
    source = script("api.js")
    post = between(source, "export async function apiPost", "\n}\n")
    send = between(source, "async function sendPost", "\n}\n")

    assert post.count("await sendPost(url, body);") == 2  # 처음 + 한 번만 더
    assert 'if (result.data?.error?.code === "CSRF_REJECTED") {' in post
    assert post.index("CSRF_REJECTED") < post.index("result.status === 401")
    # 예전 토큰을 지워서 다음 보내기가 /api/auth/me 로 새 토큰을 받는다
    assert "forgetCsrfToken();" in send
    # 로그아웃은 따로 다시 보내지 않는다 (apiPost 가 한다)
    assert script("logout.js").count("await apiPost(") == 1


def test_api_script_tells_when_the_server_may_have_processed_the_request():
    # 서버가 오류 JSON 으로 실패를 알려 온 게 아니면 서버가 처리했는지 모른다
    # (연결 끊김, JSON 이 아닌 응답, 200 인데 본문을 못 읽음) → 같은 요청 번호로 다시 보낸다
    # 동작은 js/chat_retry.test.mjs
    assert "return result.offline || !result.data?.error?.code;" in script("api.js")


# ── chat.js: 답변을 만드는 중 ──


def test_chat_script_shows_making_answer_bubble_while_waiting():
    source = script("chat.js")
    loading = between(source, "function showLoading", "\n}\n")
    waiting = between(source, "function setWaiting", "\n}\n")

    assert 'createBubble("답변을 만드는 중")' in loading  # 글자로만 넣는다
    assert loading.count('document.createElement("i")') == 3  # 시안의 점 세 개
    assert 'dots.setAttribute("aria-hidden", "true");' in loading  # 점은 읽지 않는다
    assert "loading.replaceChildren(item);" in loading
    assert "loading.replaceChildren();" in loading  # 답을 받으면 비운다
    assert "showLoading(on);" in waiting


def test_loading_dots_blink_unless_reduced_motion():
    css = (STATIC / "css" / "style.css").read_text(encoding="utf-8")
    reduced = between(css, "@media (prefers-reduced-motion: reduce)", "\n}\n")

    assert "animation: loading-blink 1.2s infinite;" in css
    assert ".loading-dots i" in reduced and "animation: none;" in reduced
    # 비어 있는 상태 칸은 줄 간격만큼 되돌려 빈자리를 만들지 않는다
    assert ".chat-loading:empty {\n  margin-top: calc(-1 * var(--chat-gap));" in css


# ── chat.js: 다시 보내기 ──


def test_retry_button_resends_the_failed_question_in_place():
    source = script("chat.js")
    question = between(source, "function sendQuestion", "\n}\n")
    resend = between(source, "function resendFailed", "\n}\n")

    assert 'retryButton.addEventListener("click", resendFailed);' in source
    assert "send(failed);" in resend
    assert "addQuestion(" not in resend  # 말풍선을 또 붙이지 않는다
    # 입력칸이나 후속 버튼으로 같은 질문(같은 글·수준)을 보내도 다시 보내기와 같다
    same = "if (failed && failed.question === question && failed.level.value === level.value) {"
    assert same in question
    assert question.index(same) < question.index("resendFailed();")
    assert question.index("resendFailed();") < question.index("addQuestion(")


def test_retry_keeps_the_key_only_when_the_server_may_have_it():
    source = script("chat.js")
    resend = between(source, "function resendFailed", "\n}\n")
    failure = flat(between(source, "function showFailure", "\n}\n"))

    # 처리 여부를 모르거나(응답 없음) 처리 중(CHAT_BUSY)이면 같은 번호 — 시간이 지나도 안 바꾼다.
    # 화면은 서버가 언제 처리를 시작했는지 몰라서, 시간만으로 실패라고 단정하면 중복이 생긴다
    # (PR #47 리뷰)
    assert 'request.sameIdNext = outcomeUnknown(result) || code === "CHAT_BUSY";' in failure
    assert "sentAt" not in source and "STALE_BUSY_MS" not in source
    # 같은 번호를 쓸 때가 아니면(서버가 실패를 확정해 알려 옴) 새 번호
    # 동작은 js/chat_retry.test.mjs
    assert "if (!failed.sameIdNext) {" in resend
    assert resend.index("if (!failed.sameIdNext) {") < resend.index("newRequestId();")


def test_failed_question_stays_until_the_user_moves_on():
    source = script("chat.js")
    failure = between(source, "function showFailure", "\n}\n")
    drop = between(source, "function dropFailed", "\n}\n")
    submit = between(source, 'form.addEventListener("submit"', "\n});\n")
    paste = between(source, 'questionInput.addEventListener("paste"', "\n});\n")
    new_chat = between(source, 'newChatButton.addEventListener("click"', "\n});\n")

    assert "failed = request;" in failure  # 시안처럼 말풍선을 남기고 다시 보내기를 기다린다
    assert "failed.item.remove();" in drop  # 다시 보내지 않기로 하면 그때 뺀다
    assert "dropFailed();" in between(source, "function sendQuestion", "\n}\n")  # 다른 질문
    assert "failed = null;" in new_chat
    # 입력 안내(빈 질문·넘치는 붙여 넣기)는 보내지 않은 것이라 답을 못 받은 질문과
    # 요청 번호를 지우지 않고 다시 보내기도 남긴다 (PR #47 리뷰 — 동작은 js/chat_retry.test.mjs)
    for handler in (submit, paste):
        assert "dropFailed()" not in handler
        assert "{ retry: failed !== null }" in handler


def test_validation_error_offers_no_retry_and_sends_focus_to_the_input():
    failure = between(script("chat.js"), "function showFailure", "\n}\n")
    branch = between(failure, 'if (code === "VALIDATION_ERROR") {', "return;")

    note = '{ note: "질문을 고쳐서 다시 보내 주세요." }'
    assert f"showError(failureMessage(result), {note});" in branch
    assert "retry: true" not in branch
    assert "request.item.remove();" in branch
    assert "questionInput.focus();" in branch


def test_missing_conversation_restarts_as_a_new_conversation():
    failure = between(script("chat.js"), "function showFailure", "\n}\n")
    branch = between(failure, 'if (code === "CONVERSATION_NOT_FOUND") {', "showError(")

    assert "conversationId = null;" in branch  # 다시 보내면 POST /api/conversations 부터
    assert 'note = "다시 보내면 새 대화로 시작해요.";' in branch


def test_failure_shows_server_message_and_moves_focus_to_retry():
    failure = between(script("chat.js"), "function showFailure", "\n}\n")

    # 서버가 보낸 error.message 를 그대로 (failureMessage)
    assert "showError(failureMessage(result), { retry: true, note });" in failure
    # 마지막에 포커스를 다시 보내기로 — Enter 한 번이면 다시 보낸다
    assert failure.rstrip().splitlines()[-1].strip().startswith("retryButton.focus();")


# ── chat.js: 429 대기 ──


def test_rate_limit_locks_sending_and_shows_remaining_seconds():
    source = script("chat.js")
    cooldown = between(source, "function startCooldown", "\n}\n")
    failure = between(source, "function showFailure", "\n}\n")

    assert "const RATE_LIMIT_WAITS = [10, 20, 40, 60];" in source
    assert 'if (code === "RATE_LIMITED") {' in failure
    assert failure.index("startCooldown();") < failure.index("errorBox.focus();")
    assert "return waiting || cooldownTimer !== null;" in source  # 기다리는 동안은 보내지 않는다
    assert "setLocked(true);" in cooldown and "setLocked(false);" in cooldown
    assert "clearInterval(cooldownTimer);" in cooldown
    # 1초마다 바뀌는 숫자는 aria-hidden, 스크린리더용 문장은 처음 한 번
    assert 'shown.setAttribute("aria-hidden", "true");' in cooldown
    assert 'spoken.className = "visually-hidden";' in cooldown
    assert "spoken.textContent = `${seconds}초 뒤에 다시 보낼 수 있어요.`;" in cooldown
    assert "shown.textContent = `${left}초 뒤에 다시 보낼 수 있어요.`;" in cooldown
    assert 'countdown.replaceChildren("이제 다시 보낼 수 있어요.");' in cooldown


def test_rate_limit_waits_grow_only_for_consecutive_429():
    source = script("chat.js")
    cooldown = between(source, "function startCooldown", "\n}\n")
    send = between(source, "async function send(", "\n}\n")

    assert "rateLimitStreak += 1;" in cooldown
    assert (
        "RATE_LIMIT_WAITS[Math.min(rateLimitStreak, RATE_LIMIT_WAITS.length) - 1]" in cooldown
    )
    assert 'if (result.data?.error?.code !== "RATE_LIMITED") {' in send
    assert "rateLimitStreak = 0;" in send
    # 가장 긴 시간을 기다려도 걸리면 하루 한도 안내를 덧붙인다
    assert "if (rateLimitStreak >= RATE_LIMIT_WAITS.length) {" in cooldown
    assert "DAILY_LIMIT_NOTE" in cooldown


def test_messages_the_screen_adds_use_the_team_tone():
    # 서버 문구는 그대로 두고, 화면이 덧붙이는 안내만 "~해요"/"~주세요" 로 쓴다
    source = script("chat.js")
    added = [
        "질문을 고쳐서 다시 보내 주세요.",
        "다시 보내면 새 대화로 시작해요.",
        "초 뒤에 다시 보낼 수 있어요.",
        "이제 다시 보낼 수 있어요.",
        "계속 이 안내가 나오면 오늘 서비스 전체의 질문 한도를 다 썼을 수 있어요. "
        "한도는 매일 오전 9시에 다시 채워져요.",
    ]

    for message in added:
        assert message in source, message
        assert re.search(r"(요|세요)\.$", message), message

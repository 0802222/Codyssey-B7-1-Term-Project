"""회원가입(/signup)·로그인(/login) 화면 테스트. (C 담당, EE-09)

HTML 은 표준 라이브러리 HTMLParser 로 태그와 속성을 읽어 검사한다. 속성 순서나 줄바꿈이 바뀌어도
깨지지 않고, 속성이 빠지면 실패한다. 폼을 실제로 보내는 동작(입력 규칙 검사, fetch, 오류 표시,
이동)은 JS 라서 pytest 로는 실행하지 않고 브라우저에서 확인한다. 여기서는 스크립트가 연결돼 있고
API 주소와 입력 규칙 속성을 제대로 쓰는지만 본다.
"""

from html.parser import HTMLParser

import pytest

from app.web import router as web_router
from app.web.router import AUTH_INPUT_RULES, AuthInputRules

PATHS = ["/signup", "/login"]


class _StartTags(HTMLParser):
    """시작 태그를 (태그 이름, 속성 dict) 로 모은다. 값이 없는 속성(required 등)은 None 이다."""

    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def start_tags(html: str) -> list[tuple[str, dict[str, str | None]]]:
    parser = _StartTags()
    parser.feed(html)
    return parser.tags


def find_all(html: str, tag: str, **attrs: str) -> list[dict[str, str | None]]:
    """tag 중에서 attrs 의 속성 값이 모두 같은 것들. 예: find_all(html, "a", href="/login")"""
    return [
        found
        for name, found in start_tags(html)
        if name == tag and all(found.get(key) == value for key, value in attrs.items())
    ]


def find_one(html: str, tag: str, **attrs: str) -> dict[str, str | None]:
    found = find_all(html, tag, **attrs)
    assert len(found) == 1, f"<{tag} {attrs}> 가 1개가 아니라 {len(found)}개"
    return found[0]


@pytest.mark.parametrize("path", PATHS)
def test_auth_page_returns_html(client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


@pytest.mark.parametrize("path", PATHS)
def test_auth_page_uses_common_frame(client, path):
    html = client.get(path).text

    find_one(html, "link", rel="stylesheet", href="/static/css/style.css")
    find_one(html, "nav", **{"aria-label": "주 메뉴"})
    assert "AI 설명은 틀릴 수 있어요" in html


def test_login_menu_is_marked_current_only_on_login_page(client):
    login_html = client.get("/login").text
    signup_html = client.get("/signup").text

    find_one(login_html, "a", href="/login", **{"aria-current": "page"})
    # 가입 화면은 "로그인" 메뉴가 가리키는 페이지가 아니므로 현재 위치 표시가 없다
    assert find_all(signup_html, "a", **{"aria-current": "page"}) == []


@pytest.mark.parametrize(
    ("path", "form_id", "password_autocomplete"),
    [("/signup", "signup-form", "new-password"), ("/login", "login-form", "current-password")],
)
def test_form_fields_have_labels_and_autocomplete(client, path, form_id, password_autocomplete):
    html = client.get(path).text

    form = find_one(html, "form", id=form_id)
    assert form["method"] == "post"  # 스크립트가 뜨기 전에 눌려도 비밀번호가 주소에 붙지 않게
    assert "novalidate" in form  # 브라우저 말풍선 대신 auth.js 가 오류 칸에 안내 문구를 보여 준다

    email = find_one(html, "input", id="email")
    assert email["name"] == "email"
    assert email["type"] == "email"
    assert email["autocomplete"] == "email"
    assert "required" in email

    password = find_one(html, "input", id="password")
    assert password["name"] == "password"
    assert password["type"] == "password"
    assert password["autocomplete"] == password_autocomplete
    assert "required" in password

    # 입력칸마다 화면에 보이는 label 이 연결돼 있다
    find_one(html, "label", **{"for": "email"})
    find_one(html, "label", **{"for": "password"})


@pytest.mark.parametrize("path", PATHS)
def test_error_box_is_announced_and_described_by_inputs(client, path):
    html = client.get(path).text

    error_box = find_one(html, "div", id="form-error")
    assert error_box["role"] == "alert"  # 문구가 나타나면 스크린리더가 바로 읽는다
    assert error_box["tabindex"] == "-1"  # 오류가 나면 스크립트가 여기로 포커스를 옮긴다
    assert "hidden" in error_box  # 처음에는 숨겨 둔다
    find_one(html, "span", id="form-error-text")

    page_ids = {attrs["id"] for _, attrs in start_tags(html) if attrs.get("id")}
    for field_id in ("email", "password"):
        described_by = find_one(html, "input", id=field_id)["aria-describedby"].split()
        assert "form-error" in described_by
        assert set(described_by) <= page_ids, f"{field_id} 의 aria-describedby 가 없는 id 를 가리킴"


def test_signup_page_explains_input_rules(client):
    rules = AUTH_INPUT_RULES
    html = client.get("/signup").text

    assert "email-hint" in find_one(html, "input", id="email")["aria-describedby"]
    assert "password-hint" in find_one(html, "input", id="password")["aria-describedby"]
    assert f"{rules.email_max_length}자까지 입력할 수 있어요." in html
    assert f"{rules.password_min_length}~{rules.password_max_length}자로 입력해 주세요." in html
    assert ("영문·숫자·기호만 쓸 수 있어요." in html) == rules.password_ascii_only


def test_input_rules_are_the_agreed_values():
    # 화면이 쓰는 입력 규칙. 바꾸면 서버(app/auth/router.py)와 API 명세 2장도 같은 값으로 바꾼다
    assert AUTH_INPUT_RULES == AuthInputRules(
        email_max_length=100,
        password_min_length=8,
        password_max_length=64,
        password_ascii_only=True,
    )


@pytest.mark.parametrize("path", PATHS)
def test_inputs_carry_input_rules(client, path):
    rules = AUTH_INPUT_RULES
    html = client.get(path).text

    # maxlength 보다 긴 글자는 입력되지 않고, auth.js 는 이 속성들을 읽어 보내기 전에 검사한다
    email = find_one(html, "input", id="email")
    password = find_one(html, "input", id="password")
    assert email["maxlength"] == str(rules.email_max_length)
    assert password["minlength"] == str(rules.password_min_length)
    assert password["maxlength"] == str(rules.password_max_length)
    assert ("data-ascii-only" in password) == rules.password_ascii_only
    assert "data-ascii-only" not in email  # 영어만 받는 규칙은 비밀번호에만 있다


@pytest.mark.parametrize("ascii_only", [True, False])
def test_pages_follow_rule_values(client, monkeypatch, ascii_only):
    # 규칙 값을 바꾸면 두 화면의 안내·자리 표시·입력칸 속성이 함께 바뀐다
    # (템플릿에 숫자를 따로 적지 않았다)
    rules = AuthInputRules(
        email_max_length=61,
        password_min_length=7,
        password_max_length=33,
        password_ascii_only=ascii_only,
    )
    monkeypatch.setattr(web_router, "AUTH_INPUT_RULES", rules)
    signup_html = client.get("/signup").text
    login_html = client.get("/login").text

    assert "61자까지 입력할 수 있어요." in signup_html
    assert "7~33자로 입력해 주세요." in signup_html
    assert ("영문·숫자·기호만 쓸 수 있어요." in signup_html) == ascii_only
    assert find_one(login_html, "input", id="password")["placeholder"] == "7~33자"
    for html in (signup_html, login_html):
        assert find_one(html, "input", id="email")["maxlength"] == "61"
        password = find_one(html, "input", id="password")
        assert (password["minlength"], password["maxlength"]) == ("7", "33")
        assert ("data-ascii-only" in password) == ascii_only


@pytest.mark.parametrize(("path", "other_page"), [("/signup", "/login"), ("/login", "/signup")])
def test_auth_pages_link_to_each_other(client, path, other_page):
    html = client.get(path).text

    assert find_all(html, "a", href=other_page)


@pytest.mark.parametrize("path", PATHS)
def test_submit_button_has_label_for_sending_state(client, path):
    html = client.get(path).text

    button = find_one(html, "button", type="submit")
    assert button["data-busy-label"].endswith("중…")


@pytest.mark.parametrize("path", PATHS)
def test_auth_script_is_loaded_with_defer(client, path):
    html = client.get(path).text

    script = find_one(html, "script", src="/static/js/auth.js")
    assert "defer" in script


def test_auth_script_is_served_and_calls_auth_api(client):
    response = client.get("/static/js/auth.js")

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    script = response.text
    # 가입·로그인 API, 성공 뒤 이동할 곳, 서버 오류 문구, 로그인 응답의 csrf_token 보관
    assert '"/api/auth/signup"' in script
    assert '"/api/auth/login"' in script
    assert '"/login?joined=1"' in script
    assert '"/chat"' in script
    assert "data?.error?.message" in script
    assert "sessionStorage.setItem" in script
    # 서버 문구를 HTML 로 해석하지 않는다
    assert "innerHTML" not in script


def test_auth_script_checks_input_rules_before_sending(client):
    script = client.get("/static/js/auth.js").text

    # 규칙 값은 스크립트에 적지 않고 입력칸 속성에서 읽어 안내 문구를 만든다
    assert "이메일을 입력해 주세요." in script
    assert "이메일은 ${email.maxLength}자 이하로 입력해 주세요." in script
    assert "비밀번호를 입력해 주세요." in script
    assert "비밀번호는 ${password.minLength}~${password.maxLength}자로 입력해 주세요." in script
    # 영어만 받는 칸(data-ascii-only)은 제출할 때와 붙여 넣을 때 모두 글자 종류를 본다.
    # 쓸 수 있는 글자는 영문·숫자·기호·공백 (ASCII 32~126)
    assert r"/^[\x20-\x7E]*$/" in script
    on_submit = 'password.hasAttribute("data-ascii-only") && !ENGLISH_ONLY.test(password.value)'
    on_paste = 'input.hasAttribute("data-ascii-only") && !ENGLISH_ONLY.test(text)'
    assert on_submit in script
    assert on_paste in script
    assert "비밀번호는 영어(영문·숫자·기호)로만 입력해 주세요." in script
    # 제출하면 fetch 보다 먼저 검사하고, 걸리면 보내지 않는다
    assert script.index("const problem = findInputProblem(form);") < script.index("fetch(apiUrl")
    # 너무 길거나 영어가 아닌 글을 붙여 넣으면 잘라 넣지 않고 막는다
    assert 'addEventListener("paste"' in script
    assert "${field} ${input.maxLength}자까지 입력할 수 있어요." in script


def test_login_page_shows_notice_only_after_signup(client):
    notice = "가입이 끝났어요"

    assert notice in client.get("/login?joined=1").text
    assert notice not in client.get("/login").text
    assert notice not in client.get("/login?joined=0").text


def test_login_page_explains_when_login_ended(client):
    # 채팅 중 API 가 401 이면 api.js 가 /login?expired=1 로 보낸다 (EE-14)
    notice = '<p class="form-notice">로그인이 풀렸어요. 다시 로그인해 주세요.</p>'

    assert notice in client.get("/login?expired=1").text
    assert notice not in client.get("/login").text
    assert notice not in client.get("/login?expired=0").text
    both = client.get("/login?joined=1&expired=1").text  # 안내는 한 번에 하나 (가입 안내가 먼저)
    assert "가입이 끝났어요" in both and notice not in both


@pytest.mark.parametrize("path", PATHS)
def test_email_input_has_format_pattern_and_example(client, path):
    email = find_one(client.get(path).text, "input", id="email")

    # 서버와 같은 형식 정규식. auth.js 가 이 속성을 읽어 보내기 전에 형식을 본다
    assert email["pattern"] == AUTH_INPUT_RULES.email_pattern
    assert email["placeholder"] == "name@example.com"


def test_email_pattern_comes_from_rules(client, monkeypatch):
    rules = AuthInputRules(
        email_max_length=61,
        password_min_length=7,
        password_max_length=33,
        password_ascii_only=False,
        email_pattern="[a-z]+@[a-z]+",
    )
    monkeypatch.setattr(web_router, "AUTH_INPUT_RULES", rules)

    for path in PATHS:
        assert find_one(client.get(path).text, "input", id="email")["pattern"] == "[a-z]+@[a-z]+"


def test_auth_script_checks_email_before_password(client):
    script = client.get("/static/js/auth.js").text
    start = script.index("function findInputProblem")
    checks = script[start : script.index("function findPasteProblem")]

    assert "new RegExp(`^(?:${email.pattern})$`)" in checks
    assert "올바른 이메일 형식을 입력해 주세요." in checks
    # 이메일(빈 값 → 글자 수 → 형식)을 다 본 뒤에 비밀번호를 본다
    email_checks = ("email.value", "email.maxLength", "email.pattern")
    assert max(checks.index(code) for code in email_checks) < checks.index("password.value")

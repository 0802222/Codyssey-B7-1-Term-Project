"""채팅 화면의 오류·다시 보내기 규칙이 실제 서버 동작과 맞는지 확인한다. (C 담당, EE-14)

화면(app/static/js/chat.js 의 resendFailed·showFailure, api.js 의 apiPost)은
실패를 이렇게 나눠 다룬다.
- 응답을 못 받았으면(연결 끊김) 같은 client_request_id 로 다시 — 서버가 이미 답을 만들었으면
  AI 를 다시 부르지 않고 저장한 답을 돌려준다
- 서버가 실패를 알려 왔으면 새 client_request_id — 같은 키면 서버가 저장한 실패를 돌려준다
- 401 이면 로그인 화면으로, 429 면 정한 시간 기다리기, 422 는 다시 보내기 없이 입력 고치기
여기서는 화면이 기대는 서버 동작을 실제 가입·로그인·CSRF 로 확인한다.
AI 만 호출 수를 세는 가짜로 끼운다. 서버 규칙(B 의 app/chat)이 바뀌면 여기서 실패한다 —
그때는 chat.js 의 규칙도 같이 바꾼다.
"""

import re
from datetime import UTC, date, datetime, time, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlmodel import Session, select

from app.chat import rate_limit
from app.chat.fake_provider import FakeAIProvider
from app.chat.provider import AITimeoutError, get_ai_provider
from app.core.errors import AppError, ErrorCode
from app.db.models import ChatTurn
from app.web.router import CHAT_INPUT_RULES as RULES

JS_DIR = Path(__file__).parents[2] / "app" / "static" / "js"
PASSWORD = "correct-horse-1"


def script(name: str) -> str:
    return (JS_DIR / name).read_text(encoding="utf-8")


class CountingProvider(FakeAIProvider):
    """가짜 AI. 몇 번 불렸는지 세고, error 를 넣으면 그 오류를 낸다."""

    def __init__(self):
        super().__init__(reply="테스트 답변")
        self.calls = 0
        self.error = None

    async def generate_reply(self, *args, **kwargs):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return await super().generate_reply(*args, **kwargs)


@pytest.fixture
def ai(app):
    provider = CountingProvider()
    app.dependency_overrides[get_ai_provider] = lambda: provider
    yield provider
    app.dependency_overrides.pop(get_ai_provider, None)


@pytest.fixture
def browser(client, settings):
    """화면과 같은 순서로 실제 가입·로그인한 client 와 X-CSRF-Token 헤더.

    헤더 값은 로그인 화면이 sessionStorage 에 보관하는 로그인 응답의 csrf_token 이다.
    """
    account = {"email": "screen@example.com", "password": PASSWORD}
    origin = {"Origin": settings.site_origin}
    assert client.post("/api/auth/signup", headers=origin, json=account).status_code == 201
    login = client.post("/api/auth/login", headers=origin, json=account)
    assert login.status_code == 200
    return SimpleNamespace(client=client, csrf={"X-CSRF-Token": login.json()["csrf_token"]})


@pytest.fixture
def conversation_id(browser):
    response = browser.client.post("/api/conversations", headers=browser.csrf, json={})
    assert response.status_code == 201
    return response.json()["id"]


def chat(browser, conversation_id, question="API가 뭐야?", *, key=None, level="easy"):
    body = {
        "conversation_id": conversation_id,
        "question": question,
        "level": level,
        "client_request_id": key or str(uuid4()),
    }
    return browser.client.post("/api/chat", headers=browser.csrf, json=body)


# ── 화면의 흐름 그대로: 가입 → 로그인 → 대화 만들기 → 질문 → 후속 질문 (이슈 #21 완료 조건) ──


def test_question_and_follow_up_on_the_real_server(browser, conversation_id, ai):
    first = chat(browser, conversation_id, "API가 뭐야?")
    follow_up = chat(browser, conversation_id, "더 쉽게")  # 후속 버튼 = 버튼 문구 그대로

    for response in (first, follow_up):
        assert response.status_code == 200
        turn = response.json()
        # chat.js 의 isAnswer 가 보는 값
        assert turn["status"] == "completed" and turn["answer"] == "테스트 답변"
        assert turn["created_at"].endswith("Z")  # 화면이 한국 시간으로 바꾸는 UTC 시각
    assert follow_up.json()["conversation_id"] == conversation_id  # 같은 대화로 이어진다
    assert ai.calls == 2


def test_screen_input_rules_match_the_real_chat_validation(browser, conversation_id, ai):
    # 화면 값(CHAT_INPUT_RULES)이 서버 검증과 같아야
    # 화면이 통과시킨 질문을 서버가 422 로 막지 않는다
    limit = RULES.question_max_length

    assert chat(browser, conversation_id, "가" * limit).status_code == 200
    # 앞뒤 공백은 빼고 센다 (화면도 trim 한 길이로 본다)
    assert chat(browser, conversation_id, f"  {'나' * limit}\n").status_code == 200
    assert chat(browser, conversation_id, "다" * (limit + 1)).status_code == 422
    # 공백만 → 422 (화면은 보내기 전에 "질문을 입력해 주세요.")
    assert chat(browser, conversation_id, " \n ").status_code == 422
    for level in RULES.levels:
        assert chat(browser, conversation_id, "수준 확인", level=level.value).status_code == 200
    for phrase in RULES.follow_ups:
        assert chat(browser, conversation_id, phrase).status_code == 200
    assert ai.calls == 2 + len(RULES.levels) + len(RULES.follow_ups)  # 422 는 AI 를 부르지 않는다


# ── 다시 보내기의 요청 번호 규칙 ──


def test_same_key_after_a_lost_response_returns_the_saved_answer_without_ai(
    browser, conversation_id, ai
):
    # 서버는 답을 만들어 저장했는데 화면은 연결이 끊겨 응답을 못 받은 경우
    # → 화면은 같은 키로 다시 보낸다
    key = str(uuid4())
    first = chat(browser, conversation_id, key=key)
    again = chat(browser, conversation_id, key=key)

    assert again.status_code == 200
    assert again.json()["turn_id"] == first.json()["turn_id"]  # 턴이 하나 더 생기지 않는다
    assert again.json()["answer"] == first.json()["answer"]
    assert ai.calls == 1  # AI 를 다시 부르지 않는다


def test_same_key_after_a_reported_failure_repeats_it_so_the_screen_uses_a_new_key(
    browser, conversation_id, ai
):
    key = str(uuid4())
    ai.error = AITimeoutError("시간 초과")
    failed = chat(browser, conversation_id, key=key)
    assert failed.status_code == 504
    assert failed.json()["error"]["code"] == ErrorCode.AI_TIMEOUT

    ai.error = None  # AI 가 다시 되더라도
    same_key = chat(browser, conversation_id, key=key)
    new_key = chat(browser, conversation_id)

    assert same_key.status_code == 504  # 같은 키는 저장한 실패를 그대로 돌려준다
    assert ai.calls == 2  # 처음 1번 + 새 키 1번 (같은 키는 AI 를 부르지 않았다)
    assert new_key.status_code == 200  # 그래서 화면은 서버가 실패를 알려 오면 새 키로 다시 보낸다


def test_error_codes_the_screen_checks_are_real_error_codes():
    # chat.js·api.js 가 비교하는 오류 코드 이름이 서버의 ErrorCode 에 있어야 한다
    # (서버에서 이름이 바뀌면 화면의 분기가 조용히 멈춘다)
    used = set()
    for name in ("chat.js", "api.js"):
        used |= set(re.findall(r'=== "([A-Z_]+)"', script(name)))

    assert used == {"CSRF_REJECTED", "VALIDATION_ERROR", "CHAT_BUSY", "CONVERSATION_NOT_FOUND",
                    "RATE_LIMITED"}
    assert used <= set(ErrorCode.__members__)


def test_same_key_stays_busy_while_processing_and_fails_only_when_the_server_says_so(
    app, browser, conversation_id, ai
):
    # 화면은 409 CHAT_BUSY 에 시간이 지나도 같은 키를 쓴다. 그래도 되는 근거가 서버의 이 동작이다:
    # 같은 키가 처리 중(pending)이면 409, 서버가 중단(interrupted)으로 정리하면(재시작 뒤 #22)
    # 503 을 준다
    # → 화면은 그 확정된 실패를 받은 뒤에야 새 키로 보낸다 (동작은 js/chat_retry.test.mjs)
    key = uuid4()
    user_id = browser.client.get("/api/auth/me").json()["user"]["id"]
    with Session(app.state.engine) as session:
        session.add(
            ChatTurn(
                conversation_id=UUID(conversation_id),
                user_id=user_id,
                client_request_id=key,
                request_id="still-running",
                level="easy",
                question="처리 중 질문",
                status="pending",
            )
        )
        session.commit()

    busy = chat(browser, conversation_id, "처리 중 질문", key=str(key))
    assert busy.status_code == 409
    assert busy.json()["error"]["code"] == ErrorCode.CHAT_BUSY

    with Session(app.state.engine) as session:
        turn = session.exec(select(ChatTurn).where(ChatTurn.client_request_id == key)).one()
        turn.status = "interrupted"
        session.add(turn)
        session.commit()
    stopped = chat(browser, conversation_id, "처리 중 질문", key=str(key))
    new_key = chat(browser, conversation_id, "처리 중 질문")

    assert stopped.status_code == 503
    assert stopped.json()["error"]["code"] == ErrorCode.AI_UNAVAILABLE
    assert new_key.status_code == 200
    assert ai.calls == 1  # 같은 키 두 번은 AI 를 부르지 않았다


# ── 401·403·404·422 ──


def test_requests_after_the_session_ended_get_401_so_the_screen_goes_to_login(
    browser, conversation_id, ai
):
    # 403 이 아니라 401 이 와야 api.js 가 로그인 화면으로 보낸다
    # (세션 검사가 CSRF 검사보다 먼저다)
    assert browser.client.post("/api/auth/logout", headers=browser.csrf).status_code == 204

    response = chat(browser, conversation_id)
    created = browser.client.post("/api/conversations", headers=browser.csrf, json={})

    for ended in (response, created):
        assert ended.status_code == 401
        assert ended.json()["error"]["code"] == ErrorCode.AUTH_REQUIRED
    # 로그아웃 버튼은 401 도 "이미 로그아웃됨" 으로 보고 첫 화면으로 간다 (이슈 #21)
    assert browser.client.post("/api/auth/logout", headers=browser.csrf).status_code == 401
    assert ai.calls == 0


def test_stale_csrf_token_is_rejected_before_anything_is_saved(browser, conversation_id, ai):
    # api.js 는 403 CSRF_REJECTED 면 새 토큰으로 같은 요청을 한 번 더 보낸다 —
    # 서버가 아무것도 저장하지 않고 거절해야 같은 키로 다시 보내도 안전하다
    key = str(uuid4())
    body = {"conversation_id": conversation_id, "question": "토큰", "level": "easy",
            "client_request_id": key}
    rejected = browser.client.post("/api/chat", headers={"X-CSRF-Token": "stale"}, json=body)
    token = browser.client.get("/api/auth/me").json()["csrf_token"]  # api.js 의 getCsrfToken
    retried = browser.client.post("/api/chat", headers={"X-CSRF-Token": token}, json=body)

    assert rejected.status_code == 403
    assert rejected.json()["error"]["code"] == ErrorCode.CSRF_REJECTED
    assert retried.status_code == 200
    assert ai.calls == 1


def test_unknown_conversation_and_invalid_input_are_not_saved(browser, ai):
    missing = chat(browser, str(uuid4()))
    invalid = chat(browser, str(uuid4()), level="expert")

    # 404: 화면은 새 대화로 다시 보내게 한다 / 422: 다시 보내기 없이 입력을 고치게 한다
    assert missing.status_code == 404
    assert missing.json()["error"] == {
        "code": ErrorCode.CONVERSATION_NOT_FOUND,
        "message": "대화를 찾을 수 없어요.",
        "request_id": missing.json()["error"]["request_id"],
    }
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == ErrorCode.VALIDATION_ERROR
    assert ai.calls == 0


# ── 429 (질문 한도) ──


def test_rate_limited_question_is_saved_as_failure_and_needs_a_new_key(
    browser, conversation_id, ai, settings
):
    settings.user_requests_per_minute = 1  # 앱이 처음 질문을 받을 때 이 값으로 한도를 만든다
    assert chat(browser, conversation_id, "하나").status_code == 200

    key = str(uuid4())
    limited = chat(browser, conversation_id, "둘", key=key)
    same_key = chat(browser, conversation_id, "둘", key=key)

    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == ErrorCode.RATE_LIMITED
    # 화면은 서버 문구를 그대로 보여 주고, 남은 시간 안내만 덧붙인다
    message = limited.json()["error"]["message"]
    assert message == "질문 요청 한도를 초과했어요. 잠시 후 다시 시도해 주세요."
    # 서버가 풀리는 시각을 알려 주지 않아서 기다릴 시간은 화면이 정했다
    assert "retry-after" not in limited.headers
    assert same_key.status_code == 429  # 저장된 실패 → 다시 보내기는 새 키
    assert ai.calls == 1


def test_longest_wait_on_the_screen_frees_the_per_user_limit(monkeypatch):
    # chat.js 의 RATE_LIMIT_WAITS 마지막 값(60초)을 기다리면 사용자 한도(최근 60초)는 반드시 풀린다
    match = re.search(r"const RATE_LIMIT_WAITS = \[([\d, ]+)\];", script("chat.js"))
    assert match, "chat.js 의 RATE_LIMIT_WAITS"
    waits = [int(value) for value in match.group(1).split(",")]
    clock = SimpleNamespace(seconds=1000.0)
    monkeypatch.setattr(rate_limit, "monotonic", lambda: clock.seconds)
    limiter = rate_limit.ChatRateLimiter(user_requests_per_minute=1, daily_request_limit=100)

    limiter.check_and_count(7)
    with pytest.raises(AppError):
        limiter.check_and_count(7)  # 곧바로 다시 → 429
    clock.seconds += max(waits)
    limiter.check_and_count(7)  # 화면이 기다리는 가장 긴 시간 뒤에는 풀린다

    assert waits == sorted(waits) and waits[0] > 0


def test_daily_limit_note_says_the_korean_time_the_server_resets(monkeypatch):
    # 서버의 하루 한도는 UTC 날짜가 바뀔 때 초기화된다 → 한국 시간 오전 9시 (화면 안내 문구)
    day = SimpleNamespace(value=date(2026, 10, 8))
    monkeypatch.setattr(rate_limit, "_today_utc", lambda: day.value)
    limiter = rate_limit.ChatRateLimiter(user_requests_per_minute=100, daily_request_limit=1)

    limiter.check_and_count(1)
    with pytest.raises(AppError):
        limiter.check_and_count(2)
    day.value = date(2026, 10, 9)
    limiter.check_and_count(2)

    utc_midnight = datetime.combine(day.value, time(0), tzinfo=UTC)
    # 한국 시간은 UTC+9 고정값으로 계산해 Windows의 시간대 DB 유무에 기대지 않는다.
    korean_time = timezone(timedelta(hours=9))
    assert utc_midnight.astimezone(korean_time).hour == 9
    assert "한도는 매일 오전 9시에 다시 채워져요." in script("chat.js")

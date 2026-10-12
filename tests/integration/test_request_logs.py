"""질문 하나의 서버 로그가 같은 request_id 로 이어지고, 원문·비밀 값은 남지 않는다. (EE-18)

과제 4-5 의 필수 로그: 요청 수신 / AI 호출 / AI 응답·실패 / DB 저장 성공·실패.
"""

import logging

import pytest

from app.chat.fake_provider import FakeAIProvider, FakeMode
from app.chat.provider import get_ai_provider
from app.core.logging import REQUEST_ID_HEADER

QUESTION = "로그에 남으면 안 되는 질문 원문"


def events_for(caplog, request_id):
    """해당 request_id 가 찍힌 로그 줄의 이벤트 이름과 필드를 순서대로 돌려준다."""
    events = []
    for record in caplog.records:
        name, *fields = record.getMessage().split()
        values = dict(field.split("=", 1) for field in fields if "=" in field)
        if values.get("request_id") == request_id:
            events.append((name, values))
    return events


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (
            FakeMode.SUCCESS,
            [
                ("request_received", None),
                ("db_save_success", "pending"),
                ("ai_call_start", None),
                ("ai_call_success", None),
                ("db_save_success", "completed"),
                ("request_completed", "200"),
            ],
        ),
        (
            FakeMode.TIMEOUT,
            [
                ("request_received", None),
                ("db_save_success", "pending"),
                ("ai_call_start", None),
                ("ai_call_failed", None),
                ("db_save_success", "failed"),
                ("request_completed", "504"),
            ],
        ),
    ],
)
def test_one_question_logs_six_events_with_one_request_id(app, user, caplog, mode, expected):
    conversation_id = user.post("/api/conversations", json={}).json()["id"]
    reply = "로그에 남으면 안 되는 답변 원문"
    app.dependency_overrides[get_ai_provider] = lambda: FakeAIProvider(mode=mode, reply=reply)

    with caplog.at_level(logging.INFO, logger="easyexplain"):
        response = user.ask(conversation_id, QUESTION)

    request_id = response.headers[REQUEST_ID_HEADER]
    events = events_for(caplog, request_id)
    # 이벤트 6종이 순서대로, 모두 같은 request_id 로 찍힌다 (상태는 DB 저장·응답 줄에만 있음).
    assert [(name, values.get("status")) for name, values in events] == expected
    # 응답 본문의 request_id 도 같은 값이라, 화면 오류 → 서버 로그를 바로 찾을 수 있다.
    if response.status_code != 200:
        assert response.json()["error"]["request_id"] == request_id
    else:
        assert response.json()["request_id"] == request_id

    # 질문·답변 원문, 비밀번호, CSRF 토큰, 세션 쿠키는 어느 로그에도 없다.
    session_cookie = user.client.cookies.get("session")
    for secret in [QUESTION, reply, user.password, user.csrf_token, session_cookie]:
        assert secret not in caplog.text

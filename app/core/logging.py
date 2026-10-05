"""서버 이벤트 로그와 request_id.

과제 필수 이벤트: request_received / ai_call_start / ai_call_success | ai_call_failed /
db_save_success | db_save_failed. 모두 log_event() 로 남기면 request_id 가 자동으로 붙는다.

로그에 남기면 안 되는 것: 비밀번호, 쿠키, 세션 토큰, API 키, 질문·응답 원문,
예외 메시지 원문 (입력값이나 비밀 값이 섞여 있을 수 있음).
"""

import logging
from contextvars import ContextVar

logger = logging.getLogger("easyexplain")

REQUEST_ID_HEADER = "X-Request-ID"

# 현재 요청의 request_id. RequestIdMiddleware 가 요청마다 설정한다.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logger.setLevel(level.upper())


def log_event(event: str, *, level: int = logging.INFO, **fields: object) -> None:
    """`INFO ai_call_start request_id=abc user_id=12 model=...` 형식으로 한 줄 기록한다."""
    parts = [event, f"request_id={request_id_var.get() or '-'}"]
    parts += [f"{key}={value}" for key, value in fields.items()]
    logger.log(level, " ".join(parts))

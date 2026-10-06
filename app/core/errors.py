"""공통 오류 규격.

모든 오류 응답은 아래 형식으로 통일한다. (docs/spec/api.md)
    {"error": {"code": "AI_TIMEOUT", "message": "...", "request_id": "..."}}

각 영역은 HTTPException 대신 AppError 를 raise 한다.
    raise AppError(404, ErrorCode.CONVERSATION_NOT_FOUND, "대화를 찾을 수 없어요.")
"""

import logging
import traceback
from enum import StrEnum
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import REQUEST_ID_HEADER, log_event, request_id_var

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# 오류를 잡아서 기록하는 쪽이라 "오류가 난 위치"에서 뺀다.
_CATCHER = PROJECT_ROOT / "app" / "core" / "middleware.py"


class ErrorCode(StrEnum):
    AUTH_REQUIRED = "AUTH_REQUIRED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    CSRF_REJECTED = "CSRF_REJECTED"
    NOT_FOUND = "NOT_FOUND"
    CONVERSATION_NOT_FOUND = "CONVERSATION_NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    ACCOUNT_EXISTS = "ACCOUNT_EXISTS"
    CHAT_BUSY = "CHAT_BUSY"
    REQUEST_CONFLICT = "REQUEST_CONFLICT"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    AI_UPSTREAM_ERROR = "AI_UPSTREAM_ERROR"
    AI_UNAVAILABLE = "AI_UNAVAILABLE"
    DB_ERROR = "DB_ERROR"
    AI_TIMEOUT = "AI_TIMEOUT"


class AppError(Exception):
    def __init__(self, status_code: int, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def not_implemented(issue: str) -> AppError:
    """아직 구현하지 않은 경로. 가짜 성공 대신 501 을 반환한다."""
    return AppError(501, ErrorCode.NOT_IMPLEMENTED, f"아직 구현되지 않은 기능입니다. ({issue})")


def _json_error(
    status_code: int, code: ErrorCode, message: str, request_id: str | None
) -> JSONResponse:
    headers = {REQUEST_ID_HEADER: request_id} if request_id else None
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "request_id": request_id}},
        headers=headers,
    )


def error_response(
    request: Request, status_code: int, code: ErrorCode, message: str
) -> JSONResponse:
    return _json_error(status_code, code, message, getattr(request.state, "request_id", None))


def internal_error_response(request_id: str | None) -> JSONResponse:
    message = "일시적인 오류가 발생했어요. 잠시 후 다시 시도해 주세요."
    return _json_error(500, ErrorCode.INTERNAL_ERROR, message, request_id)


def _error_location(exc: Exception) -> str:
    """우리 코드 중 예외가 난 가장 안쪽 위치. 예: app/chat/service.py:42"""
    for frame in reversed(traceback.extract_tb(exc.__traceback__)):
        path = Path(frame.filename).resolve()
        if path.is_relative_to(PROJECT_ROOT) and ".venv" not in path.parts and path != _CATCHER:
            # Windows 에서도 같은 로그가 되도록 경로 구분자를 / 로 통일한다.
            return f"{path.relative_to(PROJECT_ROOT).as_posix()}:{frame.lineno}"
    return "-"


def log_unexpected_error(exc: Exception) -> None:
    """예상하지 못한 오류를 기록한다.

    예외 메시지·스택 원문에는 입력값이나 비밀 값이 섞일 수 있으므로 남기지 않고,
    오류 종류와 발생 위치만 남긴다.
    """
    log_event(
        "unhandled_error",
        level=logging.ERROR,
        error_type=type(exc).__name__,
        location=_error_location(exc),
    )


async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    return error_response(request, exc.status_code, exc.code, exc.message)


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # 입력값 자체는 로그에 남기지 않고 문제가 된 필드 위치만 남긴다.
    fields = ",".join(".".join(str(p) for p in err["loc"]) for err in exc.errors())
    log_event("validation_failed", level=logging.WARNING, fields=fields)
    return error_response(request, 422, ErrorCode.VALIDATION_ERROR, "입력값을 확인해 주세요.")


async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code == 404:
        return error_response(request, 404, ErrorCode.NOT_FOUND, "요청한 경로를 찾을 수 없어요.")
    if exc.status_code == 405:
        return error_response(
            request, 405, ErrorCode.METHOD_NOT_ALLOWED, "허용되지 않은 요청 방식이에요."
        )
    return error_response(
        request, exc.status_code, ErrorCode.INTERNAL_ERROR, "요청을 처리할 수 없어요."
    )


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    # 대부분은 RequestIdMiddleware 가 먼저 처리한다. 미들웨어 바깥에서 난 오류만 여기로 온다.
    request_id = getattr(request.state, "request_id", None)
    token = request_id_var.set(request_id)
    try:
        log_unexpected_error(exc)
    finally:
        request_id_var.reset(token)
    return internal_error_response(request_id)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(Exception, _handle_unexpected)

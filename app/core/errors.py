"""공통 오류 규격.

모든 오류 응답은 아래 형식으로 통일한다. (docs/spec/api.md)
    {"error": {"code": "AI_TIMEOUT", "message": "...", "request_id": "..."}}

각 영역은 HTTPException 대신 AppError 를 raise 한다.
    raise AppError(404, ErrorCode.CONVERSATION_NOT_FOUND, "대화를 찾을 수 없어요.")
"""

import logging
from enum import StrEnum

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import log_event
from app.core.middleware import REQUEST_ID_HEADER


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


def error_response(
    request: Request, status_code: int, code: ErrorCode, message: str
) -> JSONResponse:
    # 500 응답은 RequestIdMiddleware 바깥에서 나가므로 헤더를 여기서도 붙인다.
    request_id = getattr(request.state, "request_id", None)
    headers = {REQUEST_ID_HEADER: request_id} if request_id else None
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "request_id": request_id}},
        headers=headers,
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
    # 스택 트레이스는 서버 로그에만 남기고 사용자에게는 보내지 않는다.
    log_event("unhandled_error", level=logging.ERROR, error_type=type(exc).__name__)
    logging.getLogger("easyexplain").exception("unhandled exception")
    message = "일시적인 오류가 발생했어요. 잠시 후 다시 시도해 주세요."
    return error_response(request, 500, ErrorCode.INTERNAL_ERROR, message)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(Exception, _handle_unexpected)

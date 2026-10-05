import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import internal_error_response, log_unexpected_error
from app.core.logging import REQUEST_ID_HEADER, log_event, request_id_var


class RequestIdMiddleware:
    """요청마다 서버가 request_id 를 발급하고, request_received/request_completed 를 기록한다.

    클라이언트가 보낸 request_id 는 신뢰하지 않는다. 응답 헤더 X-Request-ID 로 돌려준다.
    예상하지 못한 오류도 여기서 500 응답으로 끝낸다. (request_id 가 살아 있는 곳에서 기록하기 위해)
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_code = 500
        response_started = False

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_started = True
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        log_event("request_received", method=scope["method"], path=scope["path"])
        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception as exc:
            # 다시 raise 하지 않는다. raise 하면 uvicorn 이 예외 메시지 원문을 로그에 남긴다.
            log_unexpected_error(exc)
            if not response_started:
                await internal_error_response(request_id)(scope, receive, send_with_request_id)
        finally:
            latency_ms = round((time.perf_counter() - started) * 1000)
            log_event("request_completed", status=status_code, latency_ms=latency_ms)
            request_id_var.reset(token)

"""AI 호출 횟수를 앱 메모리에 센다. worker·인스턴스 1개에서만 정확하다. (EE-16)"""

from collections import deque
from datetime import UTC, date, datetime
from threading import Lock
from time import monotonic
from typing import Annotated

from fastapi import Depends, Request

from app.core.deps import SettingsDep
from app.core.errors import AppError, ErrorCode


def _today_utc() -> date:
    return datetime.now(UTC).date()


class ChatRateLimiter:
    def __init__(self, user_requests_per_minute: int, daily_request_limit: int) -> None:
        self._user_limit = user_requests_per_minute
        self._daily_limit = daily_request_limit
        self._user_calls: dict[int, deque[float]] = {}
        self._day: date | None = None
        self._daily_count = 0
        self._lock = Lock()

    def check_and_count(self, user_id: int) -> None:
        # 검사와 증가를 한 번에 해야 다른 사용자의 동시 요청도 하루 한도를 넘지 않는다.
        with self._lock:
            now = monotonic()
            today = _today_utc()
            if today != self._day:
                self._day = today
                self._daily_count = 0

            # 최근 60초만 남긴다. 오래된 사용자도 지워 메모리가 계속 쌓이지 않게 한다.
            for previous_user, calls in list(self._user_calls.items()):
                while calls and calls[0] <= now - 60:
                    calls.popleft()
                if not calls:
                    del self._user_calls[previous_user]

            calls = self._user_calls.get(user_id)
            user_count = len(calls) if calls is not None else 0
            if user_count >= self._user_limit or self._daily_count >= self._daily_limit:
                raise AppError(
                    429,
                    ErrorCode.RATE_LIMITED,
                    "질문 요청 한도를 초과했어요. 잠시 후 다시 시도해 주세요.",
                )

            if calls is None:
                calls = deque()
                self._user_calls[user_id] = calls
            calls.append(now)
            self._daily_count += 1


_creation_lock = Lock()


def get_rate_limiter(request: Request, settings: SettingsDep) -> ChatRateLimiter:
    # 앱마다 한 객체를 공유한다. 새 앱·서버 프로세스로 재시작하면 횟수는 초기화된다.
    # 여러 요청이 처음 들어와도 limiter가 두 개 만들어지지 않게 생성만 잠근다.
    with _creation_lock:
        limiter = getattr(request.app.state, "chat_rate_limiter", None)
        if limiter is None:
            limiter = ChatRateLimiter(
                settings.user_requests_per_minute, settings.daily_request_limit
            )
            request.app.state.chat_rate_limiter = limiter
    return limiter


RateLimiterDep = Annotated[ChatRateLimiter, Depends(get_rate_limiter)]

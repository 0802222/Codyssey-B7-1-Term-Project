"""시계를 직접 바꿔 60초·UTC 날짜·동시 집계 경계를 확인한다. (EE-16)"""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import Barrier
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request

from app.chat import rate_limit
from app.chat.rate_limit import ChatRateLimiter
from app.core.errors import AppError, ErrorCode


@pytest.fixture
def clock(monkeypatch):
    clock = SimpleNamespace(seconds=100.0, day=date(2026, 10, 8))
    monkeypatch.setattr(rate_limit, "monotonic", lambda: clock.seconds)
    monkeypatch.setattr(rate_limit, "_today_utc", lambda: clock.day)
    return clock


def _assert_limited(limiter, user_id):
    with pytest.raises(AppError) as caught:
        limiter.check_and_count(user_id)
    error = caught.value
    assert (error.status_code, error.code) == (429, ErrorCode.RATE_LIMITED)
    assert error.message


def test_user_can_use_exactly_the_minute_limit(clock):
    limiter = ChatRateLimiter(user_requests_per_minute=3, daily_request_limit=100)

    for _ in range(3):
        assert limiter.check_and_count(1) is None

    _assert_limited(limiter, 1)


def test_minute_limit_is_separate_for_each_user(clock):
    limiter = ChatRateLimiter(user_requests_per_minute=1, daily_request_limit=100)
    limiter.check_and_count(1)

    _assert_limited(limiter, 1)
    limiter.check_and_count(2)


def test_sliding_window_expires_each_request_at_exactly_60_seconds(clock):
    limiter = ChatRateLimiter(user_requests_per_minute=2, daily_request_limit=100)
    limiter.check_and_count(1)
    clock.seconds = 110
    limiter.check_and_count(1)

    clock.seconds = 159.999
    _assert_limited(limiter, 1)
    clock.seconds = 160
    limiter.check_and_count(1)
    clock.seconds = 169.999
    _assert_limited(limiter, 1)
    clock.seconds = 170
    limiter.check_and_count(1)


def test_daily_limit_sums_all_users_and_does_not_reset_after_60_seconds(clock):
    limiter = ChatRateLimiter(user_requests_per_minute=10, daily_request_limit=2)
    limiter.check_and_count(1)
    limiter.check_and_count(2)

    clock.seconds += 60
    _assert_limited(limiter, 3)
    clock.day += timedelta(days=1)
    limiter.check_and_count(3)


def test_utc_midnight_resets_daily_count_but_preserves_user_window(clock):
    limiter = ChatRateLimiter(user_requests_per_minute=1, daily_request_limit=1)
    limiter.check_and_count(1)
    clock.day += timedelta(days=1)
    clock.seconds += 1

    _assert_limited(limiter, 1)
    # 사용자 제한으로 거절된 요청이 새 날짜의 전체 한도를 쓰면 다음 호출이 실패한다.
    limiter.check_and_count(2)


def test_minute_rejection_does_not_consume_daily_capacity(clock):
    limiter = ChatRateLimiter(user_requests_per_minute=1, daily_request_limit=2)
    limiter.check_and_count(1)

    _assert_limited(limiter, 1)
    limiter.check_and_count(2)
    _assert_limited(limiter, 3)


def test_daily_rejection_does_not_consume_user_capacity(clock):
    limiter = ChatRateLimiter(user_requests_per_minute=1, daily_request_limit=1)
    limiter.check_and_count(1)
    _assert_limited(limiter, 2)

    clock.day += timedelta(days=1)
    clock.seconds += 1
    limiter.check_and_count(2)


def test_repeated_rejections_do_not_extend_the_user_window(clock):
    limiter = ChatRateLimiter(user_requests_per_minute=1, daily_request_limit=100)
    limiter.check_and_count(1)
    for elapsed in [1, 20, 59.999]:
        clock.seconds = 100 + elapsed
        _assert_limited(limiter, 1)

    clock.seconds = 160
    limiter.check_and_count(1)


def test_expired_users_are_removed_from_memory(clock):
    limiter = ChatRateLimiter(user_requests_per_minute=1, daily_request_limit=100)
    for user_id in range(20):
        limiter.check_and_count(user_id)
    clock.seconds += 60

    limiter.check_and_count(99)

    # 만료 기록을 남기면 사용자 수에 비례해 메모리가 계속 늘어난다.
    assert set(limiter._user_calls) == {99}


@pytest.mark.parametrize("same_user", [True, False], ids=["user-minute", "global-day"])
def test_simultaneous_threads_cannot_exceed_either_limit(clock, same_user):
    limiter = ChatRateLimiter(
        user_requests_per_minute=7 if same_user else 100,
        daily_request_limit=100 if same_user else 7,
    )
    ready = Barrier(20)

    def try_request(index):
        ready.wait(timeout=5)
        try:
            limiter.check_and_count(1 if same_user else index)
            return True
        except AppError as error:
            assert (error.status_code, error.code) == (429, ErrorCode.RATE_LIMITED)
            return False

    with ThreadPoolExecutor(max_workers=20) as pool:
        allowed = list(pool.map(try_request, range(20)))

    assert sum(allowed) == 7


def test_dependency_shares_one_counter_per_app(clock, settings):
    settings.user_requests_per_minute = 1
    first_app, second_app = FastAPI(), FastAPI()
    first_request = Request({"type": "http", "app": first_app})
    second_request = Request({"type": "http", "app": second_app})

    first = rate_limit.get_rate_limiter(first_request, settings)
    repeated = rate_limit.get_rate_limiter(first_request, settings)
    second = rate_limit.get_rate_limiter(second_request, settings)

    assert first is repeated
    assert second is not first
    first.check_and_count(1)
    _assert_limited(repeated, 1)
    second.check_and_count(1)


def test_dependency_initialization_is_shared_between_threads(clock, settings):
    app = FastAPI()
    ready = Barrier(20)

    def get_shared_counter(_index):
        ready.wait(timeout=5)
        request = Request({"type": "http", "app": app})
        return rate_limit.get_rate_limiter(request, settings)

    with ThreadPoolExecutor(max_workers=20) as pool:
        counters = list(pool.map(get_shared_counter, range(20)))

    assert all(counter is counters[0] for counter in counters)

"""배포 HTTP API로 수준별 질문·후속 질문·저장을 확인한다. (EE-23)

수집 완료는 AI 품질 판정이나 서버 로그 확인을 뜻하지 않는다.
실제 실행: uv run python -m app.chat.deployment_check --live --base-url URL --output PATH
"""

import argparse
import json
import logging
import math
import os
import secrets
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx

from app.chat.quality_check import SAMPLE_PLAN
from app.chat.schemas import ChatResponse
from app.core.errors import ErrorCode


class _CheckFailed(Exception):
    """응답·예외 원문 대신 공개해도 되는 실패 분류만 전달한다."""

    def __init__(self, reason: str, code: str | None = None):
        self.reason = reason
        self.code = code


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _base_url(value: str) -> str:
    parsed = urlsplit(value)
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if (
        not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or (parsed.scheme != "https" and not (parsed.scheme == "http" and local))
    ):
        raise ValueError("HTTPS 배포 주소 또는 로컬 테스트 주소를 사용해 주세요.")
    # 잘못된 포트도 파일을 만들거나 요청하기 전에 거부한다.
    _ = parsed.port
    return value.rstrip("/")


def _checkpoint(output: Path, report: dict) -> None:
    # 임시 파일을 완성한 뒤 교체해, 중단돼도 앞서 수집한 사례를 보존한다.
    temporary = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output.parent, delete=False
        ) as file:
            temporary = Path(file.name)
            json.dump(report, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _request_id(value: object) -> str | None:
    # 서버가 발급하는 32자리 추적 ID만 기록한다. 임의 헤더·문자열은 저장하지 않는다.
    if isinstance(value, str) and len(value) == 32 and all(c in "0123456789abcdef" for c in value):
        return value
    return None


def _send(
    client: httpx.Client,
    report: dict,
    step: str,
    method: str,
    path: str,
    expected: int = 200,
    **kwargs,
) -> dict:
    check = {"step": step, "started_at": _now(), "http_status": None, "request_id": None}
    report["checks"].append(check)
    started = time.perf_counter()
    try:
        response = client.request(method, path, **kwargs)
    except httpx.TimeoutException:
        # 클라이언트 대기 실패만으로 서버의 AI_TIMEOUT·실패 저장을 단정하지 않는다.
        check["outcome"] = "unconfirmed"
        raise _CheckFailed("CLIENT_TIMEOUT") from None
    except httpx.RequestError:
        check["outcome"] = "unconfirmed"
        raise _CheckFailed("TRANSPORT_ERROR") from None
    finally:
        check["elapsed_seconds"] = round(time.perf_counter() - started, 3)

    check["http_status"] = response.status_code
    check["request_id"] = _request_id(response.headers.get("x-request-id"))
    try:
        data = {} if response.status_code == 204 else response.json()
    except ValueError:
        raise _CheckFailed("INVALID_RESPONSE") from None
    if not isinstance(data, dict):
        raise _CheckFailed("INVALID_RESPONSE")
    check["body_request_id"] = _request_id(data.get("request_id"))
    error = data.get("error")
    if isinstance(error, dict):
        check["body_request_id"] = _request_id(error.get("request_id"))
        code = error.get("code")
        check["error_code"] = code if isinstance(code, str) and code in set(ErrorCode) else None
    if response.status_code != expected:
        if expected == 504 and response.status_code == 200:
            raise _CheckFailed("UNEXPECTED_SUCCESS")
        raise _CheckFailed("HTTP_ERROR", check.get("error_code"))
    if check["request_id"] is None:
        raise _CheckFailed("MISSING_REQUEST_ID")
    return data


def _stored_turn(
    client: httpx.Client, report: dict, case: dict, *, expected_status: str | None = None
) -> None:
    detail = _send(
        client,
        report,
        f"history:{case['id']}",
        "GET",
        f"/api/conversations/{case['conversation_id']}",
    )
    turns = detail.get("turns")
    if not isinstance(turns, list):
        raise _CheckFailed("INVALID_RESPONSE")
    matches = [
        turn
        for turn in turns
        if isinstance(turn, dict)
        and (
            turn.get("id") == case.get("turn_id")
            if case.get("turn_id") is not None
            else turn.get("question") == case["question"] and turn.get("level") == case["level"]
        )
    ]
    fields = ("conversation_id", "level", "question", "answer")
    if len(matches) != 1 or any(matches[0].get(field) != case[field] for field in fields):
        raise _CheckFailed("STORED_TURN_MISMATCH")
    status = expected_status or case["status"]
    if matches[0].get("status") != status:
        raise _CheckFailed("STORED_TURN_MISMATCH")
    if matches[0].get("error_code") != case.get("error_code"):
        raise _CheckFailed("STORED_TURN_MISMATCH")
    turn_id = matches[0].get("id")
    if type(turn_id) is not int or turn_id <= 0:
        raise _CheckFailed("INVALID_RESPONSE")
    case["turn_id"] = turn_id
    case["status"] = status
    case["storage_verified"] = True
    case["stored_turn_count"] = len(turns)


def _timeout_result(data: dict, report: dict) -> str:
    error = data.get("error")
    if not isinstance(error, dict) or (
        error.get("code") != "AI_TIMEOUT"
        or error.get("message") != "응답이 지연되고 있어요. 잠시 후 다시 시도해 주세요."
        or _request_id(error.get("request_id")) != report["checks"][-1]["request_id"]
    ):
        raise _CheckFailed("TIMEOUT_RESPONSE_MISMATCH")
    return error["request_id"]


def collect_samples(
    base_url: str,
    output: Path,
    *,
    expect_timeout: bool = False,
    check_recovery: bool = False,
    timeout_seconds: float = 60,
    transport: httpx.BaseTransport | None = None,
) -> dict:
    """자동 재전송 없이, 공개 가능한 증빙만 단계별로 저장한다."""
    if expect_timeout and check_recovery:
        raise ValueError("시간 초과와 복구 검증은 따로 실행해 주세요.")
    base_url = _base_url(base_url)
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("HTTP 대기 시간은 0보다 커야 합니다.")
    # 이미 확인한 수준별 질문은 반복하지 않고, 복구 후 정상 질문 한 건만 확인한다.
    plan = SAMPLE_PLAN[:1] if expect_timeout or check_recovery else SAMPLE_PLAN
    scenario = "levels_and_followups"
    if expect_timeout:
        scenario = "timeout"
    elif check_recovery:
        scenario = "recovery"
    report = {
        "source": "mock_http" if transport is not None else "remote_http",
        "scenario": scenario,
        "max_new_questions": len(plan),
        "base_url": base_url,
        "collection_status": "incomplete",
        "quality_review": "not_performed",
        "started_at": _now(),
        "finished_at": None,
        "http_timeout_seconds": timeout_seconds,
        "server_runtime": {
            "provider": "not_verified",
            "model": "not_exposed",
            "deploy_commit": "not_verified",
            "server_logs": "not_verified",
            "gateway_quota": "not_verified",
        },
        "checks": [],
        "cases": [],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    # 배타적으로 새 파일만 만든다. 기존 기록은 보존하고 파일 권한은 600으로 제한한다.
    descriptor = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
        file.write("\n")

    # 합성 계정의 이메일·비밀번호·Cookie·CSRF는 메모리에만 둔다.
    credentials = {
        "email": f"ee23-{uuid4().hex}@example.com",
        "password": secrets.token_urlsafe(24),
    }
    previous_disable = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    current_case = None
    logged_in = False
    try:
        with httpx.Client(
            base_url=base_url,
            headers={"Origin": base_url},
            timeout=timeout_seconds,
            follow_redirects=False,
            transport=transport,
        ) as client:
            try:
                health = _send(client, report, "health:before", "GET", "/health")
                if health != {"status": "ok", "db": "ok"}:
                    raise _CheckFailed("HEALTH_FAILED")
                _send(client, report, "signup", "POST", "/api/auth/signup", 201, json=credentials)
                login = _send(client, report, "login", "POST", "/api/auth/login", json=credentials)
                csrf = login.get("csrf_token")
                if not isinstance(csrf, str) or not csrf:
                    raise _CheckFailed("INVALID_RESPONSE")
                client.headers["X-CSRF-Token"] = csrf
                logged_in = True
                conversations = {}
                for case_id, alias, level, question in plan:
                    if alias not in conversations:
                        conversation = _send(
                            client,
                            report,
                            f"conversation:{alias}",
                            "POST",
                            "/api/conversations",
                            201,
                            json={},
                        )
                        try:
                            conversations[alias] = str(UUID(conversation["id"]))
                        except (KeyError, TypeError, ValueError):
                            raise _CheckFailed("INVALID_RESPONSE") from None
                    current_case = {
                        "id": case_id,
                        "conversation_alias": alias,
                        "conversation_id": conversations[alias],
                        "level": level,
                        "question": question,
                        "answer": None,
                        "status": "unconfirmed",
                        "storage_verified": False,
                    }
                    report["cases"].append(current_case)
                    _checkpoint(output, report)
                    body = {
                        "conversation_id": conversations[alias],
                        "level": level,
                        "question": question,
                        "client_request_id": str(uuid4()),
                    }
                    if expect_timeout:
                        data = _send(
                            client, report, f"chat:{case_id}", "POST", "/api/chat", 504, json=body
                        )
                        current_case.update(
                            {
                                "error_code": "AI_TIMEOUT",
                                "request_id": _timeout_result(data, report),
                            }
                        )
                        _stored_turn(client, report, current_case, expected_status="failed")
                        count = current_case["stored_turn_count"]
                        replay = _send(
                            client, report, f"replay:{case_id}", "POST", "/api/chat", 504, json=body
                        )
                        _timeout_result(replay, report)
                        _stored_turn(client, report, current_case)
                        if current_case["stored_turn_count"] != count:
                            raise _CheckFailed("REPLAY_CREATED_TURN")
                        current_case["replay_verified"] = True
                        current_case["replay_ai_call_count"] = "server_logs_required"
                        _checkpoint(output, report)
                        continue
                    data = _send(client, report, f"chat:{case_id}", "POST", "/api/chat", json=body)
                    try:
                        response = ChatResponse.model_validate(data)
                    except ValueError:
                        raise _CheckFailed("INVALID_RESPONSE") from None
                    if (
                        str(response.conversation_id) != conversations[alias]
                        or response.level != level
                        or response.question != question
                        or not response.answer.strip()
                        or _request_id(response.request_id) != report["checks"][-1]["request_id"]
                    ):
                        raise _CheckFailed("CHAT_RESPONSE_MISMATCH")
                    current_case.update(
                        {
                            "answer": response.answer,
                            "status": response.status,
                            "turn_id": response.turn_id,
                            "request_id": response.request_id,
                        }
                    )
                    _stored_turn(client, report, current_case)
                    if case_id == SAMPLE_PLAN[0][0]:
                        replay = _send(
                            client, report, f"replay:{case_id}", "POST", "/api/chat", json=body
                        )
                        if (
                            replay != data
                            or report["checks"][-1]["request_id"] == response.request_id
                        ):
                            raise _CheckFailed("REPLAY_MISMATCH")
                        count = current_case["stored_turn_count"]
                        _stored_turn(client, report, current_case)
                        if current_case["stored_turn_count"] != count:
                            raise _CheckFailed("REPLAY_CREATED_TURN")
                        current_case["replay_verified"] = True
                        current_case["replay_ai_call_count"] = "server_logs_required"
                    _checkpoint(output, report)
                health = _send(client, report, "health:after", "GET", "/health")
                if health != {"status": "ok", "db": "ok"}:
                    raise _CheckFailed("HEALTH_FAILED")
                report["collection_status"] = "completed"
            except _CheckFailed as exc:
                report["failure"] = {"reason": exc.reason, "error_code": exc.code}
                if current_case is not None and current_case["status"] == "unconfirmed":
                    if exc.reason == "UNEXPECTED_SUCCESS":
                        current_case["status"] = "unexpected_success"
                    elif exc.reason == "HTTP_ERROR":
                        # API 실패와 DB 턴의 상태는 다르다. 저장 조회 없이는 확정하지 않는다.
                        current_case["request_outcome"] = "failed"
            finally:
                if logged_in:
                    try:
                        _send(client, report, "logout", "POST", "/api/auth/logout", 204)
                        report["logout_status"] = "completed"
                    except _CheckFailed:
                        report["logout_status"] = "unconfirmed"
                report["finished_at"] = _now()
                _checkpoint(output, report)
    finally:
        logging.disable(previous_disable)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="EE-23 배포 API 확인: 기본 질문 5개, 시간 초과·복구 질문 1개"
    )
    parser.add_argument("--live", action="store_true", help="실제 배포 AI 호출을 명시적으로 허용")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    scenario = parser.add_mutually_exclusive_group()
    scenario.add_argument(
        "--expect-timeout",
        action="store_true",
        help="운영자가 시간 초과 조건을 준비한 서버에서 한 질문만 확인",
    )
    scenario.add_argument(
        "--check-recovery",
        action="store_true",
        help="운영 설정을 복구한 서버에서 정상 질문 한 건·저장·같은 키 재전송·health 확인",
    )
    args = parser.parse_args(argv)
    if not args.live:
        print("실제 배포를 확인하려면 --live를 지정해 주세요.", file=sys.stderr)
        return 1
    try:
        report = collect_samples(
            args.base_url,
            args.output,
            expect_timeout=args.expect_timeout,
            check_recovery=args.check_recovery,
        )
    except (OSError, ValueError, KeyboardInterrupt):
        print("수집을 중단했습니다. 배포 주소와 새로운 출력 경로를 확인해 주세요.", file=sys.stderr)
        return 1
    if report["collection_status"] != "completed":
        print(
            "수집이 완료되지 않았어요. 완료한 사례와 실패 분류는 보고서에 남겼습니다.",
            file=sys.stderr,
        )
        return 1
    print("배포 API 기록을 저장했습니다. AI 품질·서버 로그·사용 한도는 별도로 확인해 주세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

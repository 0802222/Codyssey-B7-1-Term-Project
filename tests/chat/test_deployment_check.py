"""EE-23 수집기는 모의 HTTP 응답만 사용한다. 실제 배포·AI에는 접속하지 않는다."""

import json
import logging
import stat
from uuid import uuid4

import httpx
import pytest

from app.chat import deployment_check
from app.chat.quality_check import SAMPLE_PLAN

BASE_URL = "https://deployed.example"
PRIVATE = "PRIVATE-RESPONSE-MARKER"


class DeployedAPI:
    """서버 계약 응답과 저장 결과를 독립적으로 준비하는 HTTP 대역."""

    def __init__(self):
        self.requests = []
        self.credentials = None
        self.conversations = {}
        self.saved = {}
        self.ai_calls = 0
        self.chat_bodies = []
        self.fail_on = None
        self.client_timeout_on = None
        self.corrupt_history_on = None
        self.extra_replay_turn = False
        self.bad_timeout_message = False
        self.output = None
        self.checkpoint_statuses = []

    def __call__(self, request):
        self.requests.append(request)
        assert request.headers["Origin"] == BASE_URL
        request_id = uuid4().hex
        path = request.url.path
        body = json.loads(request.content) if request.content else {}
        status = 200
        data = {}
        headers = {"X-Request-ID": request_id, "PRIVATE-HEADER": PRIVATE}
        if request.method == "POST" and path not in {"/api/auth/signup", "/api/auth/login"}:
            assert request.headers["X-CSRF-Token"] == "PRIVATE-CSRF-MARKER"
            assert "PRIVATE-COOKIE-MARKER" in request.headers["Cookie"]
        if path == "/health":
            data = {"status": "ok", "db": "ok"}
        elif path == "/api/auth/signup":
            self.credentials = body
            status = 201
            data = {"id": 777, "email": body["email"], "private": PRIVATE}
        elif path == "/api/auth/login":
            assert body == self.credentials
            data = {
                "user": {"id": 777, "email": body["email"]},
                "csrf_token": "PRIVATE-CSRF-MARKER",
                "private": PRIVATE,
            }
            headers["Set-Cookie"] = "session=PRIVATE-COOKIE-MARKER; Secure; Path=/"
        elif path == "/api/conversations":
            conversation_id = str(uuid4())
            self.conversations[conversation_id] = []
            data = {"id": conversation_id, "title": "새 대화", "private": PRIVATE}
            status = 201
        elif path == "/api/chat":
            self.chat_bodies.append(body)
            key = body["client_request_id"]
            if key not in self.saved:
                self.ai_calls += 1
                if self.output is not None:
                    self.checkpoint_statuses.append(
                        [case["status"] for case in json.loads(self.output.read_text())["cases"]]
                    )
                if self.ai_calls == self.client_timeout_on:
                    raise httpx.ReadTimeout(PRIVATE, request=request)
                turn = {
                    "id": self.ai_calls,
                    "conversation_id": body["conversation_id"],
                    "level": body["level"],
                    "question": body["question"],
                    "answer": f"설명 {self.ai_calls}",
                    "status": "completed",
                    "error_code": None,
                    "created_at": "2026-10-09T13:00:00Z",
                }
                if self.ai_calls == self.fail_on:
                    turn.update(answer=None, status="failed", error_code="AI_TIMEOUT")
                self.conversations[body["conversation_id"]].append(turn)
                self.saved[key] = {**turn, "turn_id": turn["id"], "request_id": request_id}
            elif self.extra_replay_turn:
                self.conversations[body["conversation_id"]].append(
                    {**self.conversations[body["conversation_id"]][0], "id": 999}
                )
            saved = self.saved[key]
            if saved["status"] == "failed":
                status = 504
                data = {
                    "error": {
                        "code": "AI_TIMEOUT",
                        "request_id": request_id,
                        "message": PRIVATE
                        if self.bad_timeout_message
                        else "응답이 지연되고 있어요. 잠시 후 다시 시도해 주세요.",
                        "private": PRIVATE,
                    }
                }
            else:
                data = {**saved, "private": PRIVATE}
        elif path.startswith("/api/conversations/"):
            conversation_id = path.rsplit("/", 1)[-1]
            turns = [dict(turn) for turn in self.conversations[conversation_id]]
            if self.ai_calls == self.corrupt_history_on:
                turns[-1]["answer"] = "잘못 저장된 답변"
            data = {"conversation": {"id": conversation_id}, "turns": turns, "private": PRIVATE}
        elif path == "/api/auth/logout":
            status = 204
        else:
            pytest.fail("계약에 없는 요청")
        return httpx.Response(status, json=data if status != 204 else None, headers=headers)


def collect(api, output, **kwargs):
    api.output = output
    return deployment_check.collect_samples(
        BASE_URL, output, transport=httpx.MockTransport(api), **kwargs
    )


def test_levels_followups_replay_and_actual_stored_answers_are_checked(tmp_path):
    api = DeployedAPI()
    output = tmp_path / "samples.json"
    report = collect(api, output)

    assert report["collection_status"] == "completed"
    assert report["source"] == "mock_http"
    assert report["quality_review"] == "not_performed"
    assert api.ai_calls == 5
    assert len(api.chat_bodies) == 6
    assert api.chat_bodies[0] == api.chat_bodies[1]
    cases = report["cases"]
    assert [case["id"] for case in cases] == [case[0] for case in SAMPLE_PLAN]
    assert [case["level"] for case in cases] == [case[2] for case in SAMPLE_PLAN]
    assert [case["question"] for case in cases] == [case[3] for case in SAMPLE_PLAN]
    assert len({case["conversation_id"] for case in cases[:3]}) == 3
    assert cases[2]["conversation_id"] == cases[3]["conversation_id"] == cases[4]["conversation_id"]
    assert all(case["status"] == "completed" and case["storage_verified"] for case in cases)
    assert cases[0]["replay_verified"] is True
    assert cases[0]["replay_ai_call_count"] == "server_logs_required"
    replay = next(check for check in report["checks"] if check["step"] == "replay:A-easy")
    assert replay["body_request_id"] == cases[0]["request_id"]
    assert replay["request_id"] != replay["body_request_id"]
    assert report["logout_status"] == "completed"
    assert all(value.startswith("not_") for value in report["server_runtime"].values())
    assert json.loads(output.read_text()) == report
    # 다음 요청을 하기 전에 지금까지의 완료·현재 미확인 상태가 파일에 남는다.
    assert api.checkpoint_statuses == [
        ["unconfirmed"],
        ["completed", "unconfirmed"],
        ["completed", "completed", "unconfirmed"],
        ["completed", "completed", "completed", "unconfirmed"],
        ["completed", "completed", "completed", "completed", "unconfirmed"],
    ]


def test_credentials_cookie_debug_fields_and_exception_text_are_not_exported(tmp_path, caplog):
    api = DeployedAPI()
    output = tmp_path / "safe.json"
    previous_disable = logging.root.manager.disable
    with caplog.at_level(logging.DEBUG):
        collect(api, output)
    text = output.read_text() + caplog.text
    for secret in [
        PRIVATE,
        "PRIVATE-CSRF-MARKER",
        "PRIVATE-COOKIE-MARKER",
        api.credentials["email"],
        api.credentials["password"],
        "Set-Cookie",
        "password_hash",
        "csrf_token",
    ]:
        assert secret not in text
    assert api.credentials["email"].startswith("ee23-")
    assert api.credentials["email"].endswith("@example.com")
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert logging.root.manager.disable == previous_disable


def test_http_failure_stops_without_retry_and_keeps_completed_cases(tmp_path):
    api = DeployedAPI()
    api.fail_on = 3
    report = collect(api, tmp_path / "failed.json")

    assert report["collection_status"] == "incomplete"
    assert report["failure"] == {"reason": "HTTP_ERROR", "error_code": "AI_TIMEOUT"}
    assert [case["status"] for case in report["cases"]] == ["completed", "completed", "unconfirmed"]
    assert report["cases"][-1]["request_outcome"] == "failed"
    assert api.ai_calls == 3
    assert len(api.chat_bodies) == 4  # 첫 성공의 명시적 재전송 외에 자동 재시도는 없다.
    assert report["cases"][0]["storage_verified"] is True
    assert report["cases"][-1]["storage_verified"] is False


def test_client_read_timeout_is_unconfirmed_not_server_ai_timeout(tmp_path):
    api = DeployedAPI()
    api.client_timeout_on = 3
    output = tmp_path / "client-timeout.json"
    report = collect(api, output)

    assert report["collection_status"] == "incomplete"
    assert report["failure"] == {"reason": "CLIENT_TIMEOUT", "error_code": None}
    assert report["cases"][-1]["status"] == "unconfirmed"
    assert api.ai_calls == 3
    assert "AI_TIMEOUT" not in output.read_text()
    assert PRIVATE not in output.read_text()


def test_storage_mismatch_prevents_completion(tmp_path):
    api = DeployedAPI()
    api.corrupt_history_on = 2
    report = collect(api, tmp_path / "mismatch.json")

    assert report["failure"]["reason"] == "STORED_TURN_MISMATCH"
    assert report["collection_status"] == "incomplete"
    assert report["cases"][0]["storage_verified"] is True
    assert report["cases"][1]["storage_verified"] is False
    assert api.ai_calls == 2


def test_replay_cannot_silently_create_another_turn(tmp_path):
    api = DeployedAPI()
    api.extra_replay_turn = True
    report = collect(api, tmp_path / "duplicate.json")

    assert report["failure"]["reason"] == "REPLAY_CREATED_TURN"
    assert report["collection_status"] == "incomplete"
    assert api.ai_calls == 1


def test_controlled_timeout_checks_message_failure_storage_replay_and_health(tmp_path):
    api = DeployedAPI()
    api.fail_on = 1
    report = collect(api, tmp_path / "server-timeout.json", expect_timeout=True)

    assert report["collection_status"] == "completed"
    assert report["scenario"] == "timeout"
    assert len(report["cases"]) == 1
    case = report["cases"][0]
    assert case["status"] == "failed"
    assert case["error_code"] == "AI_TIMEOUT"
    assert case["answer"] is None
    assert case["storage_verified"] is True
    assert case["replay_verified"] is True
    assert case["stored_turn_count"] == 1
    assert api.ai_calls == 1
    assert len(api.chat_bodies) == 2
    assert [
        check["http_status"] for check in report["checks"] if check["step"].startswith("health:")
    ] == [200, 200]


def test_timeout_scenario_stops_on_success_without_running_five_more_questions(tmp_path):
    api = DeployedAPI()
    report = collect(api, tmp_path / "unexpected.json", expect_timeout=True)

    assert report["collection_status"] == "incomplete"
    assert report["failure"]["reason"] == "UNEXPECTED_SUCCESS"
    assert report["cases"][0]["status"] == "unexpected_success"
    assert api.ai_calls == 1
    assert len(api.chat_bodies) == 1


def test_timeout_message_must_match_contract(tmp_path):
    api = DeployedAPI()
    api.fail_on = 1
    api.bad_timeout_message = True
    output = tmp_path / "wrong-message.json"
    report = collect(api, output, expect_timeout=True)

    assert report["failure"]["reason"] == "TIMEOUT_RESPONSE_MISMATCH"
    assert report["collection_status"] == "incomplete"
    assert report["cases"][0]["storage_verified"] is False
    assert PRIVATE not in output.read_text()


def test_server_timeout_without_matching_stored_failure_is_unconfirmed(tmp_path):
    api = DeployedAPI()
    api.fail_on = 1
    api.corrupt_history_on = 1
    report = collect(api, tmp_path / "failure-not-saved.json", expect_timeout=True)

    assert report["failure"]["reason"] == "STORED_TURN_MISMATCH"
    assert report["cases"][0]["status"] == "unconfirmed"
    assert report["cases"][0]["storage_verified"] is False


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_invalid_wait_time_is_rejected_without_creating_output(tmp_path, timeout):
    api = DeployedAPI()
    output = tmp_path / "invalid-timeout.json"
    with pytest.raises(ValueError):
        collect(api, output, timeout_seconds=timeout)
    assert api.requests == []
    assert not output.exists()


def test_existing_output_is_preserved_without_any_http_request(tmp_path):
    api = DeployedAPI()
    output = tmp_path / "existing.json"
    output.write_text("original evidence")
    with pytest.raises(FileExistsError):
        collect(api, output)
    assert api.requests == []
    assert output.read_text() == "original evidence"


@pytest.mark.parametrize(
    "url",
    [
        "http://deployed.example",
        "https://user:secret@deployed.example",
        "https://deployed.example?key=secret",
        "https://deployed.example#secret",
        "https://deployed.example/api",
        "https://deployed.example:INVALID",
        "file:///tmp",
    ],
)
def test_unsafe_url_is_rejected_before_creating_output_or_request(url, tmp_path):
    calls = []
    output = tmp_path / "unsafe.json"
    with pytest.raises(ValueError):
        deployment_check.collect_samples(url, output, transport=httpx.MockTransport(calls.append))
    assert calls == []
    assert not output.exists()


@pytest.mark.parametrize(
    "url", ["http://localhost:8000", "http://127.0.0.1:8000", "http://[::1]:8000"]
)
def test_local_http_is_allowed_only_for_testing(url):
    assert deployment_check._base_url(url + "/") == url


def test_redirect_is_not_followed_or_secret_response_saved(tmp_path):
    requests = []

    def redirect(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://other.example"}, text=PRIVATE)

    output = tmp_path / "redirect.json"
    report = deployment_check.collect_samples(
        BASE_URL, output, transport=httpx.MockTransport(redirect)
    )
    assert report["collection_status"] == "incomplete"
    assert len(requests) == 1
    assert PRIVATE not in output.read_text()


def test_cli_requires_live_without_creating_output(tmp_path, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("실제 수집기를 부르면 안 됨")

    monkeypatch.setattr(deployment_check, "collect_samples", forbidden)
    output = tmp_path / "not-created.json"
    result = deployment_check.main(["--base-url", BASE_URL, "--output", str(output)])
    assert result == 1
    assert "--live" in capsys.readouterr().err
    assert not output.exists()


def test_cli_forwards_timeout_scenario_and_reports_incomplete_safely(tmp_path, monkeypatch, capsys):
    calls = []

    def stopped(base_url, output, *, expect_timeout):
        calls.append((base_url, output, expect_timeout))
        return {"collection_status": "incomplete"}

    monkeypatch.setattr(deployment_check, "collect_samples", stopped)
    output = tmp_path / "cli.json"
    result = deployment_check.main(
        ["--live", "--base-url", BASE_URL, "--output", str(output), "--expect-timeout"]
    )
    assert result == 1
    assert calls == [(BASE_URL, output, True)]
    assert "완료되지" in capsys.readouterr().err

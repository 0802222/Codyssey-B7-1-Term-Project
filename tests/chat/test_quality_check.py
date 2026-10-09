"""품질 수집기는 실제 키·네트워크 없이 주입한 provider로 검증한다."""

import asyncio
import json
import logging

import pytest
from pydantic import SecretStr

from app.chat import quality_check
from app.chat.fake_provider import FakeAIProvider
from app.chat.provider import AIResult, AITimeoutError
from app.core.config import Settings


class SpyProvider:
    def __init__(self):
        self.calls = []
        self.fail_on = None
        self.error = AITimeoutError("PRIVATE-PROVIDER-ERROR-MARKER")
        self.checkpoint = None
        self.previous_case_counts = []

    async def generate_reply(self, messages, *, system, timeout_seconds, max_output_tokens):
        if self.checkpoint is not None:
            previous = json.loads(self.checkpoint.read_text(encoding="utf-8"))
            self.previous_case_counts.append(len(previous["cases"]))
        self.calls.append(
            {
                "messages": [
                    {"role": message.role, "content": message.content} for message in messages
                ],
                "system": system,
            }
        )
        if len(self.calls) == self.fail_on:
            raise self.error
        return AIResult(
            text=f"수집 답변 {len(self.calls)}",
            model="observed-gateway-model",
            input_tokens=10 + len(self.calls),
            output_tokens=20 + len(self.calls),
        )


@pytest.fixture
def quality_settings():
    return Settings(
        _env_file=None,
        app_env="test",
        ai_provider="fake",
        ai_model="requested-model",
        anthropic_api_key=SecretStr("UNUSED-TEST-KEY-MARKER"),
        anthropic_base_url=(
            "https://PRIVATE-URL-USER:PRIVATE-URL-PASSWORD@gateway.example/path"
            "?key=PRIVATE-QUERY-MARKER#PRIVATE-FRAGMENT-MARKER"
        ),
        context_turns=5,
        context_max_chars=12000,
        user_requests_per_minute=10,
        daily_request_limit=200,
    )


def test_plan_uses_three_independent_conversations_then_two_followups(quality_settings, tmp_path):
    provider = SpyProvider()
    output = tmp_path / "samples.json"

    report = asyncio.run(quality_check.collect_samples(quality_settings, provider, output))

    assert report["collection_status"] == "completed"
    assert len(provider.calls) == 5
    assert [case["conversation_alias"] for case in report["cases"]] == ["A", "B", "C", "C", "C"]
    assert [case["level"] for case in report["cases"]] == [
        "easy",
        "beginner",
        "advanced",
        "easy",
        "easy",
    ]
    question = "API가 무엇인지 설명해줘."
    assert [case["question"] for case in report["cases"]] == [
        question,
        question,
        question,
        "더 쉽게",
        "예시 하나 더",
    ]
    assert [len(call["messages"]) for call in provider.calls] == [1, 1, 1, 3, 5]
    assert provider.calls[3]["messages"] == [
        {"role": "user", "content": question},
        {"role": "assistant", "content": "수집 답변 3"},
        {"role": "user", "content": "더 쉽게"},
    ]
    assert provider.calls[4]["messages"] == provider.calls[3]["messages"] + [
        {"role": "assistant", "content": "수집 답변 4"},
        {"role": "user", "content": "예시 하나 더"},
    ]
    assert "현재 설명 수준은 advanced이다" in provider.calls[2]["system"]
    assert "현재 설명 수준은 easy이다" in provider.calls[3]["system"]
    assert json.loads(output.read_text(encoding="utf-8")) == report


def test_report_records_actual_input_models_usage_and_safe_metadata(quality_settings, tmp_path):
    provider = SpyProvider()
    output = tmp_path / "samples.json"

    report = asyncio.run(quality_check.collect_samples(quality_settings, provider, output))

    assert report["requested_model"] == "requested-model"
    assert report["gateway_hostname"] == "gateway.example"
    assert report["quality_review"] == "not_performed"
    for index, sample in enumerate(report["cases"]):
        assert sample["observed_model"] == "observed-gateway-model"
        assert sample["sent_messages"] == provider.calls[index]["messages"]
        assert sample["system_prompt"] == provider.calls[index]["system"]
        assert sample["token_usage"] == {"input_tokens": 11 + index, "output_tokens": 21 + index}
        assert sample["started_at"].endswith("+00:00")
        assert sample["finished_at"].endswith("+00:00")
    assert all(len(digest) == 64 for digest in report["source_sha256"].values())
    text = output.read_text(encoding="utf-8")
    for forbidden in [
        "PRIVATE-",
        "UNUSED-TEST-KEY",
        "user_id",
        "email",
        "password_hash",
        "database_url",
        "env_file",
    ]:
        assert forbidden not in text


def test_each_completed_case_is_checkpointed_before_the_next_call(quality_settings, tmp_path):
    provider = SpyProvider()
    provider.checkpoint = tmp_path / "samples.json"

    asyncio.run(quality_check.collect_samples(quality_settings, provider, provider.checkpoint))

    assert provider.previous_case_counts == [0, 1, 2, 3, 4]


@pytest.mark.parametrize(
    ("error", "code", "error_type"),
    [
        (AITimeoutError("PRIVATE-PROVIDER-ERROR-MARKER"), "AI_TIMEOUT", "AITimeoutError"),
        (RuntimeError("PRIVATE-PROVIDER-ERROR-MARKER"), "INTERNAL_ERROR", "RuntimeError"),
    ],
)
def test_failure_stops_without_retry_and_preserves_completed_samples(
    quality_settings, tmp_path, caplog, error, code, error_type
):
    provider = SpyProvider()
    provider.fail_on = 3
    provider.error = error
    output = tmp_path / "samples.json"

    with caplog.at_level(logging.INFO, logger="easyexplain"):
        report = asyncio.run(quality_check.collect_samples(quality_settings, provider, output))

    assert report["collection_status"] == "incomplete"
    assert len(provider.calls) == 3
    assert [sample["status"] for sample in report["cases"]] == ["completed", "completed", "failed"]
    assert [sample["answer"] for sample in report["cases"]] == ["수집 답변 1", "수집 답변 2", None]
    assert report["cases"][-1]["error"] == {"code": code, "type": error_type}
    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert "PRIVATE-PROVIDER-ERROR-MARKER" not in output.read_text(encoding="utf-8") + caplog.text
    assert "API가 무엇인지 설명해줘." not in caplog.text
    assert "수집 답변" not in caplog.text


def test_existing_output_is_preserved_without_calling_ai(quality_settings, tmp_path):
    output = tmp_path / "existing.json"
    original = '{"keep": true}\n'
    output.write_text(original, encoding="utf-8")
    provider = SpyProvider()

    with pytest.raises(FileExistsError):
        asyncio.run(quality_check.collect_samples(quality_settings, provider, output))

    assert provider.calls == []
    assert output.read_text(encoding="utf-8") == original


def test_fake_collection_is_identified_and_does_not_claim_quality_pass(quality_settings, tmp_path):
    report = asyncio.run(
        quality_check.collect_samples(quality_settings, FakeAIProvider(), tmp_path / "fake.json")
    )

    assert report["provider"] == "fake"
    assert report["collection_status"] == "completed"
    assert report["quality_review"] == "not_performed"
    assert all(sample["observed_model"] == "fake" for sample in report["cases"])
    assert "score" not in report


def test_collection_respects_configured_zero_context(quality_settings, tmp_path):
    quality_settings.context_turns = 0
    provider = SpyProvider()

    report = asyncio.run(
        quality_check.collect_samples(quality_settings, provider, tmp_path / "no-history.json")
    )

    assert report["settings"]["context_turns"] == 0
    assert [len(call["messages"]) for call in provider.calls] == [1, 1, 1, 1, 1]


def test_cli_without_live_does_not_read_settings_or_call_provider(tmp_path, monkeypatch, capsys):
    def forbidden_settings(*args, **kwargs):
        raise AssertionError("Settings를 읽으면 안 된다")

    monkeypatch.setattr(quality_check, "Settings", forbidden_settings)
    output = tmp_path / "guarded.json"

    result = quality_check.main(
        [
            "--env-file",
            str(tmp_path / "unread.env"),
            "--output",
            str(output),
        ]
    )

    assert result == 1
    assert "--live" in capsys.readouterr().err
    assert not output.exists()


@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    # 실제 환경의 키를 쓰지 않는다. provider도 아래 테스트에서 Spy로 교체한다.
    for name, value in {
        "APP_ENV": "test",
        "AI_PROVIDER": "fake",
        "ANTHROPIC_API_KEY": "UNUSED-CLI-TEST-PLACEHOLDER",
        "ANTHROPIC_BASE_URL": "https://gateway.example",
        "AI_MODEL": "requested-model",
    }.items():
        monkeypatch.setenv(name, value)
    env_file = tmp_path / "private-env-marker.env"
    env_file.write_text("AI_PROVIDER=fake\n", encoding="utf-8")
    return env_file


def test_cli_forces_anthropic_selection_and_writes_samples(cli_env, tmp_path, monkeypatch, capsys):
    provider = SpyProvider()
    selected = []

    def select(settings):
        selected.append(settings.ai_provider)
        return provider

    monkeypatch.setattr(quality_check, "get_ai_provider", select)
    output = tmp_path / "live-simulated.json"

    result = quality_check.main(
        [
            "--live",
            "--env-file",
            str(cli_env),
            "--output",
            str(output),
        ]
    )

    assert result == 0
    assert selected == ["anthropic"]
    assert len(provider.calls) == 5
    assert json.loads(output.read_text(encoding="utf-8"))["provider"] == "anthropic"
    console = capsys.readouterr()
    assert "별도로 검토" in console.out
    assert "UNUSED-CLI-TEST-PLACEHOLDER" not in console.out + console.err
    assert str(cli_env) not in output.read_text(encoding="utf-8")


@pytest.mark.parametrize("problem", ["empty-key", "invalid-timeout"])
def test_cli_empty_key_or_invalid_setting_does_not_expose_values(
    cli_env, tmp_path, monkeypatch, capsys, problem
):
    if problem == "empty-key":
        monkeypatch.setenv("ANTHROPIC_API_KEY", " ")
    else:
        monkeypatch.setenv("AI_TIMEOUT_SECONDS", "PRIVATE-INVALID-SETTING-MARKER")
    output = tmp_path / "invalid-settings.json"

    result = quality_check.main(
        [
            "--live",
            "--env-file",
            str(cli_env),
            "--output",
            str(output),
        ]
    )

    assert result == 1
    console = capsys.readouterr()
    assert "AI 설정을 확인" in console.err
    assert "PRIVATE-INVALID-SETTING-MARKER" not in console.err
    assert "Traceback" not in console.err
    assert not output.exists()


def test_cli_existing_output_is_preserved_before_loading_settings(tmp_path, monkeypatch, capsys):
    output = tmp_path / "existing.json"
    output.write_text("keep-existing", encoding="utf-8")

    def forbidden_settings(*args, **kwargs):
        raise AssertionError("기존 출력이 있으면 설정을 읽지 않는다")

    monkeypatch.setattr(quality_check, "Settings", forbidden_settings)
    result = quality_check.main(
        [
            "--live",
            "--env-file",
            str(tmp_path / "unread.env"),
            "--output",
            str(output),
        ]
    )

    assert result == 1
    assert output.read_text(encoding="utf-8") == "keep-existing"
    assert "이미 있어요" in capsys.readouterr().err


def test_cli_failed_sample_returns_one_and_keeps_checkpoint(cli_env, tmp_path, monkeypatch, capsys):
    provider = SpyProvider()
    provider.fail_on = 2
    monkeypatch.setattr(quality_check, "get_ai_provider", lambda settings: provider)
    output = tmp_path / "failed.json"

    result = quality_check.main(
        [
            "--live",
            "--env-file",
            str(cli_env),
            "--output",
            str(output),
        ]
    )

    assert result == 1
    assert len(provider.calls) == 2
    report = json.loads(output.read_text(encoding="utf-8"))
    assert [sample["status"] for sample in report["cases"]] == ["completed", "failed"]
    console = capsys.readouterr()
    assert "PRIVATE-PROVIDER-ERROR-MARKER" not in console.out + console.err
    assert "Traceback" not in console.err


@pytest.mark.parametrize("mode", ["success", "init-error", "sample-error"])
@pytest.mark.parametrize("previous_disable", [logging.NOTSET, logging.WARNING])
def test_cli_blocks_late_sdk_debug_setup_and_restores_logging(
    cli_env, tmp_path, monkeypatch, caplog, capsys, mode, previous_disable
):
    marker = "PRIVATE-REQUEST-OPTIONS-MARKER"
    loggers = [logging.getLogger(name) for name in ("anthropic", "httpx2")]
    original_levels = [logger.level for logger in loggers]
    original_disable = logging.root.manager.disable

    def sdk_debug_setup():
        # ANTHROPIC_LOG=debug의 최초 SDK import와, 이후 설정 변경을 재현한다.
        for logger in loggers:
            logger.setLevel(logging.DEBUG)
            logger.debug("Request options: %s", marker)

    class NoisyProvider(SpyProvider):
        async def generate_reply(self, *args, **kwargs):
            sdk_debug_setup()
            return await super().generate_reply(*args, **kwargs)

    provider = NoisyProvider()
    if mode == "sample-error":
        provider.fail_on = 1

    def select(settings):
        sdk_debug_setup()
        if mode == "init-error":
            raise RuntimeError(marker)
        return provider

    monkeypatch.setenv("ANTHROPIC_LOG", "debug")
    monkeypatch.setattr(quality_check, "get_ai_provider", select)
    output = tmp_path / "sdk-debug.json"
    try:
        with caplog.at_level(logging.DEBUG):
            logging.disable(previous_disable)
            result = quality_check.main(
                ["--live", "--env-file", str(cli_env), "--output", str(output)]
            )
            assert logging.root.manager.disable == previous_disable
        assert result == (0 if mode == "success" else 1)
        assert marker not in caplog.text
        console = capsys.readouterr()
        assert marker not in console.out + console.err
        if output.exists():
            assert marker not in output.read_text(encoding="utf-8")
    finally:
        for logger, level in zip(loggers, original_levels, strict=True):
            logger.setLevel(level)
        logging.disable(original_disable)

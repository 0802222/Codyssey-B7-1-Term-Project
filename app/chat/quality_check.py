"""실제 채팅 서비스를 거쳐 품질 검토용 답변을 모은다. (EE-19, #54)

수집 완료는 품질 통과가 아니다. 답변 평가는 사람이 별도로 한다.
실제 호출: uv run python -m app.chat.quality_check --live --env-file PATH --output PATH
수준 변경 후 같은 질문을 검토하려면 --repeat-question을 추가한다. (3건)
"""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from urllib.parse import urlsplit
from uuid import uuid4

from sqlmodel import Session

from app.chat.provider import AIProvider, AIResult, ChatMessage, get_ai_provider
from app.chat.rate_limit import ChatRateLimiter
from app.chat.schemas import ChatRequest
from app.chat.service import answer_question
from app.conversations.repository import create_conversation
from app.core.config import Settings
from app.core.errors import AppError
from app.db.models import User
from app.db.session import create_db_engine, init_db

QUESTION = "API가 무엇인지 설명해줘."
SAMPLE_PLAN = (
    ("A-easy", "A", "easy", QUESTION),
    ("B-beginner", "B", "beginner", QUESTION),
    ("C-advanced", "C", "advanced", QUESTION),
    ("C-easier", "C", "easy", "더 쉽게"),
    ("C-example", "C", "easy", "예시 하나 더"),
)
REPEAT_QUESTION_PLAN = (
    ("R-easy", "R", "easy", "도커?"),
    ("R-easier", "R", "easy", "더 쉽게"),
    ("R-advanced-repeat", "R", "advanced", "도커?"),
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _checkpoint(output: Path, report: dict) -> None:
    # 완성된 JSON을 먼저 쓴 다음 교체해, 쓰는 도중 중단돼도 이전 샘플을 보존한다.
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


class _RecordingProvider:
    """서비스가 실제로 보낸 입력과 provider 응답의 모델·사용량만 기록한다."""

    def __init__(self, provider: AIProvider, sample: dict):
        self.provider = provider
        self.sample = sample

    async def generate_reply(
        self,
        messages: list[ChatMessage],
        *,
        system: str,
        timeout_seconds: float,
        max_output_tokens: int,
    ) -> AIResult:
        self.sample["sent_messages"] = [
            {"role": message.role, "content": message.content} for message in messages
        ]
        self.sample["system_prompt"] = system
        try:
            result = await self.provider.generate_reply(
                messages,
                system=system,
                timeout_seconds=timeout_seconds,
                max_output_tokens=max_output_tokens,
            )
        except (Exception, asyncio.CancelledError) as exc:
            # 예외 원문에는 키나 요청 내용이 있을 수 있어 종류만 남긴다.
            self.sample["provider_error_type"] = type(exc).__name__
            raise
        self.sample["observed_model"] = result.model
        self.sample["token_usage"] = {
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
        }
        return result


async def collect_samples(
    settings: Settings, provider: AIProvider, output: Path, *, repeat_question: bool = False
) -> dict:
    """기본 5건 또는 반복 질문 3건을 모은다. 실패하면 앞선 결과를 남기고 멈춘다."""
    plan = REPEAT_QUESTION_PLAN if repeat_question else SAMPLE_PLAN
    report = {
        "provider": settings.ai_provider,
        "scenario": "repeat-question" if repeat_question else "levels-and-followups",
        "new_question_limit": len(plan),
        "collection_status": "incomplete",
        "quality_review": "not_performed",
        "started_at": _utc_now(),
        "updated_at": _utc_now(),
        "finished_at": None,
        "requested_model": settings.ai_model,
        # URL 전체를 남기지 않는다. 인증 정보·경로·쿼리는 증빙에 필요하지 않다.
        "gateway_hostname": urlsplit(settings.anthropic_base_url).hostname,
        "settings": {
            "context_turns": settings.context_turns,
            "context_max_chars": settings.context_max_chars,
            "ai_timeout_seconds": settings.ai_timeout_seconds,
            "ai_max_output_tokens": settings.ai_max_output_tokens,
            "user_requests_per_minute": settings.user_requests_per_minute,
            "daily_request_limit": settings.daily_request_limit,
        },
        "source_sha256": {
            f"app/chat/{name}": hashlib.sha256(
                Path(__file__).with_name(name).read_bytes()
            ).hexdigest()
            for name in ("prompts.py", "context.py")
        },
        "cases": [],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    # 기존 파일이 있으면 호출 전에 실패한다. 완료·실패 보고서 모두 덮어쓰지 않는다.
    with output.open("x", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
        file.write("\n")

    limiter = ChatRateLimiter(settings.user_requests_per_minute, settings.daily_request_limit)
    with TemporaryDirectory(prefix="easyexplain-quality-") as directory:
        engine = create_db_engine(f"sqlite:///{Path(directory) / 'samples.db'}")
        try:
            init_db(engine)
            with Session(engine) as session:
                # 로그인 화면을 우회하는 수집 전용 사용자다. DB는 종료할 때 삭제한다.
                user = User(email="quality-check@example.invalid", password_hash="unused-test-only")
                session.add(user)
                session.commit()
                session.refresh(user)
                user_id = user.id
                conversations = {}
                for case_id, alias, level, question in plan:
                    sample = {
                        "id": case_id,
                        "conversation_alias": alias,
                        "level": level,
                        "question": question,
                        "answer": None,
                        "status": "failed",
                        "started_at": _utc_now(),
                        "finished_at": None,
                        "sent_messages": [],
                        "system_prompt": None,
                        "observed_model": None,
                        "token_usage": {"input_tokens": None, "output_tokens": None},
                    }
                    recorded = _RecordingProvider(provider, sample)
                    try:
                        if alias not in conversations:
                            conversation = create_conversation(session, user_id, "품질 검토")
                            conversations[alias] = conversation.id
                        response = await answer_question(
                            ChatRequest(
                                conversation_id=conversations[alias],
                                question=question,
                                level=level,
                                client_request_id=uuid4(),
                            ),
                            user_id=user_id,
                            request_id=f"quality-{case_id}",
                            session=session,
                            settings=settings,
                            provider=recorded,
                            rate_limiter=limiter,
                        )
                        sample["answer"] = response.answer
                        sample["status"] = response.status
                    except (Exception, asyncio.CancelledError) as exc:
                        sample["error"] = {
                            "code": str(exc.code)
                            if isinstance(exc, AppError)
                            else "INTERNAL_ERROR",
                            "type": sample.pop("provider_error_type", type(exc).__name__),
                        }
                    sample["finished_at"] = _utc_now()
                    report["cases"].append(sample)
                    report["updated_at"] = _utc_now()
                    if sample["status"] == "failed":
                        report["finished_at"] = _utc_now()
                        _checkpoint(output, report)
                        return report
                    _checkpoint(output, report)
        finally:
            engine.dispose()

    report["collection_status"] = "completed"
    report["finished_at"] = report["updated_at"] = _utc_now()
    _checkpoint(output, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI 품질 검토용 실제 답변 수집 (기본 5건)")
    parser.add_argument("--live", action="store_true", help="실제 AI 호출을 명시적으로 허용")
    parser.add_argument(
        "--repeat-question", action="store_true", help="수준 변경 후 같은 질문 사례만 3건 수집"
    )
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.live:
        print("실제 AI를 호출하려면 --live를 지정해 주세요.", file=sys.stderr)
        return 1
    if args.output.exists():
        print("출력 파일이 이미 있어요. 새로운 출력 파일을 지정해 주세요.", file=sys.stderr)
        return 1
    if not args.env_file.is_file():
        print("설정 파일을 확인해 주세요.", file=sys.stderr)
        return 1

    # SDK import가 DEBUG 설정을 다시 켜더라도 요청 원문이 로그로 나가지 않게 한다.
    previous_disable = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        try:
            settings = Settings(ai_provider="anthropic", _env_file=args.env_file)
            provider = get_ai_provider(settings)
        except Exception:
            print(
                "AI 설정을 확인해 주세요. 모델·키·환경 파일 내용을 점검해 주세요.", file=sys.stderr
            )
            return 1
        try:
            report = asyncio.run(
                collect_samples(
                    settings, provider, args.output, repeat_question=args.repeat_question
                )
            )
        except (Exception, KeyboardInterrupt):
            print("수집을 중단했습니다. 설정과 출력 파일을 확인해 주세요.", file=sys.stderr)
            return 1
        if report["collection_status"] != "completed":
            print(
                "수집을 중단했습니다. 완료된 샘플과 오류 코드는 보고서에 남겼습니다.",
                file=sys.stderr,
            )
            return 1
        count = len(report["cases"])
        print(f"샘플 {count}개를 저장했습니다. 보고서를 읽고 실제 품질을 별도로 검토해 주세요.")
        return 0
    finally:
        # 테스트나 다른 호출자가 쓰던 전역 설정은 성공·실패 모두 원래대로 돌린다.
        logging.disable(previous_disable)


if __name__ == "__main__":
    raise SystemExit(main())

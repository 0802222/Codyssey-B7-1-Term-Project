# AGENTS.md — AI 코딩 도구 공통 규칙

Codex, Claude Code 등 AI 도구가 이 저장소에서 작업할 때 따르는 규칙이다. 사람도 같은 규칙을 따른다.

## 프로젝트
- EasyExplain: 설명 수준(easy / beginner / advanced)을 바꿔 가며 개념을 설명하는 한국어 AI 챗봇
- Codyssey B7-1 과제. 과제 필수 요구사항은 README.md 1장 참고
- Python 3.12 + FastAPI + Jinja2 + SQLite(SQLModel). 프런트 빌드 도구(React 등) 없음
- 계약 문서: `docs/spec/api.md`, `docs/spec/db.md`. 코드보다 계약이 우선이다
- 팀 규칙 전문: `CONTRIBUTING.md`. 이 파일은 그 요약이다
- 사용자는 평가 때 이 코드를 직접 설명해야 한다. 변경 내용과 이유를 짧게 설명해 주고,
  사용자가 이해하지 못한 채 넘어갈 만큼 큰 변경을 한 번에 만들지 않는다

## 명령
```bash
uv sync                    # 의존성 설치 (pip install 사용 금지)
uv run pytest              # 테스트
uv run ruff check .        # 린트
uv run uvicorn app.main:app --reload
```
작업을 끝내기 전에 `uv run ruff check .` 와 `uv run pytest` 를 실행하고 결과를 보고한다.
실행하지 못한 검증은 "미실행"으로 보고하고 통과했다고 쓰지 않는다.

## 역할과 수정 범위
| 역할 | 수정 가능 | 
|---|---|
| L 팀장 | `app/main.py`, `app/core/`, `app/health.py`, `tests/conftest.py`, `tests/core/`, `tests/integration/`, `.github/`, `docs/`, `pyproject.toml`, `uv.lock` |
| A 인증·DB | `app/db/`, `app/auth/`, `app/conversations/`, `tests/auth/`, `tests/conversations/`, `scripts/` 중 DB 확인 도구 |
| B AI·채팅 | `app/chat/`, `tests/chat/` |
| C 화면 | `app/web/`, `app/templates/`, `app/static/`, `tests/web/` |

- 지금 맡은 이슈의 범위 밖 파일은 고치지 않는다. 필요하면 변경 내용을 보고하고 멈춘다.
- 공유 파일(`main.py`, `core/`, `conftest.py`, `pyproject.toml`, `docs/` 계약)은 L 이 조정한다.
- 다른 영역의 기능을 다시 만들지 않는다. 인증은 `app.auth.dependencies`, DB 세션은
  `app.db.session.SessionDep`, AI 는 `app.chat.provider.AIProvider` 를 사용한다.

## 코드 규칙
- 오류는 `app.core.errors.AppError(status, ErrorCode.X, "한국어 안내")` 로 raise 한다.
  `HTTPException` 을 직접 쓰지 않는다. 응답 형식은 `{"error": {"code", "message", "request_id"}}`.
- 미구현 기능은 가짜 성공을 반환하지 않고 `not_implemented("EE-XX")` 를 raise 한다.
- 서버 이벤트는 `app.core.logging.log_event("event_name", key=value)` 로 남긴다.
  비밀번호·쿠키·토큰·API 키·질문/응답 원문은 로그에 남기지 않는다.
- 설정 값은 `app.core.config.Settings` 에서만 읽는다. 라우터에서는 `SettingsDep` 를 쓴다.
- `user_id` 는 요청 본문에서 받지 않는다. 항상 서버 인증(`CurrentUserDep`)으로 결정한다.
- 테스트는 fake AI provider 와 임시 DB(`tests/conftest.py` 의 `client` fixture)를 쓴다.
  로그인이 필요한 API 는 `logged_in_client` fixture 를 쓴다.
  실제 AI 키가 필요한 테스트를 기본 테스트에 넣지 않는다.

## 커밋 메시지
- 형식: `<type>(<scope>): <한국어 요약>` (CONTRIBUTING.md "커밋 메시지 규칙" 참고)
- type: `feat` `fix` `test` `refactor` `docs` `style` `chore` `ci`
- scope: `core` `db` `auth` `conversations` `chat` `web` `deploy` (애매하면 생략)
- 한 커밋에 한 목적. 관련 이슈는 본문 끝에 `Refs #번호`
- 커밋 작성자는 작업한 사람 본인의 git 설정을 그대로 쓴다. 작성자를 바꾸지 않는다

## 금지
- API 키·비밀번호를 코드·문서·테스트·커밋에 쓰기, `.env`·DB 파일 커밋
- `git push --force`, `git reset --hard`, 테스트 삭제·skip 으로 실패 숨기기
- 프로젝트 전체 재생성, 묻지 않은 대규모 리팩터링, 의존성 임의 추가·업그레이드
- main 브랜치에 직접 커밋. 작업은 `feat/ee-XX-설명` 같은 기능 브랜치에서 한다
- PR 머지. 머지는 팀장(L)만 한다 (main 보호 규칙의 push 제한)

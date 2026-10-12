# 👑 L 이초롱 평가 대비 — 앱 구조, 공통 처리, 협업, 배포

[공통 문서](../2-evaluation-example.md)의 답변 요령(2장)과 진행 대본(3장)을 먼저 읽고, 이 파일로 **내 영역**을 준비합니다.
이 파일은 담당자가 직접 고칩니다. 하지 않은 일을 한 것처럼 쓰지 않습니다.

## 1. 예상 질문과 답

### 앱 구조

**🧑‍🏫 퍼실:** 팀장님, FastAPI 앱 전체 구조를 코드로 설명해 주세요.

**👑 L:** `app/main.py` 의 `create_app()` 입니다.
설정을 읽고 → DB 연결을 만들고 → 요청 ID 미들웨어와 공통 오류 처리기를 붙이고 → 영역별 라우터(인증·대화·채팅·화면)를 연결합니다.
각 영역은 자기 폴더에 라우터를 두고, 여기서 `include_router` 로 조립만 합니다. 그래서 네 명이 서로 다른 폴더에서 동시에 작업할 수 있었습니다.
DB 테이블은 서버가 **시작할 때**(`lifespan`) 만듭니다. 배포 서버의 저장 공간(Volume)은 실행 중에만 붙기 때문입니다.

### 서버 로그

**🧑‍🏫 퍼실:** 과제에서 요구한 서버 로그는 어디서 남기나요?

**👑 L:** 요청이 들어오면 `app/core/middleware.py` 가 **서버에서 요청 ID 를 발급**하고 `request_received` 를 남깁니다.
그다음 B 의 AI 호출, A 의 DB 저장도 `log_event()` 하나로 남기는데, 이 함수가 요청 ID 를 자동으로 붙입니다.
그래서 요청 ID 하나로 검색하면 질문 하나의 처리 과정이 이어져 보입니다. 아래는 **배포 서버 Railway 로그**에서 실제로 본 것입니다 (EE-23, 시간 초과 재현 때).

```
INFO    request_received request_id=f5a2… method=POST path=/api/chat
INFO    db_save_success  request_id=f5a2… entity=chat_turn status=pending
INFO    ai_call_start    request_id=f5a2… turn_id=18
WARNING ai_call_failed   request_id=f5a2… turn_id=18 error_code=AI_TIMEOUT
INFO    db_save_success  request_id=f5a2… entity=chat_turn status=failed
INFO    request_completed request_id=f5a2… status=504 latency_ms=2264
```

화면 오류 응답에도 같은 `request_id` 가 들어 있어서, 사용자가 본 오류에서 바로 서버 로그를 찾을 수 있습니다.
이 6단계가 같은 ID 로 이어지는지는 통합 테스트로도 확인합니다. → `tests/integration/test_request_logs.py`

**🧑‍🏫 퍼실:** 로그에 질문 내용이나 비밀번호가 남지는 않나요?

**👑 L:** 남기지 않도록 규칙으로 정했고, 테스트로 확인합니다. 비밀번호, 쿠키, 토큰, API 키, 질문·답변 원문은 로그에 쓰지 않습니다.
질문·답변은 접근이 통제된 DB 에만 저장합니다. 입력 검증 실패 로그도 값이 아니라 **문제가 된 필드 이름만** 남깁니다.
통합 테스트가 실제로 가입·로그인·질문한 뒤 로그 전체에 질문·답변·비밀번호·CSRF 토큰·세션 쿠키가 없는지 검사합니다.

### 오류 처리

**🧑‍🏫 퍼실:** 예상하지 못한 에러가 나면 서버가 죽나요?

**👑 L:** 아니요. 공통 오류 처리기(`app/core/errors.py`)가 잡아서 `500 INTERNAL_ERROR` 와 안내 메시지를 돌려줍니다.
모든 오류는 `{"error": {"code", "message", "request_id"}}` 한 가지 형식이라 화면은 `message` 만 보여 주면 됩니다.
에러 상세 내용은 서버 로그에만 남기고 사용자에게는 보여 주지 않습니다. `tests/core/test_errors.py` 에서 확인합니다.
AI 시간 초과·DB 오류 뒤에도 서버가 계속 응답하는지는 `tests/integration/test_failure_paths.py` 에서 확인합니다.

### 민감정보

**🧑‍🏫 퍼실:** API 키 같은 민감정보는 어떻게 관리했나요?

**👑 L:** 키는 `.env`(로컬)와 Railway 변수(배포)에만 두고, `.gitignore` 로 저장소에 안 올라가게 했습니다. 대신 이름만 있는 `.env.example` 을 제공합니다.
설정은 `app/core/config.py` 한 곳에서만 읽고, 키는 `SecretStr` 이라 실수로 출력해도 가려집니다.
또 **운영 환경에서 가짜 AI 로 켜지거나, 키가 없거나, 쿠키 보안 설정이 꺼져 있으면 서버가 아예 시작되지 않게** 막아 두었습니다.

### 협업

**🧑‍🏫 퍼실:** 브랜치 전략과 PR 규칙을 설명해 주세요.

**👑 L:** main 과 기능 브랜치 구조입니다. 이슈마다 `feat/ee-08-auth-session` 같은 브랜치를 만들고 PR 로만 main 에 들어갑니다.
main 은 보호 규칙으로 **직접 push 금지, 다른 팀원 1명 승인 필수, 리뷰 대화 해결 필수, CI 통과 필수, 최신 main 반영 필수**로 설정했습니다. 팀장인 저도 예외가 아닙니다.
그리고 **머지는 팀장만** 할 수 있게 했습니다. 기능마다 담당자가 다르다 보니, 마지막에 한 사람이 전체 일관성과 민감정보 포함 여부를 확인하고 합치는 게 안전하다고 판단했습니다.
이 권한을 나누려고 저장소를 Organization 으로 옮겼고, `.github/CODEOWNERS` 로 모든 PR 에 팀장이 자동으로 리뷰어로 들어가게 했습니다.
병합은 **Merge commit 만** 허용했습니다. Squash 를 쓰면 개인 커밋이 하나로 합쳐져서 각자의 작업 기록이 사라지기 때문입니다.

### CI (자동 검사)

**🧑‍🏫 퍼실:** CI 는 무엇을 하나요?

**👑 L:** GitHub Actions(`.github/workflows/ci.yml`)가 **모든 PR 과 main push** 마다 돕니다.
`uv sync --locked` 로 잠금 파일과 똑같은 패키지를 설치하고 → `ruff` 로 코드 검사 → `pytest` 로 자동 테스트 750여 개를 돌립니다.
리눅스(`test`)와 Windows(`test-windows`) 두 곳에서 돌리는데, 팀원 Windows 에서만 실패한 일(#12)이 있어서 추가했습니다.
`test` 가 통과하지 않으면 main 보호 규칙 때문에 머지 버튼이 막힙니다.

**🧑‍🏫 퍼실:** CI 에서 실제 AI 는 부르나요?

**👑 L:** 부르지 않습니다. CI 에는 키를 넣지 않고 **가짜 AI 와 테스트마다 새로 만드는 임시 DB** 로 돌립니다.
비용이 들지 않고, 결과가 매번 같고, 키가 새어 나갈 일도 없습니다.
대신 가짜 AI 로는 "실제 AI 가 어떻게 답하는지"를 확인할 수 없어서, 실제 답변은 B 가 따로 샘플로 검증했습니다(EE-19, EE-23).
실제로 배포 서버에서 직접 써 보다가 가짜 AI 테스트로는 못 잡는 문제(#54)를 찾기도 했습니다.

### CD (자동 배포)

**🧑‍🏫 퍼실:** 배포는 어떻게 하나요? 자동인가요?

**👑 L:** 네. Railway 가 GitHub 저장소와 연결되어 있어서 **main 에 머지되면 자동으로 다시 배포**합니다.
"Wait for CI" 를 켜 둬서 **CI 가 통과한 커밋만** 배포됩니다. 그래서 흐름은 PR → 리뷰·CI → 머지 → 자동 배포입니다.
설정과 키는 코드가 아니라 Railway 변수에 있고, DB 파일은 Volume 에 있어서 배포 때는 **코드만** 바뀝니다.

**🧑‍🏫 퍼실:** 서버를 재시작하면 데이터가 남나요?

**👑 L:** 남습니다. SQLite 는 파일이라서, 재배포해도 지워지지 않는 **Railway Volume(`/app/data`)** 에 DB 파일을 둡니다.
2026-10-09 1차 배포 때 재배포 전에 만든 대화가 재배포 후에도 `GET /api/me/conversations` 에 남아 있는 것을 확인했습니다.
그 뒤로도 여러 번 자동 재배포됐는데 계정과 대화가 유지됐습니다.

**🧑‍🏫 퍼실:** 배포하는 동안 서비스가 멈추지 않나요?

**👑 L:** 1~2분 멈출 수 있습니다. Volume 은 한 번에 서버 하나만 붙을 수 있어서, 이전 서버를 내리고 새 서버를 올리는 동안 공백이 생깁니다.
중단 없이 배포하려면 서버를 두 대 이상 띄워야 하고, 그러려면 DB 를 PostgreSQL 같은 별도 서버로, 질문 횟수 제한도 메모리 대신 Redis 같은 공유 저장소로 옮겨야 합니다.
평가 규모(수십 명)에서는 그 복잡도보다 **단순하고 설명할 수 있는 구조**가 낫다고 판단했고, 대신 평가 기간에는 머지를 멈춰 배포가 일어나지 않게 합니다.
배포가 실패했을 때 확인·Rollback 방법은 [배포 문서 8장](../3-deploy-options.md#8-railway-설정-절차)에 적었습니다.

**🧑‍🏫 퍼실:** 배포하면서 문제는 없었나요?

**👑 L:** 두 가지가 있었습니다. 가입이 403 으로 막힌 건 `SITE_ORIGIN` 이 실제 주소와 달라서였고, 배포가 Crashed 된 건 `DATABASE_URL` 형식 오류였습니다.
둘 다 Deploy Logs 와 일부러 틀린 요청을 보내는 방법으로 원인을 찾았습니다. → [트러블슈팅 4·5번](../4-troubleshooting.md)

### 통합 검증

**🧑‍🏫 퍼실:** 네 명이 만든 걸 합쳤을 때 제대로 동작하는지는 어떻게 확인했나요?

**👑 L:** 영역별 테스트는 로그인을 가짜로 처리하는데, 통합 테스트(`tests/integration/`)는 **실제로 가입·로그인해서 쿠키와 CSRF 토큰을 받아** 끝까지 갑니다.
가입 → 질문 → 후속 질문 → 기록 조회 → 로그아웃 흐름, 그리고 AI 시간 초과·DB 오류·비로그인·남의 대화·CSRF 없음 같은 실패 경로를 확인합니다.
테스트가 진짜로 잡는지 보려고 CSRF 검사를 일부러 끄거나 질문 원문을 로그에 남기도록 망가뜨려서 테스트가 실패하는 것도 확인했습니다.

> ⚠️ 배포·재시작 검증은 **실제로 해 본 것만** 말합니다. 안 해 봤으면 "아직 확인하지 못했다"고 합니다.

## 2. 읽을 코드 표

| 파일 | 무엇을 보여 주나 | 관련 테스트 |
|---|---|---|
| [app/main.py](../../../app/main.py) | `create_app()` 조립 순서, 시작할 때 DB 만들기(`lifespan`) | `tests/core/test_health.py` |
| [app/core/middleware.py](../../../app/core/middleware.py) | 요청 ID 발급, `request_received`·`request_completed` | `tests/core/test_logging.py` |
| [app/core/logging.py](../../../app/core/logging.py) | `log_event()` 가 요청 ID 를 붙이는 방법, 남기면 안 되는 것 | `tests/integration/test_request_logs.py` |
| [app/core/errors.py](../../../app/core/errors.py) | `AppError`, 공통 오류 형식, 예상 못 한 오류 → 500 | `tests/core/test_errors.py` |
| [app/core/config.py](../../../app/core/config.py) | 설정 한 곳, `SecretStr`, 운영 모드 시작 거부 검사 | `tests/core/test_config.py` |
| [.github/workflows/ci.yml](../../../.github/workflows/ci.yml) | CI 단계, 리눅스·Windows | PR 화면의 체크 |
| [tests/integration/](../../../tests/integration/) | 실제 로그인 통합 테스트 | (자체) |
| [docs/team/3-deploy-options.md](../3-deploy-options.md) 8장 | Railway 설정·업데이트 절차·1차 배포 기록 | — |

## 3. 결과 예측 → 실제 실행

| 해 볼 것 | 내 예측 | 실제 결과 |
|---|---|---|
| 배포 URL `/health` | `{"status":"ok","db":"ok"}` | 〔 〕 |
| 로그아웃 상태로 `curl -X POST <URL>/api/chat` | 401 `AUTH_REQUIRED`, 본문에 `request_id` | 〔 〕 |
| `curl <URL>/api/nope` | 404, 공통 오류 형식 | 〔 〕 |
| 화면에서 질문 1개 → 응답 헤더 `X-Request-ID` 로 Railway Logs 검색 | 6줄이 같은 ID 로 이어짐, 질문 원문 없음 | 〔 〕 |
| `.env` 에 `APP_ENV=production`, `AI_PROVIDER=fake` 로 서버 실행 | 시작하지 않고 설정 오류 | 〔 〕 |
| `uv run pytest tests/integration -q` | 21 passed | 〔 〕 |
| `git shortlog -sne --no-merges origin/main` | 4명 모두 10개 이상 | 〔 〕 |

## 4. 준비 메모

- **보여 줄 파일:** 위 2장 표
- **시연:** `/health` → 질문 하나의 `X-Request-ID` 로 Railway Logs 검색 → GitHub PR 목록과 보호 규칙 → Actions 의 CI 결과
- **어려웠던 점 후보:** [트러블슈팅](../4-troubleshooting.md) 1번(#54, 실제 AI 로만 잡힌 문제) 또는 4·5번(배포 설정)
- **내 답변 메모:**

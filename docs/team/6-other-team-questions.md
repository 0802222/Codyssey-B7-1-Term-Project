# 다른 팀 평가에서 나온 질문 — 우리 팀 대응 점검

다른 팀 평가에서 실제로 나온 질문을 모아, 우리 팀이 얼마나 대응되는지 담당자별로 정리했어요.
상태는 **✅ 대응됨 · 🟨 일부만 · ❌ 없음** 이에요. 🟨·❌ 는 "빈 곳" 칸의 답할 말을 미리 연습해 둬요.

담당: 👑 L 이초롱 · 🔐 A 송지윤 · 🤖 B 나현준 · 🎨 C 유민규

## 평가 진행 방식 (다른 팀 후기)

- 코드를 전부 보고, 기본 질문도 하며, **본인이 구현한 부분은 본인이 설명**하게 함
- Postman 으로 API 를 전부 호출하고, 오류 처리가 돼 있는지 확인함
- 개발자도구에서 세션키를 지우고 동작을 확인함. 세션키가 어디 저장되는지도 봄
- 실제 서버 DB 에 들어가 즉석에서 쿼리를 짜서 확인함
- 문서는 있으면 깊게 보지 않음 → **말로 설명할 수 있어야 함**
- 스택 선택 근거(트레이드오프·장단점)를 많이 물어봄

## 1. 질문별 대응

| # | 질문 | 담당 | 상태 | 우리 답 | 근거 | 빈 곳 · 답할 말 |
|---|---|---|---|---|---|---|
| 1 | 장애 대응 전략 | 👑 L | 🟨 | `/health` 가 DB 까지 확인. DB 실패는 롤백 후 503 `DB_ERROR`. 재시작 시 `pending` → `interrupted` 정리. 운영 설정이 잘못되면 일부러 기동 거부. CI 통과 후 배포, 문제 시 Rollback | [health.py](../../app/health.py), [session.py](../../app/db/session.py), [config.py](../../app/core/config.py), [5번 문서 5장](5-facilitator-questions.md) | 장애 알림(모니터링) 없음 → "과제 범위 밖이라 뺐고, 실무라면 UptimeRobot 으로 `/health` 감시, Sentry 로 500 추적부터 붙이겠습니다" |
| 2 | 백업 전략 | 🔐 A | 🟨 | SQLite `backup()` 으로 서버를 멈추지 않고 복사본 생성 → 무결성 검사 → SHA-256 확인 → 내려받기. 2026-10-11 리허설 | [README 7장](../../README.md), [test_db_backup.py](../../tests/conversations/test_db_backup.py) | 수동 백업만 있음 (Railway 자동 백업은 Pro 요금제) → "평가 전후 수동 백업. 운영이면 매일 정기 백업 + S3 같은 외부 보관" |
| 3 | 로그 파일을 바로 뽑아서 분석 | 👑 L | 🟨 | 요청마다 `request_id` 를 붙여 `이벤트 key=value` 한 줄로 기록. 오류 응답에도 같은 ID. `railway logs --filter <ID>` 로 터미널 검색 | [logging.py](../../app/core/logging.py), [middleware.py](../../app/core/middleware.py), [eval/L.md](eval/L.md) | 로그 파일·JSON 형식 없음 → `railway logs > logs.txt` 후 `grep ai_call_failed logs.txt \| wc -l` 시연 연습 |
| 4 | Postman 으로 전부 호출 · 오류 처리 | 👑 L (공통 형식)<br>각자 (자기 API) | ✅ | 모든 오류가 `{"error": {"code","message","request_id"}}` 하나로 통일. 예상 못 한 예외도 미들웨어가 500 으로 정리 | [errors.py](../../app/core/errors.py), [test_failure_paths.py](../../tests/integration/test_failure_paths.py) | Postman 은 `Origin` 헤더가 없어 가입·로그인이 403 `CSRF_REJECTED` → "의도한 동작입니다. Origin 을 넣으면 됩니다" (A 도 설명 가능하게) |
| 5 | Swagger: 개발에선 열고 운영에선 닫기 | 👑 L | ✅ | `APP_ENV=production` 이면 `/docs`·`/redoc`·`/openapi.json` 끔 | [main.py](../../app/main.py), [test_api_docs.py](../../tests/core/test_api_docs.py) | — |
| 6 | 의존성 주입 · 재사용 · 객체 할당 | 👑 L (구조)<br>🤖 B (AI provider) | ✅ | `Annotated[..., Depends(...)]` 공통 의존성: `SessionDep` `CurrentUserDep` `CsrfDep` `SettingsDep` `AIProviderDep` `RateLimiterDep`. 테스트는 `dependency_overrides` 로 교체. DB 엔진·요청 제한기는 앱당 1개, DB 세션·AI provider 는 요청마다 | [deps.py](../../app/core/deps.py), [provider.py](../../app/chat/provider.py), [rate_limit.py](../../app/chat/rate_limit.py), [conftest.py](../../tests/conftest.py) | "AI provider 를 왜 요청마다 만드나?" → B 가 답 준비 |
| 7 | 어디서 fetch 하나 | 🎨 C (프런트)<br>🤖 B (AI 호출) | ✅ | 프런트의 모든 API 호출은 `api.js` 한 곳 (CSRF 헤더, 토큰 재발급). 외부 AI 는 `anthropic_provider.py` 에서만 호출 | [api.js](../../app/static/js/api.js), [anthropic_provider.py](../../app/chat/anthropic_provider.py) | — |
| 8 | 크론 작업은 어디서 어떻게 동기화했나 | 🔐 A (세션)<br>🤖 B (요청 한도) | ❌ | 크론 없음. 세션 만료는 요청 때 `expires_at` 비교, 하루 요청 한도는 날짜가 바뀐 뒤 첫 요청에서 초기화 (필요할 때 판단) | [dependencies.py](../../app/auth/dependencies.py), [rate_limit.py](../../app/chat/rate_limit.py) | 만료된 `auth_sessions` 행이 계속 쌓임 → "동작은 맞지만, 앱 시작 시 `DELETE ... WHERE expires_at < now` 나 주기 작업으로 정리하겠습니다" |
| 9 | 인증과 인가를 정확히 구분 | 🔐 A | ✅ | 인증: 쿠키 토큰 → 해시 → DB 세션 조회. 인가: 모든 조회에 로그인 사용자 ID 조건, 남의 대화는 없는 대화와 같은 404. 상태 변경 요청은 CSRF 토큰 + Origin 확인 | [dependencies.py](../../app/auth/dependencies.py), [repository.py](../../app/conversations/repository.py) | — |
| 10 | 개발자도구에서 세션키 지우고 검증 · 세션키가 어디 들어가나 | 🎨 C (화면 동작)<br>🔐 A (쿠키 설정) | ✅ | 세션 토큰: `session` 쿠키 (`HttpOnly` `Secure` `SameSite=Lax`, JS 로 못 읽음). CSRF 토큰: 탭의 `sessionStorage`. 쿠키 삭제 → API 401, 페이지는 `/login` 이동. `sessionStorage` 만 지우면 `/api/auth/me` 로 다시 받아 계속 동작 | [auth.js](../../app/static/js/auth.js), [api.js](../../app/static/js/api.js), [auth/router.py](../../app/auth/router.py) | 두 경우의 차이를 실제 화면으로 시연 연습 |
| 11 | 비동기 · 이벤트 루프 · 어디까지 동기/비동기인가 | 🤖 B | 🟨 | `async def` 는 채팅 API 하나, AI 호출만 `await`. 나머지 API 는 `def` 라 FastAPI 가 스레드풀에서 실행 → 이벤트 루프를 막지 않음 | [chat/router.py](../../app/chat/router.py), [service.py](../../app/chat/service.py), [5번 문서 8장](5-facilitator-questions.md) | 채팅 함수 안의 DB 호출은 동기라 그 순간 이벤트 루프가 멈춤 → "알고 있는 한계. `run_in_threadpool` 이나 비동기 DB 드라이버로 바꾸겠습니다" |
| 12 | SQLite 는 쓰기가 한 번에 하나, 어떻게 보장하나 · DB 가 죽지 않게 | 🔐 A (DB 설정)<br>🤖 B (채팅 트랜잭션) | 🟨 | AI 를 기다리기 전에 `pending` 을 commit 하고 `rollback()` 으로 트랜잭션을 닫아 30초 동안 잠금을 쥐지 않음. 중복 요청은 `(user_id, client_request_id)` 유일 제약. 같은 사용자 동시 질문은 409 `CHAT_BUSY`. 서버·worker 1개 고정 | [service.py](../../app/chat/service.py), [models.py](../../app/db/models.py), [3번 문서 8장](3-deploy-options.md) | WAL·`busy_timeout` 미설정 (pysqlite 기본 5초 대기만) → [session.py](../../app/db/session.py) PRAGMA 옆에 두 줄 추가로 보강 가능 |
| 13 | 서버가 죽었을 때 DB·로그 데이터가 살아 있나 (서버리스) | 👑 L | 🟨 | 서버리스가 아니라 Railway 컨테이너 + Volume. DB 파일은 Volume(`/app/data`)에 있어 재배포·재시작 후에도 유지 (확인함). Volume 삭제 대비 수동 백업 | [3번 문서 8장](3-deploy-options.md), [README 7장](../../README.md) | 로그는 Railway 보관 기간에만 의존 → "서버리스면 SQLite 파일이 사라져 관리형 DB·외부 로그 저장소가 필요. 그래서 Volume 되는 Railway 를 골랐습니다" |
| 14 | GitHub 브랜치 전략 | 👑 L | ✅ | GitHub Flow. `feat/ee-XX-...` 기능 브랜치 → PR → 승인 1명 + CI `test` 통과 → 팀장만 Merge commit. main 보호, 병합 시 Railway 자동 배포 | [CONTRIBUTING.md](../../CONTRIBUTING.md) | — |
| 15 | 설계 구조 · 코드 간 의존성 | 👑 L | ✅ | 영역별 폴더(auth·db·conversations·chat·web·core). 다른 영역은 공통 의존성으로만 연결. AI 는 `AIProvider` Protocol 뒤에 숨겨 가짜·실제 교체. 계약은 `docs/spec` | [main.py](../../app/main.py), [api.md](../spec/api.md), [db.md](../spec/db.md) | — |
| 16 | 실제 서버 DB 에 들어가 조회 · 스크립트 실행 | 🔐 A | ✅ | `railway ssh` → 컨테이너 Python → `check_logs.sql` (JOIN·WHERE·ORDER BY·LIMIT). 컨테이너에 `sqlite3` 명령이 없어 Python 으로 실행. 리허설함 (#31) | [check_logs.sql](../../scripts/check_logs.sql), [README 7장](../../README.md) | 즉석 쿼리 요구 대비 → `GROUP BY status` 집계 등 1~2개 연습 |
| 17 | 로그인 담당: DB 세션 방식 (서명 검증·난수 생성) · 문제점 · 그래도 쓴 이유 | 🔐 A | ✅ | `secrets.token_urlsafe(32)` 암호학적 난수 토큰. DB 에는 SHA-256 해시만 저장. 서명(HMAC·JWT) 대신 DB 조회가 검증. 비밀번호는 Argon2, 없는 이메일도 더미 해시와 비교해 응답 시간 차이 제거 | [auth/router.py](../../app/auth/router.py), [dependencies.py](../../app/auth/dependencies.py) | 문제점: 요청마다 DB 조회, 만료 행 누적, 서버 확장 어려움. 쓴 이유: 로그아웃 즉시 무효화(JWT 는 만료까지 유효), `HttpOnly` 로 스크립트 탈취 방지 |
| 18 | 스택 선택 근거 · 트레이드오프 | 👑 L (전체)<br>각자 (자기 영역) | ✅ | FastAPI·SQLite·Jinja2+순수 JS·세션 쿠키·Railway·uv 를 대안·한계와 함께 표로 정리 | [5번 문서 2장](5-facilitator-questions.md) | 각자 자기 영역 선택(A: 세션 쿠키·SQLite, B: async·provider, C: 순수 JS) 은 직접 말할 수 있게 |

## 2. 담당자별 모아 보기

| 담당 | 맡은 질문 | 🟨·❌ 로 준비할 것 |
|---|---|---|
| 👑 L 이초롱 | 1, 3, 4, 5, 6, 13, 14, 15, 18 | 장애 알림 부재 답변, 로그 뽑기 시연, 서버리스 대비 답변 |
| 🔐 A 송지윤 | 2, 8, 9, 10, 12, 16, 17 | 정기 백업 답변, 만료 세션 정리, WAL·`busy_timeout`, 즉석 SQL 연습, Postman `Origin` 403 설명 |
| 🤖 B 나현준 | 6, 7, 8, 11, 12 | 동기 DB 가 이벤트 루프를 막는 한계, AI provider 요청마다 생성 이유 |
| 🎨 C 유민규 | 7, 10 | 쿠키 삭제 vs `sessionStorage` 삭제 시연 |

## 3. 평가 전 보강 후보

| 순서 | 할 일 | 담당 | 종류 |
|---|---|---|---|
| 1 | SQLite `PRAGMA journal_mode=WAL` + `busy_timeout` 추가 | 🔐 A | 코드 (작음) |
| 2 | 만료된 `auth_sessions` 정리 (앱 시작 시 삭제) 또는 답변 준비 | 🔐 A | 코드 또는 답변 |
| 3 | `railway logs > file` → `grep` 시연 연습 | 👑 L | 연습 |
| 4 | `check_logs.sql` 외 집계 쿼리 1~2개 연습 | 🔐 A | 연습 |
| 5 | Postman 에서 `Origin` 없을 때 403 이 의도된 동작임을 설명 연습 | 🔐 A · 👑 L | 연습 |
| 6 | 개발자도구에서 쿠키·`sessionStorage` 삭제 시연 연습 | 🎨 C | 연습 |

# 트러블슈팅 기록

개발·배포하면서 실제로 겪은 문제와 해결 과정입니다. 평가에서 "어려웠던 점", "어떻게 찾고 고쳤나"를 물으면 여기서 고릅니다.
사례마다 **증상 → 원인 → 해결 → 재발 방지 → 근거** 순서로 적습니다.

| # | 사례 | 어디서 발견 | 담당 | 근거 |
|---|---|---|---|---|
| 1 | [수준만 바꿔 같은 질문을 하면 "이전 대화를 전달받지 못했다"고 답함](#1-수준만-바꿔-같은-질문을-하면-이전-대화를-전달받지-못했다고-답함) | 배포 서버 + 실제 AI | B | #54 → #55 |
| 2 | [대화 제목이 항상 "새 대화"](#2-대화-제목이-항상-새-대화) | 배포 서버에서 기록 API 확인 | A | #49 → #53 |
| 3 | [CSRF 헤더에 한글이 오면 403 이 아니라 500](#3-csrf-헤더에-한글이-오면-403-이-아니라-500) | 코드 리뷰 | A | #40 → #45 |
| 4 | [배포 후 회원가입이 403](#4-배포-후-회원가입이-403) | 1차 배포 | L | #50 |
| 5 | [환경 변수 형식 오류로 배포 실패(Crashed)](#5-환경-변수-형식-오류로-배포-실패crashed) | 1차 배포 | L | #50 |
| 6 | [Windows 에서만 테스트 실패](#6-windows-에서만-테스트-실패) | 팀원 로컬 실행 | L | #12, #58 |
| 7 | [아주 큰 offset 이면 500](#7-아주-큰-offset-이면-500) | 코드 리뷰 | A | #42 리뷰 → #57 |

---

## 1. 수준만 바꿔 같은 질문을 하면 "이전 대화를 전달받지 못했다"고 답함

- **증상:** 같은 대화에서 아주 쉽게 "도커?" → "더 쉽게" → **전공자** "도커?" 로 물으니, AI 가 "이전 대화 내용을 전달받지 못해서 어떤 부분이 궁금한지 알 수 없어요" 라고 답했다. 바로 다음 "핵심만" 은 도커로 이어서 답했다.
- **원인 찾기:** 내 기록 화면에서 네 턴이 모두 같은 대화이고 앞 두 턴이 completed 인 것을 확인했다. 문맥 코드(`app/chat/context.py`)는 수준과 관계없이 같은 대화의 완료 턴을 보낸다. 즉 **문맥은 전달됐고, AI 가 판단을 잘못한 것**이다.
- **원인:** 프롬프트의 "질문이 모호하면 확인 질문을 한다", "전달받지 않은 내용을 아는 척하지 않는다" 지침에 AI 가 과하게 반응해, 이미 설명한 질문을 "모호한 질문" 으로 보고 사실과 다른 말까지 했다.
- **해결:** 지침 보완 — "이미 설명한 주제를 수준을 바꿔 다시 물어도 현재 수준으로 다시 설명한다", "질문이 짧거나 이전과 같다는 이유만으로 모호하다고 보지 않는다", "문맥을 받았으면 받지 못했다고 말하지 않는다" (`app/chat/prompts.py`)
- **재발 방지:** `tests/chat/test_chat_api.py::test_repeated_short_question_keeps_context_when_switching_to_advanced` 가 같은 3턴의 문맥 전달(메시지 1 → 3 → 5개)과 전공자 지침을 확인한다. 실제 AI 결과는 [ISSUE-54](../../app/chat/ISSUE-54.md) 에 기록.
- **배운 점:** 자동 테스트는 가짜 AI 라 **"AI 가 실제로 어떻게 답하는지"는 잡지 못한다.** 실제 서비스를 직접 써 보는 확인이 따로 필요하다.

## 2. 대화 제목이 항상 "새 대화"

- **증상:** 배포 후 `GET /api/me/conversations` 를 보니 모든 대화 제목이 "새 대화" 라 어떤 대화인지 알 수 없었다.
- **원인:** 화면은 첫 질문 직전에 빈 요청으로 대화를 만들고, 서버는 제목을 "새 대화" 로 저장한 뒤 바꾸는 단계가 없었다. DB 명세(`docs/spec/db.md`)의 title 설명은 "첫 질문 일부" 라 **명세와 구현이 어긋나 있었다.** 제목을 보여 주는 화면이 아직 없어서 드러나지 않았다.
- **해결:** 첫 질문을 저장할 때 제목이 "새 대화" 면 질문 앞 30자로 바꾼다 (`app/conversations/repository.py`).
- **재발 방지:** `tests/conversations/test_conversations.py` 의 `test_first_pending_turn_sets_default_conversation_title`, `test_second_pending_turn_keeps_first_question_title`, `test_long_first_question_is_truncated_with_ellipsis` · 통합 테스트 `tests/integration/test_user_journey.py`
- **배운 점:** 기록 화면(EE-17)이 만들어지기 **전에** 배포 서버에서 API 를 직접 확인해서, 화면 작업 전에 고칠 수 있었다.

## 3. CSRF 헤더에 한글이 오면 403 이 아니라 500

- **증상:** `X-CSRF-Token: 가나다` 처럼 ASCII 가 아닌 값을 보내면 403 대신 500 `INTERNAL_ERROR` 가 났다.
- **원인:** 토큰 비교에 쓴 `secrets.compare_digest` 는 문자열에 ASCII 밖 문자가 있으면 `TypeError` 를 던진다. 리뷰에서 타이밍 공격을 막으려고 `==` 를 이 함수로 바꾸면서 생겼다.
- **해결:** 두 값을 `.encode()` 로 바이트로 바꿔 비교 (`app/auth/dependencies.py`).
- **재발 방지:** `tests/auth/test_login.py::test_logout_with_non_ascii_csrf`. 수정을 되돌리면 이 테스트가 `TypeError` 로 실패하는 것을 확인했다.
- **배운 점:** 보안을 위한 변경도 **예외 상황(이상한 입력)** 을 같이 확인해야 한다. 정상 사용자는 겪지 않지만, 응답 코드가 틀리면 서버 오류로 보인다.

## 4. 배포 후 회원가입이 403

- **증상:** 배포 주소에서 가입이 안 됐다. 정확한 주소를 Origin 으로 보내도 403 `CSRF_REJECTED`.
- **원인 찾기:** 계정을 만들지 않도록 일부러 틀린 이메일로 요청을 보내, 이메일 검사 전에 Origin 검사에서 막히는 것을 확인했다.
- **원인:** 가입·로그인은 요청 Origin 이 `SITE_ORIGIN` 과 정확히 같아야 한다. Railway 변수 `SITE_ORIGIN` 이 실제 주소와 달랐다.
- **해결:** `SITE_ORIGIN` 에 실제 주소(`https://…up.railway.app`, 끝에 `/` 없이)를 직접 적고 재배포.
- **재발 방지:** [배포 문서 8장](3-deploy-options.md#8-railway-설정-절차) 에 "도메인을 만든 **뒤** 실제 주소를 그대로" 와 증상을 적었다.

## 5. 환경 변수 형식 오류로 배포 실패(Crashed)

- **증상:** 변수를 고친 뒤 새 배포가 Crashed. 그 사이 사이트가 가짜 AI 로 돌고 있던 것도 발견했다 (`APP_ENV`·`AI_PROVIDER` 가 적용되지 않아 개발 모드로 떠 있었음).
- **원인:** Deploy Logs 의 `Could not parse SQLAlchemy URL` — `DATABASE_URL` 값 모양이 잘못돼 앱이 시작하지 못했다.
- **해결:** `DATABASE_URL=sqlite:////app/data/easyexplain.db` (슬래시 4개, 따옴표·공백 없이) 로 고치고, Deploy Logs 의 `app_started ... env=production ai_provider=anthropic` 으로 운영 모드를 확인했다.
- **재발 방지:** 배포 문서 8장에 형식 주의와 "실패하면 Volume 서비스는 사이트도 중단될 수 있음, 로그·`/health` 확인 후 재배포 또는 Rollback" 을 적었다 (리뷰에서 "이전 배포가 유지된다" 는 잘못된 안내를 바로잡음).
- **배운 점:** 운영에서 설정이 틀리면 **일부러 시작하지 않게 한 검사**(`app/core/config.py`) 덕분에, 키 없이 운영 모드로 뜨는 사고를 막았다.

## 6. Windows 에서만 테스트 실패

- **증상:** 팀원 Windows 에서 `test_unexpected_error_log_keeps_request_id` 가 실패했다. CI(Ubuntu)와 macOS 에서는 통과.
- **원인:** 오류 위치 로그의 경로를 운영체제 방식으로 만들어 Windows 에서는 `tests\core\...` 로 찍혔고, 테스트는 `/` 를 기대했다.
- **해결:** `relative_to(...).as_posix()` 로 경로 구분자를 `/` 로 통일 (`app/core/errors.py`, #12).
- **재발 방지:** CI 에 `test-windows` job 추가 (#58) — PR 마다 Windows 에서도 테스트한다.

## 7. 아주 큰 offset 이면 500

- **증상:** `GET /api/me/conversations?offset=9223372036854775808` 이 500.
- **원인:** 입력 검증(0 이상)은 통과하지만 SQLite 정수 범위를 넘어 쿼리에서 `OverflowError`.
- **해결:** `offset` 최대 1,000,000, 넘으면 422 `VALIDATION_ERROR` (`app/conversations/router.py`, API 명세 2장).
- **재발 방지:** `tests/conversations/test_api.py` 의 offset 경계 테스트.
- **배운 점:** "0 이상" 같은 아래쪽 경계만이 아니라 **위쪽 경계**도 정해야 한다.

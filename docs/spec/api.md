# API 명세 v1

코드보다 먼저 합의하는 약속이다. 필드 이름·상태 코드를 바꾸려면 **이 문서를 고치는 PR 을 먼저** 올리고
관련 담당자(특히 화면 담당 C)가 함께 반영한다.

공통 규칙
- 웹 페이지와 JSON API 는 같은 서버(같은 출처)에서 제공한다.
- `user_id` 는 요청에서 받지 않는다. 서버가 로그인 세션으로 결정한다.
- 시각은 ISO 8601 UTC (`2026-10-02T07:00:00Z`).
- 목록은 최신순, 대화 상세의 턴은 오래된 순.
- 모든 응답 헤더에 서버가 발급한 `X-Request-ID` 가 있다.
- 로그인 후 상태 변경 요청(POST 등)에는 `X-CSRF-Token` 헤더가 필요하다.

## 1. 페이지

| 경로 | 접근 | 담당 |
|---|---|---|
| `GET /` | 공개 소개 | C |
| `GET /signup`, `GET /login` | 공개 | C |
| `GET /chat` | 로그인. 아니면 `/login` 으로 303 | C+A |
| `GET /history` | 로그인. 아니면 `/login` 으로 303 | C+A |
| `GET /health` | 공개. 키·DB 경로·개인정보 출력 금지 | L |

API 의 비로그인 요청은 리다이렉트가 아니라 JSON 401 을 반환한다.

## 2. API

| 메서드·경로 | 요청 | 성공 | 인증 / 담당 |
|---|---|---|---|
| `POST /api/auth/signup` | `email`, `password` | 201 `{id, email}` | 공개·Origin 검증 / A |
| `POST /api/auth/login` | `email`, `password` | 200 `{user, csrf_token}` + 세션 쿠키 | 공개·Origin 검증 / A |
| `GET /api/auth/me` | - | 200 `{user, csrf_token}` | 로그인 / A |
| `POST /api/auth/logout` | - | 204, 세션 삭제·쿠키 삭제 | 로그인+CSRF / A |
| `POST /api/conversations` | `{}` | 201 `{id, title, created_at}` | 로그인+CSRF / A |
| `GET /api/me/conversations?limit=20&offset=0` | - | `{items, limit, offset, has_more}` | 로그인 / A |
| `GET /api/conversations/{id}` | - | `{conversation, turns}` | 본인 소유만 / A |
| `GET /api/me/chats?limit=20&offset=0` | - | `{items, limit, offset, has_more}` (턴 목록) | 로그인 / A |
| `POST /api/chat` | 아래 참고 | 200 턴 | 로그인+CSRF+소유권 / B |
| `GET /health` | - | 200 `{status: "ok", db: "ok"}` / 503 `DB_ERROR` | 공개 / L |

### 가입·로그인 입력 규칙 (실패 시 422 `VALIDATION_ERROR`)
- `email`: 이메일 형식, 최대 100자. 앞뒤 공백 제거·소문자로 바꿔서 저장·비교한다
- `password`: 8~64자, 영어(영문·숫자·기호와 공백, ASCII 32~126)만. 그 밖의 조건(대소문자·숫자·기호 섞기 등)은 없다. 앞뒤 공백을 지우지 않고 그대로 해시한다
- 로그인 실패는 이메일이 없든 비밀번호가 틀리든 똑같이 401 `INVALID_CREDENTIALS`

- `limit` 기본 20·최대 100, `offset` 기본 0·0 이상·최대 1,000,000. 범위를 벗어나면 422 `VALIDATION_ERROR`.
- 없는 대화와 남의 대화는 **똑같이** 404 `CONVERSATION_NOT_FOUND` (존재 여부를 알려 주지 않음).
- 응답에 `password_hash`, `token_hash`, 다른 사람의 정보를 넣지 않는다.

### 항목 형식
- 대화 item: `id, title, created_at, updated_at`
- 턴 item: `id, conversation_id, level, question, answer, status, error_code, created_at`
  - `status`: `pending` / `completed` / `failed` / `interrupted`
  - 완료되지 않은 턴의 `answer` 는 `null`

## 3. POST /api/chat

요청
```json
{
  "conversation_id": "9b1c4da5-7a74-4f97-88cb-1b2790e510a9",
  "question": "API가 뭔지 쉽게 설명해줘.",
  "level": "easy",
  "client_request_id": "b2120799-6d46-4d3c-8d88-ea17361ad25d"
}
```
검증 (실패 시 422, AI 호출하지 않음)
- `question`: 앞뒤 공백 제거 후 1~2,000자
- `level`: `easy` | `beginner` | `advanced`
- `conversation_id`, `client_request_id`: UUID
- 계약에 없는 필드(`user_id` 등)는 거부

성공 200
```json
{
  "request_id": "서버가 발급한 추적 ID",
  "turn_id": 31,
  "conversation_id": "9b1c4da5-7a74-4f97-88cb-1b2790e510a9",
  "level": "easy",
  "question": "API가 뭔지 쉽게 설명해줘.",
  "answer": "한 줄 정의: ...",
  "status": "completed",
  "created_at": "2026-10-02T07:00:00Z"
}
```

중복 요청 (`(user_id, client_request_id)` 유일)
- 같은 키 + 같은 내용 + 완료 → 저장된 결과 반환, AI 재호출 없음
- 같은 키 + 다른 내용 → 409 `REQUEST_CONFLICT`
- 같은 키 + 처리 중 → 409 `CHAT_BUSY`
- 같은 키 + 실패 → 기존 실패 반환. 다시 시도는 클라이언트가 새 키로

## 4. 오류 규격

```json
{
  "error": {
    "code": "AI_TIMEOUT",
    "message": "응답이 지연되고 있어요. 잠시 후 다시 시도해 주세요.",
    "request_id": "서버 추적 ID"
  }
}
```

| HTTP | code | 의미 |
|---|---|---|
| 401 | `AUTH_REQUIRED` | 비로그인·세션 만료 |
| 401 | `INVALID_CREDENTIALS` | 이메일/비밀번호 불일치 (계정 존재 여부 구분 안 함) |
| 403 | `CSRF_REJECTED` | Origin/CSRF 검증 실패 |
| 404 | `NOT_FOUND` | 없는 경로 |
| 404 | `CONVERSATION_NOT_FOUND` | 없는 대화 또는 남의 대화 |
| 405 | `METHOD_NOT_ALLOWED` | 허용되지 않은 메서드 |
| 409 | `ACCOUNT_EXISTS` | 이미 가입된 이메일 |
| 409 | `CHAT_BUSY` / `REQUEST_CONFLICT` | 처리 중 / 같은 키에 다른 내용 |
| 422 | `VALIDATION_ERROR` | 빈 입력, 길이 초과, 잘못된 level·UUID |
| 429 | `RATE_LIMITED` | 우리 서비스의 요청 한도 초과 |
| 500 | `INTERNAL_ERROR` | 예상하지 못한 오류 (내부 정보 숨김) |
| 501 | `NOT_IMPLEMENTED` | 아직 구현하지 않은 기능 (개발 중에만) |
| 502 | `AI_UPSTREAM_ERROR` | AI 연결 실패·상위 서버 오류·빈 응답 |
| 503 | `AI_UNAVAILABLE` | AI 이용 한도·설정 문제 |
| 503 | `DB_ERROR` | DB 저장·조회 실패 |
| 504 | `AI_TIMEOUT` | AI 응답 대기 시간 초과 |

코드에서는 `app.core.errors.ErrorCode` 로 사용한다. 상위 API 의 원문 오류, 키, 스택 트레이스는
응답에 넣지 않는다.

## 5. 내부 경계 (영역 간 약속)

| 경계 | 위치 | 제공 | 사용 |
|---|---|---|---|
| 로그인 사용자 (API) | `app.auth.dependencies.CurrentUserDep` → `CurrentUser(id, email)`. 비로그인이면 401 | A | B, C |
| 로그인 사용자 (페이지) | `app.auth.dependencies.OptionalUserDep` → `CurrentUser` 또는 `None`. 오류를 내지 않음 | A | C (`None` 이면 `/login` 으로 303) |
| CSRF 검증 | `app.auth.dependencies.CsrfDep` | A | B |
| DB 세션 | `app.db.session.SessionDep` | L→A | A, B |
| 대화 저장소 | `app.conversations.repository`의 저장 함수는 내부에서 commit한다. `create_conversation(session, user_id, title) -> Conversation`, `create_pending_turn(session, conversation_id, user_id, client_request_id, request_id, level, question) -> ChatTurn`, `complete_turn(session, turn_id, user_id, answer) -> ChatTurn`, `fail_turn(session, turn_id, user_id, error_code) -> ChatTurn`. 조회 함수 `get_recent_completed_turns(session, conversation_id, user_id, limit) -> list[ChatTurn]`는 최근 완료 턴을 최신순으로 반환하며 `limit=0`이면 빈 목록을 반환한다. 소유권을 확인하며, 없는 대화나 타인 대화는 404 `CONVERSATION_NOT_FOUND`, DB 오류는 503 `DB_ERROR`로 처리한다 | A | B |
| AI provider 선택 | `app.chat.provider.get_ai_provider` → `AIProviderDep`. `settings.ai_provider` 로 fake / anthropic 선택 (EE-05 에서 작성). 테스트는 `app.dependency_overrides[get_ai_provider]` 로 타임아웃·오류를 내는 가짜로 바꿔 끼운다 | B | B |
| AI 호출 | `app.chat.provider.AIProvider.generate_reply(messages, *, system, timeout_seconds, max_output_tokens) -> AIResult` | B | B |
| AI 오류 | `AITimeoutError` / `AIUpstreamError` / `AIUnavailableError` | B | B |
| 설정 | `app.core.deps.SettingsDep` | L | 전원 |
| 이벤트 로그 | `app.core.logging.log_event` | L | 전원 |

AI 호출은 코디세이 게이트웨이(`ANTHROPIC_BASE_URL`)를 거쳐 Anthropic Messages 규격으로 한다.
시스템 프롬프트는 `messages` 가 아니라 `system` 으로 따로 넘긴다.

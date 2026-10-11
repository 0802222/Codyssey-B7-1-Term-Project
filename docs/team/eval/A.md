# 🔐 A 송지윤 평가 대비 — 회원가입·로그인, 접근 제어, 대화 기록 DB

[공통 문서](../2-evaluation-example.md)의 답변 요령(2장)과 진행 대본(3장)을 먼저 읽고, 이 파일로 **내 영역**을 준비합니다.
이 파일은 담당자가 직접 고칩니다. 하지 않은 일을 한 것처럼 쓰지 않습니다.

## 1. 예상 질문과 답

**🧑‍🏫 퍼실:** 회원가입 코드를 보여 주세요. 비밀번호는 어떻게 저장하나요?

**🔐 A:** [app/auth/router.py](../../../app/auth/router.py)의 `signup()`입니다. 이메일의 앞뒤 공백을 제거하고 소문자로 변환한 뒤 형식을 검증합니다.
비밀번호는 `pwdlib`의 권장 해시 알고리즘 (현재 기준 `Argon2`)로 저장합니다. 회원가입 응답에는 비밀번호나 해시를 반환하지 않습니다.
중복 이메일은 `409 ACCOUNT_EXISTS`, 잘못된 입력은 `422 VALIDATION_ERROR`입니다.
로그인 시에는 입력한 비밀번호를 저장된 해시와 비교하여 검증합니다.
→ [test_signup.py](../../../tests/auth/test_signup.py)


**🧑‍🏫 퍼실:** 로그인 상태는 어떻게 유지하나요?

**🔐 A:** [app/auth/router.py](../../../app/auth/router.py)에서 로그인 시 무작위 세션 토큰과 CSRF 토큰을 발급하고, [dependencies.py](../../../app/auth/dependencies.py)이후 요청의 인증을 처리합니다. 
브라우저에는 세션 토큰을 `HttpOnly` 쿠키로 전달하고,
DB에는 토큰 원문 대신 SHA-256 해시와 만료 시각을 저장합니다. 요청이 들어오면 쿠키의 토큰을 해시해 DB 세션을 조회하고,
만료되지 않은 세션의 사용자를 인증합니다. 기본 만료 시간은 설정값 `SESSION_TTL_SECONDS`입니다.
→ [test_login.py](../../../tests/auth/test_login.py): `test_login_success`, `test_login_session_ttl`

**🧑‍🏫 퍼실:** HttpOnly 를 왜 쓴 건가요?

**🔐 A:** `HttpOnly`는 JavaScript가 세션 쿠키에 직접 접근하지 못하게 해 스크립트 공격 등을 통한 세션 토큰 탈취 위험을 줄이기 위해 사용합니다.
상태 변경 요청에서는 `X-CSRF-Token` 헤더를 검증해 CSRF 공격을 방지하고, 화면에 AI 답변을 표시할 때는 `textContent`를 사용해 HTML로 해석되지 않도록 합니다.

**🧑‍🏫 퍼실:** 로그인하지 않은 사람이 채팅 API를 호출하면요?

**🔐 A:** 채팅 API가 함수 인자에 `CurrentUserDep` 를 받게 되어 있어서, 유효한 세션이 없으면 핸들러 실행 전에 `401 AUTH_REQUIRED` 오류를 반환합니다.
인증을 각 기능에서 따로 구현하지 않고 [dependencies.py](../../../app/auth/dependencies.py)의 공통 의존성을 재사용해 일관되게 처리합니다.
→ [test_chat_api.py](../../../tests/chat/test_chat_api.py)의 `test_chat_requires_login` (B 영역 테스트)

**🧑‍🏫 퍼실:** 다른 사람의 대화 ID를 알면 조회할 수 있나요?

**🔐 A:** 조회할 수 없습니다. 대화를 조회할 때 **대화 ID뿐 아니라 현재 로그인한 사용자의 ID도 함께** 조건으로 사용합니다. 다른 사용자의 대화이거나 존재하지 않는 대화라면
`404 CONVERSATION_NOT_FOUND`를 반환하므로, 그 대화가 존재하는지도 구분할 수 없습니다.
→ [repository.py](../../../app/conversations/repository.py), [test_api.py](../../../tests/conversations/test_api.py):
`test_other_users_and_missing_conversation_look_identical`

**🧑‍🏫 퍼실:** CSRF는 어떻게 막나요?

**🔐 A:** 로그인 응답으로 받은 CSRF 토큰을 상태 변경 요청의 `X-CSRF-Token` 헤더에 담아 보냅니다.
`require_csrf()`가 요청 토큰을 세션에 저장된 토큰과 상수 시간 비교로 검증, 토큰이 없거나 다르면 `403 CSRF_REJECTED`로 요청을 거부합니다.
→ [test_login.py](../../../tests/auth/test_login.py): `test_logout_without_csrf`, `test_logout_with_wrong_csrf`,
[test_api.py](../../../tests/conversations/test_api.py): `test_create_conversation_without_csrf`

**🧑‍🏫 퍼실:** 대화 기록은 어디에 저장하고 어떻게 확인하나요?

**🔐 A:** [models.py](../../../app/db/models.py)에 정의된 `ChatTurn` 모델에 사용자·대화 ID, 질문, 답변, 설명 수준,
상태와 생성 시각을 저장합니다. AI 응답이 완료되지 않았거나 실패한 경우에는 `answer`가 비어 있을 수 있습니다.
사용자는 로그인 후 `GET /api/me/conversations`로 대화 목록을 조회하고, `GET /api/conversations/{conversation_id}`로 특정 대화의 질문·답변 기록을 확인할 수 있습니다.
개발·검증 시에는 [check_logs.sql](../../../scripts/check_logs.sql)을 직접 실행해 특정 사용자의 최근 기록 20건을 확인할 수 있습니다.

## 2. 읽을 코드 표

| 파일 | 무엇을 보여 주나 | 관련 테스트 |
|---|---|---|
| [app/auth/router.py](../../../app/auth/router.py) | 이메일 정규화, Argon2 해시, 로그인 세션·쿠키, 로그아웃 | [test_signup.py](../../../tests/auth/test_signup.py), [test_login.py](../../../tests/auth/test_login.py) |
| [app/auth/dependencies.py](../../../app/auth/dependencies.py) | 세션 토큰 해시 조회, 만료 확인, 로그인·CSRF 의존성 | [test_login.py](../../../tests/auth/test_login.py): 세션·CSRF 테스트 |
| [app/db/models.py](../../../app/db/models.py) | users·auth_sessions·conversations·chat_turns 테이블과 제약 | [test_models.py](../../../tests/conversations/test_models.py) |
| `app/db/session.py` | DB 엔진·세션 생성, SQLite 외래 키 제약 활성화, 테이블 초기화, 재시작 시 `pending` 턴을 `interrupted`로 복구 | [test_models.py](../../../tests/conversations/test_models.py): 직접 호출 후 테이블 생성 및 미완료 턴 복구 테스트,  [test_api.py](../../../tests/conversations/test_api.py): 재시작 시 미완료 턴 복구 테스트 |
| [app/conversations/repository.py](../../../app/conversations/repository.py) | 사용자 소유 조건이 포함된 대화 생성·조회·목록 저장소 | [test_conversations.py](../../../tests/conversations/test_conversations.py) |
| [app/conversations/router.py](../../../app/conversations/router.py) | 로그인 사용자 기반 내 대화·채팅 기록 API와 CSRF 적용 | [test_api.py](../../../tests/conversations/test_api.py) |

## 3. 결과 예측 → 실제 실행

아래는 자동 테스트의 실행 전 예측과 결과입니다. 실제 서비스에서 계정을 만들거나 데이터를 조회한 기록은 아닙니다.

| 해 볼 것 | 실행 전 예측 | 실제 결과 |
|---|---|---|
| 아래 인증·대화 API 테스트 세 파일 함께 실행 | 가입·로그인·CSRF와 사용자별 대화 권한 사례가 통과 | **108 passed** |

실행 명령:

```bash
uv run --locked pytest -q tests/auth/ tests/conversations/
```

## 4. 준비 메모

- **보여 줄 파일:** 2장 표의 인증 의존성·모델·대화 저장소
- **시연:** 가입 → 로그인 후 세션 쿠키가 설정되는지 확인 → CSRF 없는 대화 생성 요청 거절 → 다른 계정으로 대화 ID 조회 시 404 → 내 기록 API
- **주의해서 말할 점:** HttpOnly는 JavaScript의 세션 쿠키 직접 접근을 막기 위한 설정이며, CSRF 방어는 별도로 X-CSRF-Token을 검증하는 방식입니다.
앱 재시작 시 남아 있는 pending 턴은 interrupted로 변경하고 완료 시각을 기록합니다. 관련 동작은 test_models.py와 test_api.py에서 서로 다른 방식으로 확인합니다.
- **내 답변 메모:** 

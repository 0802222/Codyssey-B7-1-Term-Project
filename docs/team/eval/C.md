# 🎨 C 유민규 평가 대비 — 웹 화면, API 연결, 사용성

[공통 문서](../2-evaluation-example.md)의 답변 요령(2장)과 진행 대본(3장)을 먼저 읽고, 이 파일로 **내 영역**을 준비합니다.
이 파일은 담당자가 직접 고칩니다. 하지 않은 일을 한 것처럼 쓰지 않습니다.

## 1. 예상 질문과 답

### 화면 구성

**🧑‍🏫 퍼실:** C 님, 화면은 어떻게 만들었나요? React 같은 걸 썼나요?

**🎨 C:** 별도 프런트엔드 프레임워크 없이, FastAPI 가 **Jinja2 템플릿**으로 HTML 을 내려주고([app/web/router.py](../../../app/web/router.py))
가입·로그인·질문·내 기록·로그아웃 같은 동작만 자바스크립트 `fetch` 로 JSON API 를 호출합니다. 서버 하나로 화면과 API 를 함께 제공해서 배포가 단순하고 빌드 도구도 없습니다.
템플릿은 `base.html` 하나를 공통 틀(머리말·본문·바닥글)로 두고 페이지마다 이어 씁니다.
CSRF 헤더 붙이기, 401 이면 로그인 화면으로 보내기 같은 공통 처리는 [api.js](../../../app/static/js/api.js) 한 파일에 모았습니다.

**🧑‍🏫 퍼실:** 질문하면 답이 같은 화면에 어떻게 나오죠?

**🎨 C:** 페이지를 새로 불러오지 않고, 자바스크립트가 서버 응답 JSON 을 받아 대화 영역 아래에 추가합니다.
[chat.js](../../../app/static/js/chat.js) 가 폼의 기본 전송을 `preventDefault()` 로 막고 `sendQuestion()` → `send()` → `askServer()` 순서로 보냅니다.
첫 질문이면 `POST /api/conversations` 로 대화를 먼저 만들고 그 id 로 `POST /api/chat` 을 부르며, 응답의 `answer` 는 `showAnswer()` → `addAnswer()` 가 말풍선으로 만들어 붙입니다.
질문 아래 시각은 서버의 UTC(`…Z`)를 화면에서만 한국 시간으로 바꿔 적습니다. 주소는 `/chat?conversation=<id>` 로만 바꿔서(`history.replaceState`) 새로고침해도 같은 대화가 이어집니다.
→ [test_chat_page.py](../../../tests/web/test_chat_page.py): `test_chat_script_calls_the_spec_apis_in_order`, `test_chat_script_shows_times_in_korea_time`,
[test_chat_retry_rules_match_server.py](../../../tests/web/test_chat_retry_rules_match_server.py): `test_question_and_follow_up_on_the_real_server`

### 중복 전송·다시 보내기

**🧑‍🏫 퍼실:** 답변을 기다리는 동안 전송 버튼을 여러 번 누르면요?

**🎨 C:** 보내는 순간 `setWaiting(true)` 가 [보내기]·후속·새 대화·다시 보내기 버튼을 잠그고 질문 칸은 읽기 전용으로 둡니다.
[보내기] 글자는 "기다리는 중…" 으로 바뀌고 답변 자리에 "답변을 만드는 중" 표시를 띄웁니다. 잠긴 동안 들어온 Enter·클릭은 `isLocked()` 에서 무시합니다.
그리고 질문마다 새 UUID 를 `client_request_id` 로 같이 보내서, 혹시 같은 요청이 두 번 가도 서버가 AI 를 두 번 호출하지 않습니다(서버 쪽 처리는 B).
→ `test_chat_script_locks_buttons_while_waiting`, `test_chat_script_makes_new_uuid_for_every_question`, 3장 ③(Enter 3번 → `POST /api/chat` 1번)

**🧑‍🏫 퍼실:** 실패해서 다시 보낼 때는 요청 번호가 같나요, 새로 만드나요?

**🎨 C:** 실패한 이유에 따라 다릅니다. 응답을 아예 못 받았으면(연결 끊김, JSON 이 아닌 응답) 서버가 처리했는지 모르니 **같은 번호**로 보냅니다.
서버가 이미 답을 만들었으면 AI 를 다시 부르지 않고 저장한 답을 돌려주기 때문이고, `409 CHAT_BUSY`(아직 처리 중)도 같은 번호입니다.
서버가 실패를 알려 온 경우(504 시간 초과, 429 한도 등)는 같은 번호면 저장된 실패가 그대로 오므로 **새 번호**를 만듭니다. 판단은 `api.js` 의 `outcomeUnknown()`, 규칙은 `chat.js` 의 `showFailure()`·`resendFailed()` 입니다.
PR #47 에서 B 님이 "처리 중인데 60초가 지나면 새 번호" 규칙이 중복 처리를 만들 수 있다고 짚어 주셔서, 서버가 실패를 확정하기 전에는 번호를 바꾸지 않게 고쳤습니다(`c3b15e7`).
→ `test_same_key_after_a_lost_response_returns_the_saved_answer_without_ai`, `test_same_key_after_a_reported_failure_repeats_it_so_the_screen_uses_a_new_key`,
[js/chat_retry.test.mjs](../../../tests/web/js/chat_retry.test.mjs)

### 보안

**🧑‍🏫 퍼실:** AI 답변에 `<script>` 같은 게 섞여 오면 위험하지 않나요?

**🎨 C:** 질문·답변·서버 오류 문구를 모두 `innerHTML` 이 아니라 **`textContent`** 로 넣어서, HTML 이 아니라 글자로만 표시됩니다. 스크립트가 실행되지 않습니다.
`innerHTML` 이면 `<img src=x onerror=…>` 같은 코드가 실행될 수 있습니다. 말풍선은 `chat.js` 의 `createBubble()`, 내 기록은 `history.js` 의 `bubble()` 에서만 만듭니다.
화면 스크립트에 `.innerHTML`·`insertAdjacentHTML` 같은 코드가 없는지 테스트가 확인하고, 내 기록 상세에 `<script>`·`<img onerror>` 가 섞인 글을 넣어 글자로만 보이는지도 Node 테스트로 확인합니다.
→ `test_scripts_never_parse_text_as_html`, `test_chat_script_puts_messages_in_as_text`, [js/history.test.mjs](../../../tests/web/js/history.test.mjs), 3장 ①·③

**🧑‍🏫 퍼실:** 로그인 안 한 사람한테 채팅 메뉴를 숨기면 충분하지 않나요?

**🎨 C:** 숨기는 건 보기 좋게 하는 것일 뿐이고, 주소를 직접 입력하면 들어올 수 있습니다. 그래서 메뉴는 숨기지 않고(머리말의 채팅·내 기록은 누구에게나 보임) **실제 권한 검사는 서버**가 합니다.
`/chat`·`/history` 페이지는 서버가 로그인을 확인해(`OptionalUserDep`) 비로그인이면 303 으로 `/login` 에 보내고, 질문·기록 API 는 A 의 `CurrentUserDep` 가 401 을 돌려줍니다.
화면은 401 을 받으면 보관한 토큰을 지우고 `/login?expired=1`("로그인이 풀렸어요")로 갑니다(`api.js` 의 `goToLogin()`).
로그인 뒤 POST 에는 로그인 응답의 `csrf_token`(이 탭의 sessionStorage, 없으면 `GET /api/auth/me`)을 `X-CSRF-Token` 헤더로 붙이고, 토큰이 낡아 403 `CSRF_REJECTED` 가 오면 새 토큰으로 한 번만 다시 보냅니다.
→ `test_chat_redirects_to_login_when_logged_out`, `test_requests_after_the_session_ended_get_401_so_the_screen_goes_to_login`, `test_stale_csrf_token_is_rejected_before_anything_is_saved`

> 💡 화면 담당도 **보안·오류 처리**를 질문받습니다. "서버가 막는다 + 화면은 어떻게 반응한다"를 함께 설명합니다.

### 오류·입력 검증

**🧑‍🏫 퍼실:** 오류가 나면 사용자는 뭘 보게 되나요?

**🎨 C:** 서버의 모든 오류가 `{"error": {"code", "message", "request_id"}}` 형식으로 오기 때문에, 화면은 `message` 를 오류 칸(`role="alert"`)에 그대로 보여 주고 `code` 로만 갈래를 나눕니다.
서버에 닿지 못했거나 JSON 이 아닌 응답이면 "서버에 연결하지 못했어요…" 같은 대체 문구를 씁니다(`failureMessage()`).
입력한 질문은 지우지 않고 버튼도 다시 풀어서, 포커스가 간 [다시 보내기]를 Enter 한 번으로 누를 수 있습니다.
422 는 다시 보내도 같아서 질문 칸으로 보내고, 429(질문 한도)는 10초 동안 보내기를 잠그고 남은 초를 보여 줍니다(연달아 걸리면 20·40·60초).
`request_id` 는 화면에 보여 주지 않습니다. 서버 로그와 맞춰 볼 때는 개발자 도구에서 응답 본문이나 `X-Request-ID` 헤더를 봅니다.
→ [test_chat_errors_and_retry.py](../../../tests/web/test_chat_errors_and_retry.py): `test_failure_shows_server_message_and_moves_focus_to_retry`, `test_rate_limit_locks_sending_and_shows_remaining_seconds`

**🧑‍🏫 퍼실:** 입력 검증은 화면에서 하나요, 서버에서 하나요?

**🎨 C:** 둘 다 합니다. 화면은 보내기 전에 빈 질문·2,000자 초과, 가입·로그인의 이메일 형식·100자, 비밀번호 8~64자·영어만을 먼저 확인해 무엇을 고칠지 바로 알려 줍니다(`chat.js` 의 `findQuestionProblem()`, `auth.js` 의 `findInputProblem()`).
화면 검사는 우회할 수 있어서, 최종 검사는 서버가 다시 해서 `422 VALIDATION_ERROR` 를 돌려줍니다. 서버 문구는 대부분 "입력값을 확인해 주세요." 한 문장이라, 무엇을 고칠지는 화면이 먼저 알려 주는 것입니다.
규칙 값은 [router.py](../../../app/web/router.py) 의 `AUTH_INPUT_RULES`·`CHAT_INPUT_RULES` 한 곳에서 HTML 속성(`maxlength`·`pattern` 등)으로 넘기고 JS 는 그 속성을 읽습니다. 화면과 서버 값이 어긋나면 교차 테스트가 실패합니다.
`maxlength` 를 넘는 붙여 넣기는 브라우저가 말없이 뒷부분을 잘라 넣어서, 잘린 채 보내지지 않게 아예 넣지 않고 안내합니다.
→ `test_screen_input_rules_match_the_real_chat_validation`, [test_auth_rules_match_server.py](../../../tests/web/test_auth_rules_match_server.py): `test_server_rejects_what_the_page_blocks`, `test_server_agrees_with_page_on_email_format`

### 내 기록

**🧑‍🏫 퍼실:** 내 기록은 어떻게 보여 주나요? 새로고침해도 남나요?

**🎨 C:** [history.js](../../../app/static/js/history.js) 가 `GET /api/me/conversations` 로 내 대화를 20개씩(최근에 질문한 대화가 위) 불러오고, [더 보기]로 다음 20개를 이어 붙입니다.
대화를 누르면 페이지를 새로 받지 않고 주소만 `/history?conversation=<id>` 로 바꿔(`history.pushState`) `GET /api/conversations/{id}` 의 질문·답변을 오래된 순서로 그립니다.
기록은 매번 서버 DB 에서 불러오니 새로고침해도 남고, 주소의 id 는 UUID 모양인지 먼저 확인해서 이상한 값이 다른 API 를 부르지 않게 했습니다.
[이어서 질문]은 `/chat?conversation=<id>` 를 열어 답을 받은 턴만 그리고 같은 대화 id 로 보내서, 서버가 그 대화의 최근 문맥을 붙여 답합니다.
남의 대화 id 를 넣으면 서버가 없는 대화와 똑같이 404 를 주고, 화면은 "대화를 찾을 수 없어요." 를 보여 줍니다.
→ [test_history_rules_match_server.py](../../../tests/web/test_history_rules_match_server.py): `test_list_comes_in_pages_of_the_screen_size`, `test_continuing_a_conversation_sends_its_answered_turns_as_context`, `test_missing_and_others_conversations_look_the_same_as_the_screen_message`

### 접근성·모바일

**🧑‍🏫 퍼실:** 키보드나 휴대폰으로도 쓸 수 있나요? 실제로 어떻게 확인했나요?

**🎨 C:** 입력칸마다 label 이 있고, 수준은 라디오 묶음이라 ←→ 로 고르며, 질문은 Enter 로 보내고 Shift+Enter 는 줄바꿈입니다(한글 조합 중인 Enter 는 보내지 않음).
페이지 맨 앞의 "본문으로 건너뛰기"로 메뉴를 건너뛸 수 있고, 오류가 나면 포커스가 오류 칸이나 [다시 보내기]로 갑니다. 화면 폭 520px 이하에서는 휴대폰 배치로 바뀌고 누르는 곳은 44px 이상입니다.
EE-21(PR #56)에서 헤드리스 Chrome 으로 키 입력만으로 가입부터 로그아웃까지(51단계), 375·320px 가로 넘침, 오류 뒤 버튼 잠금 해제를 확인했고 결과는 [화면 검증 기록](../../../tests/web/README.md)에 있습니다.
실제 스크린리더·Safari·Firefox·휴대폰 실기기로는 확인하지 못했고, 접근성 트리와 Chrome 흉내까지 봤습니다.
→ [test_accessibility.py](../../../tests/web/test_accessibility.py): `test_skip_link_is_the_first_stop_and_goes_to_main`, `test_every_form_field_has_a_name`,
[test_contrast.py](../../../tests/web/test_contrast.py), [test_mobile_style.py](../../../tests/web/test_mobile_style.py)

> 💡 "JS 는 어떻게 테스트했나요?"가 오면: pytest 는 JS 를 실행하지 못해서 세 갈래로 나눴습니다.
> ① HTML 구조·스크립트 규칙은 pytest(`test_chat_page.py` 등) ② JS 동작은 Node 기본 도구 `node:test` 로 실제 스크립트를 DOM·fetch 만 흉내 내어 실행(`tests/web/js/*.test.mjs`, `test_chat_js_behavior.py` 가 pytest 안에서 돌림)
> ③ 화면이 기대는 서버 동작은 실제 API 를 부르는 교차 테스트(`test_*_match_server.py`). 글자 대비는 `test_contrast.py` 가 WCAG 공식으로 계산합니다.

## 2. 읽을 코드 표

평가 때 열어서 가리킬 파일입니다. "무엇을 보여 주나"는 한 줄로 씁니다.

| 파일 | 무엇을 보여 주나 | 관련 테스트 |
|---|---|---|
| [app/web/router.py](../../../app/web/router.py) | 페이지 주소, 비로그인 303(`chat_page()`·`history_page()`), 화면 규칙 한곳(`AUTH_INPUT_RULES`·`CHAT_INPUT_RULES`·`HISTORY_RULES`) | [test_chat_page.py](../../../tests/web/test_chat_page.py): `test_chat_redirects_to_login_when_logged_out`, [test_auth_rules_match_server.py](../../../tests/web/test_auth_rules_match_server.py) |
| [app/static/js/chat.js](../../../app/static/js/chat.js) | `sendQuestion()` → `send()` → `askServer()`, 잠금(`setLocked()`·`isLocked()`), `createBubble()`(`textContent`), `showFailure()`·`resendFailed()`(요청 번호 규칙) | [test_chat_page.py](../../../tests/web/test_chat_page.py), [js/chat_retry.test.mjs](../../../tests/web/js/chat_retry.test.mjs), [test_chat_retry_rules_match_server.py](../../../tests/web/test_chat_retry_rules_match_server.py) |
| [app/static/js/api.js](../../../app/static/js/api.js) | `apiPost()`(CSRF 헤더·403 이면 한 번 더·401 이면 로그인 화면), `outcomeUnknown()`, `failureMessage()`, `isUuid()` | [test_chat_errors_and_retry.py](../../../tests/web/test_chat_errors_and_retry.py): `test_api_script_goes_to_login_on_401`, `test_api_script_resends_once_with_a_new_token_when_csrf_is_rejected` |
| [app/static/js/history.js](../../../app/static/js/history.js) | 목록 20개·더 보기, 상세 주소 전환(`pushState`), 답을 못 받은 턴 안내·접기, 이어서 질문 | [js/history.test.mjs](../../../tests/web/js/history.test.mjs), [test_history_rules_match_server.py](../../../tests/web/test_history_rules_match_server.py) |
| [app/templates/chat.html](../../../app/templates/chat.html) | label, 오류 칸 `role="alert"`·기다림 칸 `role="status"`, `aria-describedby`, 후속 버튼 | [test_accessibility.py](../../../tests/web/test_accessibility.py): `test_error_boxes_are_alerts_and_loading_lines_are_status` |
| [tests/web/README.md](../../../tests/web/README.md) | 화면 검증 체크리스트 18가지, 글자 대비 표, 데스크톱·휴대폰 캡처 | [test_contrast.py](../../../tests/web/test_contrast.py), [test_mobile_style.py](../../../tests/web/test_mobile_style.py) |

## 3. 결과 예측 → 실제 실행

코드를 읽고 **결과를 먼저 예측한 뒤** 실제로 돌려 봅니다. 예측이 틀린 곳이 설명이 약한 곳입니다.
아래 예측을 먼저 적은 뒤 **2026-10-12, 평가 문서 브랜치 `a4ac871` 코드 기준**으로 실행했습니다.
로컬 서버(가짜 AI·임시 DB)만 썼고 배포 서버에는 요청을 보내지 않았습니다. 구두 리허설을 대신하는 기록은 아닙니다.

| 해 볼 것 (명령·화면 동작) | 내 예측 | 실제 결과 |
|---|---|---|
| ① 화면 스크립트에서 글을 HTML 로 해석하는 코드 찾기 (아래 명령) | 0줄. `innerHTML` 이라는 낱말은 주석에만 있음 | **0줄**. 낱말은 `chat.js:134`·`history.js:299` 주석 2곳뿐 |
| ② 화면의 다시 보내기 규칙 ↔ 실제 서버 교차 테스트 | 12개 통과. 같은 번호 재전송은 같은 턴·AI 1번, 504 뒤 같은 번호는 504 그대로·새 번호는 200 | **12 passed** |
| ③ 로컬 서버에서 화면 조작: 로그아웃 상태 `/chat` → 가입·로그인 → 응답 지연(1.5초)을 걸고 질문 후 Enter 3번 → `<img src=x onerror=alert(1)>` 질문 | `/login` 으로 이동. 기다리는 동안 [보내기]가 "기다리는 중…" 으로 잠기고 "답변을 만드는 중". `POST /api/chat` 1번, 말풍선 1쌍, 페이지 이동 없음. 이상한 질문은 글자 그대로, 알림창 없음 | **예측대로(19가지 확인)**. 주소만 `/chat?conversation=<id>` 로 바뀜. 내 기록 상세에서도 글자 그대로 |

저장소 루트에서 실행하는 재현 명령입니다.

```bash
# ① 글을 HTML 로 해석하는 코드 (아무것도 나오지 않아야 함)
grep -rnE "\.(innerHTML|outerHTML)|insertAdjacentHTML|document\.write" app/static/js/

# ② 화면의 다시 보내기 규칙 ↔ 실제 서버
uv run --locked pytest -q tests/web/test_chat_retry_rules_match_server.py

# ③ 로컬 서버 (기본값이 가짜 AI) → http://localhost:8000
uv run uvicorn app.main:app
```

③ 은 저장소 밖의 헤드리스 Chrome 스크립트로 돌렸습니다. 손으로 할 때는 개발자 도구 Network 에서 느린 네트워크를 고르고 Enter 를 여러 번 누릅니다.
8000 이 아닌 포트로 띄우면 `SITE_ORIGIN` 도 그 주소로 맞춰야 가입·로그인이 됩니다.

같은 코드 기준 전체 검사: `uv run --locked ruff check .` 통과, `uv run --locked pytest -q tests/web` **345 passed**,
`node --test tests/web/js/*.test.mjs` **57개 통과**, `uv run --locked pytest -q` **733 passed**.
평가 문서 브랜치의 결과입니다. 다른 PR 이 머지되면 숫자가 달라질 수 있습니다.

## 4. 준비 메모

- **보여 줄 파일:** 2장 표의 6개. `chat.js` 의 `sendQuestion()` → `send()` → `askServer()` 에서 시작해 `createBubble()`(textContent)·`showFailure()`(오류·다시 보내기)로 이어 갑니다.
- **시연:** 로그아웃 상태 `/chat` → `/login` 이동 → 가입 → 로그인 → 수준 선택 후 질문(기다리는 동안 버튼 잠김) → 후속 버튼 → 내 기록 → 상세 → [이어서 질문] → 모바일 화면(개발자 도구 기기 모드 375px).
  개발자 도구는 기기 모드만 쓰고, 쿠키·sessionStorage 가 보이는 탭은 열지 않습니다.
- **추가 대비:**
  - 모바일·키보드 확인 방법 → 1장 마지막 질문, [화면 검증 기록](../../../tests/web/README.md) 3장(체크리스트)·4장(손으로 5분 확인)
  - 답을 못 받은 턴은 내 기록에서 원인 코드 대신 "~해요" 안내로 보이고, 2개 이상 이어지면 "답을 받지 못한 질문 N개" 로 접힙니다(`missingNote()`·`threadItems()`).
  - 대화 제목은 서버가 첫 질문 30자로 저장합니다(A, #53). 화면은 서버 제목이 "새 대화" 일 때만 첫 질문 앞부분으로 대신 보여 줍니다(`displayTitle()`).
  - ⚠️ [화면 검증 기록](../../../tests/web/README.md)에 적힌 `node --test tests/web/js/` 는 Node 24 에서 실패합니다. 평가 때는 `node --test tests/web/js/*.test.mjs` 로 돌립니다.
- **내 PR 설명 후보:** 6개 모두 머지 — [#36](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/36) EE-04 공통 레이아웃,
  [#38](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/38) EE-09 가입·로그인 화면,
  [#41](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/41) EE-12 채팅·로그아웃 버튼,
  [#47](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/47) EE-14 화면 API 통합·오류·다시 보내기,
  [#52](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/52) EE-17 내 기록·이어서 질문,
  [#56](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/56) EE-21 접근성·사용 가이드.
  리뷰 반영 예: #38 팀장님 리뷰로 비밀번호 최대 20→64자(`efc396c`), #47 B 님 변경 요청으로 처리 중이면 같은 요청 번호 유지(`c3b15e7`), #52 A 님 제안으로 기록 화면 제목의 포커스 테두리(`b9f8ce6`).
- **남은 개인 연습:** 구두 리허설은 아직 하지 않았습니다. 파일을 열고 "질문이 화면에 붙기까지", "다시 보낼 때 번호", "비로그인 접근"을 3분 안에 제 말로 말해 봅니다.
  "`textContent` 를 `innerHTML` 로 바꾸면?", "응답을 못 받았는데 새 번호로 보내면?" 같은 꼬리 질문도 답해 봅니다. 평가 당일 배포 주소 점검은 아직 완료로 기록하지 않습니다.
- **내 답변 메모:** (리허설 후 작성)

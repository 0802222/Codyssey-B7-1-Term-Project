# 🤖 B 나현준 평가 대비 — AI 호출, 설명 수준, 문맥 유지, AI 오류

[공통 문서](../2-evaluation-example.md)의 답변 요령(2장)과 진행 대본(3장)을 먼저 읽고, 이 파일로 **내 영역**을 준비합니다.
현재 코드와 실행 기록에 근거한 답변 메모입니다. 자동 검사와 현준님의 구두 리허설은 구분합니다.

## 1. 예상 질문과 답

**🧑‍🏫 퍼실:** 질문 하나가 들어오면 서버에서 어떤 순서로 처리되나요?

**🤖 B:** [router.py](../../../app/chat/router.py)에서 인증·CSRF와 입력을 확인하고,
[service.py](../../../app/chat/service.py)의 `answer_question()`으로 넘어갑니다.
사용자 번호는 브라우저가 보낸 값 대신 A 담당 인증 코드의 로그인 결과로 결정합니다.

```text
① 질문 앞뒤 공백 제거 후 1~2,000자, level 세 가지, UUID 형식 검증
② 로그인 사용자의 대화인지 확인 → 같은 요청 키가 있으면 저장된 결과 반환
③ 사용자당 새 질문 하나만 처리 → 질문을 pending 상태로 먼저 저장
④ 같은 사용자·대화의 완료 문맥 + 현재 질문 + 현재 수준 지침 구성
⑤ AI 호출 직전에 횟수 검사 → 제한 안이면 AI 호출 (기본 제한 30초)
⑥ 성공하면 답변 저장·completed → 화면에 반환
   AI 실패면 failed·오류 코드 저장 → 공통 오류 안내 반환
```

먼저 질문을 저장하면 AI가 실패해도 처리하던 턴이 남습니다.
AI를 기다리기 전 DB 트랜잭션은 끝내 두어 DB 쓰기를 오래 붙잡지 않습니다.
DB 자체가 저장에 실패하면 `503 DB_ERROR`를 반환합니다. 이 경우까지 failed 저장을 보장하지는 않습니다.
→ [test_success_commits_pending_before_ai_and_completed_after](../../../tests/chat/test_chat_api.py),
[test_result_save_failure_returns_db_error_and_keeps_pending](../../../tests/chat/test_chat_lifecycle.py).

**🧑‍🏫 퍼실:** 브라우저에서 AI를 바로 호출하지 않는 이유는요?

**🤖 B:** 브라우저에 API 키를 넣으면 사용자가 키를 볼 수 있어서 **서버에서만** 호출합니다.
키는 로컬 `.env`, 배포 Railway 환경변수에 두고 [Settings](../../../app/core/config.py) 한 곳에서 읽습니다.
키 파일은 Git에 올리지 않고, 화면에는 채팅 API 결과만 반환합니다.
서비스는 [AIProvider](../../../app/chat/provider.py)의 `generate_reply()`라는 약속만 사용합니다.
테스트에는 가짜 구현을 넣고, 실제 호출은 `AnthropicProvider`가 코디세이 게이트웨이에 보냅니다.
그래서 채팅·저장 코드를 바꾸지 않고 AI 구현을 바꿀 수 있습니다.

**🧑‍🏫 퍼실:** 문맥 유지는 어떻게 구현했나요?

**🤖 B:** [context.py](../../../app/chat/context.py)의 `build_messages()`가
**같은 사용자·같은 대화의 완료된 질문·답변**만 오래된 순서로 보냅니다.
한 턴은 질문·답변 한 쌍입니다. pending·failed·interrupted와 빈 답변은 제외하고 마지막에 현재 질문을 붙입니다.
“그걸 음식점에 비유해줘”도 앞 질문·답변과 함께 전달됩니다.
가짜 AI 테스트는 전달 흐름을, 실제 AI 샘플은 주제를 이어 답했는지를 확인하는 별도 증거입니다.

**🧑‍🏫 퍼실:** 왜 5턴인가요? 대화가 길어지면요?

**🤖 B:** 과거 대화를 전부 보내면 입력량과 비용이 커져서 **기본값을 최근 5턴·과거 내용 12,000자**로 제한했습니다.
12,000자는 토큰이 아니라 질문·답변 문자열의 문자 수 합입니다.
넘으면 가장 오래된 질문·답변을 한 쌍씩 빼고, 답변을 중간에서 자르지 않습니다.
현재 질문과 시스템 지침은 과거 문맥 예산에서 제외합니다. 현재 질문의 2,000자 제한은 입력 검증이 따로 맡습니다.
`CONTEXT_TURNS`, `CONTEXT_MAX_CHARS`는 0 이상이며, 둘 중 하나가 0이면 현재 질문만 보냅니다. 음수는 설정 단계에서 거절합니다.
→ [test_context.py](../../../tests/chat/test_context.py)의 12,000자 경계·0 설정 테스트.

**🧑‍🏫 퍼실:** 새 대화나 다른 사람의 대화가 섞이지 않나요?

**🤖 B:** DB 조회와 문맥 구성 모두 사용자 번호·대화 ID로 범위를 제한합니다.
다른 사람의 대화는 소유권 검사에서 404로 거절하고, 내 다른 대화도 문맥에 넣지 않습니다.
→ [test_a_different_user_or_conversation_cannot_reuse_the_history](../../../tests/chat/test_context.py),
[test_context_contains_only_completed_turns_in_this_conversation](../../../tests/chat/test_chat_api.py).

**🧑‍🏫 퍼실:** easy에서 advanced로 바꾸면 이전 수준이 남지 않나요?

**🤖 B:** 매번 [prompts.py](../../../app/chat/prompts.py)의 `build_system_prompt(request.level)`를 새로 만듭니다.
과거 답변은 주제 문맥이고, 현재 난이도는 이번 시스템 지침이 결정합니다.
easy는 일상 단어·비유, beginner는 기본 용어·흐름, advanced는 원리·전제·한계를 요구합니다.
배포에서 “도커? → 더 쉽게 → advanced로 도커?”에 문맥을 못 받았다고 답한
[#54](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/issues/54)가 있었습니다.
[#55](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/55)에서 짧거나 반복된 질문도 현재 수준으로 바로 설명하도록 보완했습니다.
가짜 AI로 전달 메시지 1·3·5개와 advanced 지침을 확인하고 실제 샘플도 따로 검토했습니다.
모든 답변의 정확성을 보장한다는 뜻은 아닙니다. → [수정·실제 AI 기록](../../../app/chat/ISSUE-54.md).

**🧑‍🏫 퍼실:** AI가 응답을 안 주면요?

**🤖 B:** 기본 30초 제한을 서비스와 실제 provider에 걸고 SDK 자동 재시도는 `max_retries=0`으로 껐습니다.
초과하면 `504 AI_TIMEOUT`과 “응답이 지연되고 있어요. 잠시 후 다시 시도해 주세요.”를 반환하고,
턴은 failed, 답변은 비워 둡니다. 서버는 다음 요청을 계속 받습니다.
연결·상위 서버 오류는 `502 AI_UPSTREAM_ERROR`, AI 인증·한도 등 이용 불가는 `503 AI_UNAVAILABLE`로 구분합니다.
외부 예외 원문 대신 정해진 코드·안내만 저장하고 반환합니다.

**🧑‍🏫 퍼실:** 다시 보내면 AI를 두 번 부르지 않나요?

**🤖 B:** `client_request_id`는 브라우저의 **질문 전송 키**, `X-Request-ID`는 서버의 **HTTP 요청 추적 ID**입니다.
같은 키·같은 내용이면 completed는 저장 답변, failed는 저장 오류를 반환하고 AI를 다시 부르지 않습니다.
pending은 `409 CHAT_BUSY`, 같은 키에 다른 내용은 `409 REQUEST_CONFLICT`입니다.
응답을 못 받아 중복 확인할 때는 같은 키, 실패가 확정된 질문을 새로 시도할 때는 새 키를 씁니다.
완료 재전송 본문에는 최초 요청 ID가 남고 헤더에는 이번 HTTP 요청 ID가 새로 붙습니다.
→ [중복·실패 재시도 테스트](../../../tests/chat/test_chat_api.py).

**🧑‍🏫 퍼실:** 질문 횟수 제한은 어떻게 세나요?

**🤖 B:** [rate_limit.py](../../../app/chat/rate_limit.py)에서 AI 호출 직전에만 셉니다.
기본은 사용자 최근 60초 10회, 서비스 전체 UTC 하루 200회입니다. UTC 0시는 한국 오전 9시입니다.
AI를 시작한 시간 초과·오류도 한도를 쓰지만, 입력 거절·중복 반환·호출 전 DB 실패는 쓰지 않습니다.
한도에 걸린 새 질문은 `429 RATE_LIMITED` 실패 턴으로 저장하며 같은 키 재전송은 그대로 429입니다.
횟수·처리 중 표시는 서버 메모리라 worker·서버가 하나일 때 쓰는 구조입니다.
재시작하면 횟수가 초기화되므로 하루 200회는 과금의 강제 상한이 아닙니다. 키 예산은 콘솔에서 따로 확인합니다.
→ [test_chat_limits.py](../../../tests/chat/test_chat_limits.py), [EE-16 운영 한계](../../../app/chat/EE-16.md).

**🧑‍🏫 퍼실:** 실제 시간 초과·복구도 확인했나요?

**🤖 B:** 자동 테스트는 느린 가짜 AI·임시 DB로 확인했고, **2026-10-11 KST**에는 팀장님과 실제 배포를 점검했습니다.
팀장님이 제한을 1초로 낮춰 재배포한 뒤 1건의 504·failed·`answer=null`을 확인했습니다.
30초 복구 신호 후 새 요청 키로 1건을 보내 200·completed·저장 답변 일치를 확인했습니다.
각 요청의 같은 키 재전송과 전후 `/health`도 확인했습니다. 신규 AI 질문은 합계 2건입니다.
이 운영 점검의 배포 코드 기준은 `03f84e6`입니다. 이후 배포 전체를 다시 검증한 자료로 말하지 않습니다.
EE-23의 앞선 품질 수집은 수준별 3건·후속 질문 2건, 합계 **5건**입니다.
그 원본은 보존했고, 최종 배포 운영 점검 때 5건을 재실행하지 않았습니다. 품질 5건과 운영 신규 2건은 별도 기록입니다.
HTTP·기록 조회는 B의 수집 결과이고 Railway 로그·설정 복구는 팀장님 제공 자료입니다.
로그의 AI 구간은 timeout 1.002초·복구 10.371초였고 두 재전송에 추가 AI 시작은 없었습니다.
복구 수집은 새 합성 계정이므로 기존 실패 계정의 화면 잠금 해제를 확인한 증거는 아닙니다.

최종 증빙은 PR #51의 `26384cf` 고정 링크로 보여 줍니다.
[EE-23 운영 기록](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/blob/26384cf/app/chat/EE-23.md),
[시간 초과 HTTP](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/blob/26384cf/app/chat/samples/ee-23-2026-10-11-production-timeout.json),
[복구 HTTP](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/blob/26384cf/app/chat/samples/ee-23-2026-10-11-production-recovery.json),
[시간 초과 로그](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/blob/26384cf/app/chat/samples/ee-23-2026-10-11-timeout-logs.json),
[복구 로그](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/blob/26384cf/app/chat/samples/ee-23-2026-10-11-recovery-logs.json).
키·쿠키·사용자 식별자는 공개 증빙에서 제외했습니다. 설명 품질은 [EE-19](../../../app/chat/EE-19.md)의 실제 답변·수동 검토와 구분합니다.

## 2. 읽을 코드 표

| 파일 | 무엇을 보여 주나 | 관련 테스트 |
|---|---|---|
| [schemas.py](../../../app/chat/schemas.py) | 질문 공백·1~2,000자·수준·UUID 검증, 임의 user_id 거절 | [test_chat_api.py](../../../tests/chat/test_chat_api.py): `test_invalid_input_does_not_save_or_call_ai` |
| [service.py](../../../app/chat/service.py) | 소유권→중복→pending→문맥→한도→AI→저장 | [test_chat_api.py](../../../tests/chat/test_chat_api.py), [test_chat_lifecycle.py](../../../tests/chat/test_chat_lifecycle.py) |
| [context.py](../../../app/chat/context.py) | 같은 사용자·대화의 완료 Q/A, 예산, 현재 질문 유지 | [test_context.py](../../../tests/chat/test_context.py) |
| [prompts.py](../../../app/chat/prompts.py) | 현재 수준의 시스템 지침, 반복·후속 질문 원칙 | [test_prompts.py](../../../tests/chat/test_prompts.py), [test_chat_api.py](../../../tests/chat/test_chat_api.py): `test_repeated_short_question_keeps_context_when_switching_to_advanced` |
| [anthropic_provider.py](../../../app/chat/anthropic_provider.py) | 서버 키 호출, 시간 제한, 자동 재시도 0, 예외 원문 제거 | [test_anthropic_provider.py](../../../tests/chat/test_anthropic_provider.py) |
| [rate_limit.py](../../../app/chat/rate_limit.py) | 최근 60초·UTC 하루 집계와 메모리 한계 | [test_rate_limit.py](../../../tests/chat/test_rate_limit.py), [test_chat_limits.py](../../../tests/chat/test_chat_limits.py) |

## 3. 결과 예측 → 실제 실행

아래 예측을 먼저 작성한 뒤 **2026-10-11, `68b30f3` 코드 기준**으로 실행했습니다.
가짜 AI·임시 DB만 사용하며 실제 배포에 추가 질문을 보내지 않습니다. 구두 리허설 완료를 대신하는 기록은 아닙니다.

| 해 볼 것 | 실행 전 예측 | 실제 결과 |
|---|---|---|
| 입력 검증·길이 경계 (①) | 공백·2,001자·잘못된 수준 등은 422, 저장·AI 호출 0회. 1자·2,000자는 200 | **10 passed**. 거절 시 저장·AI 호출 0회, 허용 길이의 200 확인 |
| 문맥 경계·분리·수준 전환 (②) | 12,000자는 유지, 초과 시 오래된 Q/A 제거. 0이면 현재 질문만. 다른 사용자·대화 제외. 반복 질문도 이번 advanced 지침 전달 | **43 passed**. 예산·분리·0 설정과 반복 질문의 현재 advanced 전달 확인 |
| 시간 제한·실패 재전송·횟수 (③) | 느린 AI 중단·failed 저장. 같은 키는 추가 AI 없이 같은 오류, 실패 시도는 한도 소모. 60초·UTC 날짜 경계 적용 | **22 passed**. 서비스 시간 초과·실패 저장·같은 키 AI 미호출·한도 경계 확인 |

저장소 루트에서 실행하는 재현 명령입니다.

```bash
# ① 입력 검증과 허용 길이
uv run --locked pytest -q tests/chat/test_chat_api.py::test_invalid_input_does_not_save_or_call_ai tests/chat/test_chat_api.py::test_question_boundaries_are_accepted

# ② 문맥·현재 수준
uv run --locked pytest -q tests/chat/test_context.py tests/chat/test_chat_api.py::test_repeated_short_question_keeps_context_when_switching_to_advanced tests/chat/test_chat_api.py::test_context_respects_settings_and_zero_disables_history

# ③ 시간 초과·오류·한도
uv run --locked pytest -q tests/chat/test_chat_lifecycle.py::test_service_enforces_deadline_even_when_provider_does_not tests/chat/test_chat_api.py::test_ai_failure_is_saved_sanitized_and_replayed_without_another_call tests/chat/test_chat_limits.py::test_fake_failure_consumes_allowance_but_replay_does_not_call_ai tests/chat/test_rate_limit.py
```

같은 코드 기준 전체 검사: `uv run --locked ruff check .` 통과,
`uv run --locked pytest` **733 passed (31.65초)**.
이는 평가 문서 브랜치의 결과입니다. 이후 main의 테스트 수나 EE-23 당시 결과와 섞지 않습니다.

## 4. 준비 메모

- **보여 줄 파일:** 2장 표의 6개. `answer_question()` 처리 순서에서 문맥·지침·provider·한도로 연결합니다.
- **시연 순서:** “API가 뭐야?” easy·advanced 비교 → 후속 질문 → 내 기록 → 기존 EE-23 시간 초과·복구 증빙. 실제 질문·설정 변경은 팀장님과 정한 시연 시간에만 합니다.
- **로그 설명:** `request_received → pending 저장 → ai_call_start → ai_call_success/failed → 결과 저장 → request_completed`. HTTP 총 대기와 AI 구간의 대기 시간은 다릅니다.
- **내 PR 설명 후보:** [#44](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/44)는 EE-16이며 기능·테스트·문서·main 동기화 4개 커밋입니다. 지윤씨 리뷰에서 AI 직전 집계·실패 횟수 유지·API 계약 연결을 확인했습니다. [#55](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/55)는 실제 AI 반복 질문 지침 보완, [#51](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/51)은 배포 검증·로그 증빙입니다.
- **어려움 설명 후보:** #54처럼 문맥 전달 코드가 있어도 실제 AI는 다르게 답할 수 있었습니다. 전달 테스트와 실제 답변 검토를 나눠 지침을 보완했습니다. 모든 질문의 정확성을 보장한다고 말하지 않습니다.
- **한계 답변:** 최근 문맥만 사용하며 메모리 한도는 재시작·여러 서버의 과금 상한이 아닙니다. 키 잔여량은 실행 당시 운영자 보고이며 현재 수치로 말하지 않습니다.
- **남은 개인 연습:** 파일을 열고 흐름을 3분 안에 말해 보기. “왜 pending을 먼저 저장하나?”, “같은 키와 새 키는 언제 쓰나?”, “12,000자와 토큰은 왜 다른가?”를 자기 말로 답해 봅니다. 구두 리허설·평가 당일 네트워크·계정 점검은 아직 완료로 기록하지 않습니다.

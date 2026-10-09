# EE-05: AI provider 경계와 Fake

`provider.py`의 `ChatMessage`, `AIResult`, `AIProvider` 계약을 그대로 사용합니다.
`get_ai_provider(settings)`는 서버의 `SettingsDep`로 선택하고, 라우터에서는
`AIProviderDep`로 주입받습니다. 공개 query/body로 provider나 Fake 모드를 선택하지 않습니다.

- `AI_PROVIDER=fake`: 외부 API·키 없이 `FakeAIProvider`를 반환합니다.
- `AI_PROVIDER=anthropic`: `AnthropicProvider`가 설정된 게이트웨이에 요청합니다.
  실제 AI 설정을 Fake 성공으로 대체하지 않습니다.
- `/api/chat`의 요청 검증·문맥·DB 저장 연결은 EE-13에서 구현했습니다.
  전체 처리 순서와 실패 시 동작은 [EE-13 안내](EE-13.md)를 참고합니다.

Fake의 기본 결과는 `model="fake"`인 모의 답변입니다. 실제 모델이나 토큰 사용량을 주장하지 않습니다.
`generate_reply()`는 문맥·시스템 지침·시간 제한·출력 상한 인자를 받지만, 외부 호출이나 실제 대기,
문맥 수정·보관, 입력/출력 로그 기록을 하지 않습니다. 실제 시간·출력 토큰 제한은
`AnthropicProvider`가 적용하고, 채팅 서비스도 전체 대기 시간을 제한합니다.

## 실패 재현

모드는 테스트 코드에서 객체를 만들 때 지정합니다.

```python
from app.chat.fake_provider import FakeAIProvider, FakeMode

provider = FakeAIProvider(mode=FakeMode.TIMEOUT)
# await provider.generate_reply(...) → AITimeoutError
```

| mode | 결과 |
|---|---|
| `success` | `AIResult(text=reply, model="fake")` |
| `timeout` | `AITimeoutError` |
| `upstream_error` | `AIUpstreamError` |
| `unavailable` | `AIUnavailableError` |
| `empty` | 빈 응답을 `AIUpstreamError`로 알림 |

`reply`가 빈 값·공백뿐인 경우도 `AIUpstreamError`입니다. HTTP 오류 매핑과 실패 저장은
EE-13에 연결했습니다. [EE-16](EE-16.md)에서는 AI 호출 직전 사용자별 최근 60초와
서비스 전체 UTC 하루 횟수를 제한합니다. 한도 초과는 AI 없이 429로 응답합니다.

## 의존성 교체

```python
from app.chat.fake_provider import FakeAIProvider, FakeMode
from app.chat.provider import get_ai_provider

app.dependency_overrides[get_ai_provider] = lambda: FakeAIProvider(mode=FakeMode.TIMEOUT)
# 테스트 후 app.dependency_overrides.clear()
```

이 방식으로 실제 AI·인증·DB 연결 없이 provider 계약과 실패 경로를 검증할 수 있습니다.
수준별 프롬프트·최근 문맥은 [EE-10](EE-10.md), 실제 AI·채팅 처리 순서는
[EE-13](EE-13.md)에 설명했습니다.

실제 답변의 수준 차이·후속 문맥·정의와 예시를 검토한 기록은 [EE-19](EE-19.md)에 모았습니다.
수집 도구는 수동 실행할 때만 실제 AI를 호출하며, 자동 테스트와 품질 검토를 구분합니다.

배포 서버의 실제 답변·저장·시간 초과·운영 로그·키 한도 검증은 [EE-23](EE-23.md)에 기록합니다.

검증 명령: `uv run pytest tests/chat`, `uv run pytest`, `uv run ruff check .`.

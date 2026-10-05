# EE-05: AI provider 경계와 Fake

`provider.py`의 `ChatMessage`, `AIResult`, `AIProvider` 계약을 그대로 사용합니다.
`get_ai_provider(settings)`는 서버의 `SettingsDep`로 선택하고, 라우터에서는
`AIProviderDep`로 주입받습니다. 공개 query/body로 provider나 Fake 모드를 선택하지 않습니다.

- `AI_PROVIDER=fake`: 외부 API·키 없이 `FakeAIProvider`를 반환합니다.
- `AI_PROVIDER=anthropic`: 실제 연결은 EE-13에서 구현하므로 현재는 `501 NOT_IMPLEMENTED`입니다.
  실제 AI 설정을 Fake 성공으로 대체하지 않습니다.
- `/api/chat` 연결은 EE-13 범위이며, EE-05만으로 채팅 API가 완성된 것은 아닙니다.

Fake의 기본 결과는 `model="fake"`인 모의 답변입니다. 실제 모델이나 토큰 사용량을 주장하지 않습니다.
`generate_reply()`는 문맥·시스템 지침·시간 제한·출력 상한 인자를 받지만, 외부 호출이나 실제 대기,
문맥 수정·보관, 입력/출력 로그 기록을 하지 않습니다. 입력 시간·토큰 예산을 실제로 적용하는 호출은
후속 실제 provider에서 구현합니다.

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

`reply`가 빈 값·공백뿐인 경우도 `AIUpstreamError`입니다. HTTP 오류 매핑은 EE-16에서 구현합니다.

## 의존성 교체

```python
from app.chat.fake_provider import FakeAIProvider, FakeMode
from app.chat.provider import get_ai_provider

app.dependency_overrides[get_ai_provider] = lambda: FakeAIProvider(mode=FakeMode.TIMEOUT)
# 테스트 후 app.dependency_overrides.clear()
```

이 방식으로 실제 AI·인증·DB 연결 없이 provider 계약과 실패 경로를 검증할 수 있습니다.
수준별 프롬프트·최근 문맥은 EE-10, 실제 AI·채팅 처리 순서는 EE-13에서 진행합니다.

검증 명령: `uv run pytest tests/chat`, `uv run pytest`, `uv run ruff check .`.

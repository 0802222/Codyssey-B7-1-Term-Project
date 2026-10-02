# EasyExplain

> 모르는 개념을 물어보면 **설명 수준(아주 쉽게 / 입문자 / 전공자)** 에 맞춰 풀어 주고,
> "더 쉽게", "예시 하나 더" 같은 후속 질문으로 이해를 넓혀 가는 AI 챗봇입니다.

Codyssey **B7-1 Term Project「웹 기반 AI 챗봇 서비스 개발 프로젝트」** 의 4인 팀 결과물입니다.

> **현재 상태:** 개발 환경(Python·의존성 버전 고정)만 준비된 단계입니다. 앱 코드는 아직 없습니다.
> 이 문서는 진행하면서 계속 채워 갑니다.

---

## 1. 이 미션은 무엇인가요?

리눅스·웹·DB·AI API를 **하나의 서비스로 연결해 기획부터 배포까지** 해 보는 팀 프로젝트입니다.
한 줄로 요약하면 다음 흐름을 직접 만드는 것입니다.

```
로그인한 사용자가 웹에서 질문 → FastAPI 서버가 AI API 호출 → 응답을 화면에 표시 → 질문·응답을 DB에 저장
```

### 과제가 요구하는 것 (반드시 지켜야 함)

| # | 요구사항 | 쉽게 말하면 |
|---|---|---|
| 1 | 웹 UI | 질문 입력창이 있고, 같은 화면에서 답을 볼 수 있어야 함 |
| 2 | 인증·접근 제어 | 회원가입/로그인이 되고, **로그인한 사람만** 챗봇을 쓸 수 있음 |
| 3 | AI 처리 | AI 호출은 **서버에서만** (키가 브라우저로 새면 안 됨) + **이전 대화 문맥 유지** |
| 4 | 대화 로그 | 질문·응답·사용자·시각을 DB에 쌓고, **사용자 기준으로 조회** 가능 |
| 5 | 운영 | 서버 로그(요청 수신 / AI 호출 / AI 성공·실패 / DB 저장 성공·실패), AI **타임아웃·실패 시 서버가 죽지 않고 오류 안내**, 입력 검증 |
| 6 | 배포 | 평가 시점에 **외부 네트워크에서 접속 가능한 URL** |
| 7 | 협업 | 브랜치 전략, **PR로 Merge**, **팀원 각자 의미 있는 커밋 10개 이상**, 문서의 역할 설명이 Git 기록과 일치 |

- 개발 환경: **Python + FastAPI** (필수), SQLite (권장)
- 제약: API 키 등 민감정보는 코드·문서에 쓰지 않고 `.env`로 관리, `.env`는 Git에 올리지 않음

### 제출물
GitHub 저장소 + README/기술 문서(개요, 구조, API 명세, DB 구조, 실행·배포 방법, 환경 변수,
**팀 역할·개인별 작업 요약**, 민감정보 관리, DB 확인 방법) + 외부 접속 가능한 서비스 URL

---

## 2. 팀 역할

| 역할 | 담당 | 주로 만지는 곳 |
|---|---|---|
| **L** 팀장 | 공통 뼈대, API 계약, CI, 통합 테스트, 배포 | `app/main.py`, `app/core/`, `tests/integration/`, `.github/` |
| **A** 팀원1 | 회원가입·로그인·세션, DB, 내 기록 API | `app/db/`, `app/auth/`, `app/conversations/` |
| **B** 팀원2 | AI 호출, 프롬프트, 문맥 유지, AI 오류 처리 | `app/chat/` |
| **C** 팀원3 | 웹 화면, API 연결, 사용성 | `app/web/`, `app/templates/`, `app/static/` |

> 자기 담당 폴더 위주로 작업합니다. 다른 사람 영역이나 공유 파일(`main.py`, `config.py`,
> `pyproject.toml` 등)을 바꿔야 하면 먼저 이슈/단톡으로 알려 주세요. 충돌을 줄이기 위한 약속입니다.

---

## 3. 기술 스택 — 각각 뭐 하는 도구인가요?

| 도구 | 한 줄 설명 | 우리 프로젝트에서의 역할 |
|---|---|---|
| **uv** | 파이썬 버전 + 패키지 관리 도구 (pip + venv + pyenv를 합친 것, 매우 빠름) | 4명의 개발 환경을 똑같이 맞춤 |
| **FastAPI** | 파이썬 웹 프레임워크 | 웹 페이지와 `/api/...` 요청을 처리하는 서버 |
| **Uvicorn** | FastAPI 앱을 실제로 띄워 주는 서버 프로그램 | `uv run uvicorn app.main:app` |
| **Jinja2** | HTML 템플릿 엔진 | 서버에서 HTML 화면 생성 (React 같은 별도 프런트 없음) |
| **SQLite** | 파일 하나로 동작하는 DB | 회원·대화 기록 저장 |
| **SQLModel** | 파이썬 클래스로 DB 테이블을 다루게 해 주는 라이브러리 | SQL을 직접 덜 쓰고 테이블 정의·조회 |
| **pydantic-settings** | 환경변수(.env)를 읽어 설정 객체로 만들어 줌 | API 키·DB 경로 등 설정 관리 |
| **pwdlib[argon2]** | 비밀번호 해시 라이브러리 | 비밀번호를 평문이 아닌 해시로 저장 |
| **anthropic** | Anthropic(Claude) 공식 파이썬 SDK | 코디세이 AI 게이트웨이를 통해 Claude 호출 |
| **pytest** | 테스트 실행 도구 | `uv run pytest` |
| **httpx** | HTTP 클라이언트 | FastAPI 테스트(TestClient)에 필요 |
| **ruff** | 코드 스타일 검사·정리 도구 | `uv run ruff check .` 로 실수·스타일 문제 확인 |

---

## 4. 처음 시작하기

### 4-1. uv가 뭔가요? 왜 쓰나요?

파이썬 프로젝트를 여럿이 하면 이런 일이 자주 생깁니다.

- A는 Python 3.8, B는 3.12 → 같은 코드가 한 명 컴퓨터에서만 에러
- `pip install fastapi`를 각자 다른 날 실행 → 서로 다른 버전이 깔려서 "내 컴퓨터에선 되는데?"

**uv는 이걸 막아 줍니다.** 이 저장소에는 아래 파일들이 있습니다.

| 파일 | 의미 | 누가 수정? |
|---|---|---|
| `.python-version` | 이 프로젝트는 **Python 3.12**를 쓴다 | 거의 안 바꿈 |
| `pyproject.toml` | 우리가 **쓰겠다고 선언한 패키지 목록** (예: `fastapi>=0.142`) | `uv add` 명령이 자동 수정 |
| `uv.lock` | 실제로 설치할 **정확한 버전이 전부 잠긴 목록** (하위 의존성까지) | **직접 수정 금지**, uv가 자동 관리 |

### 4-2. uv 설치 (한 번만)

```bash
# macOS
brew install uv

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

설치 확인: `uv --version`

### 4-3. 저장소 받고 `uv sync`

```bash
git clone https://github.com/0802222/Codyssey-B7-1-Term-Project.git
cd Codyssey-B7-1-Term-Project
uv sync
```

**`uv sync`는 무엇을 하나요?**

1. `.python-version`을 보고 **Python 3.12가 없으면 알아서 내려받습니다.** (따로 설치할 필요 없음)
2. 프로젝트 폴더 안에 **`.venv`(가상환경)** 를 만듭니다. → 내 컴퓨터의 다른 파이썬 프로젝트와 섞이지 않습니다.
3. `uv.lock`에 적힌 **정확히 같은 버전**의 패키지를 `.venv`에 설치합니다. → 4명 모두 완전히 같은 환경이 됩니다.

**언제 다시 하나요?** `git pull` 후 `pyproject.toml`이나 `uv.lock`이 바뀌었을 때.
헷갈리면 그냥 pull 할 때마다 `uv sync` 해도 됩니다. (바뀐 게 없으면 1초 안에 끝남)

### 4-4. 실행할 때는 `uv run`

```bash
uv run pytest                 # 테스트
uv run ruff check .           # 코드 검사
uv run uvicorn app.main:app --reload   # 서버 실행 (앱 뼈대가 만들어진 뒤 사용 가능)
```

`uv run`을 앞에 붙이면 **이 프로젝트의 `.venv` 파이썬으로 실행**됩니다.
가상환경을 직접 activate 할 필요가 없고, 실수로 다른 파이썬(예: 시스템 3.8, conda)으로 실행하는 일도 막아 줍니다.

> VS Code를 쓴다면 `Cmd/Ctrl + Shift + P` → "Python: Select Interpreter" → `./.venv`를 선택하면
> 자동완성·에러 표시도 같은 환경 기준으로 동작합니다.

### 4-5. 패키지를 추가하고 싶으면?

```bash
uv add 패키지이름           # 서비스에 필요한 패키지
uv add --dev 패키지이름     # 테스트/개발에만 필요한 패키지
```

`pip install`은 쓰지 마세요. `pyproject.toml`·`uv.lock`에 기록되지 않아 다른 팀원 환경에는 안 깔립니다.
의존성 추가는 공유 파일 변경이므로 **팀장에게 먼저 알려 주고**, 바뀐 `pyproject.toml`과 `uv.lock`을 함께 커밋합니다.

---

## 5. 환경 변수 (.env)

API 키처럼 **공개되면 안 되는 값은 코드가 아니라 `.env` 파일**에 둡니다.
`.env`는 `.gitignore`에 등록되어 있어서 Git에 올라가지 않습니다.

- 앱 뼈대 작업 때 **`.env.example`(이름만 있고 값은 빈 파일)** 이 추가될 예정입니다.
  이 파일을 복사해서 `.env`를 만들고 값만 채우면 됩니다: `cp .env.example .env`
- AI 키는 코디세이에서 발급받은 **가상 키**를 사용합니다. Anthropic 규격의 코디세이 게이트웨이(`https://copa.codyssey.kr`)를 거칩니다.
- **키 값을 단톡·이슈·PR·커밋·스크린샷에 절대 붙여 넣지 마세요.**

예정된 주요 변수 이름 (확정 시 갱신):

| 변수 | 용도 |
|---|---|
| `APP_ENV` | development / test / production |
| `DATABASE_URL` | SQLite 파일 위치 |
| `AI_PROVIDER` | `fake`(키 없이 개발·테스트) 또는 `anthropic` |
| `ANTHROPIC_BASE_URL` | AI 게이트웨이 주소 |
| `ANTHROPIC_API_KEY` | 발급받은 가상 키 (**비밀**) |
| `AI_MODEL` | 사용할 모델 ID (예: `claude-sonnet-4`) |
| `AI_TIMEOUT_SECONDS` | AI 응답 최대 대기 시간 |

> 실제 키가 없어도 개발할 수 있도록 **Fake AI provider**(가짜 응답기)를 둘 예정입니다.
> 자동 테스트도 Fake로 돌기 때문에 키를 공유할 필요가 없습니다.

---

## 6. 협업 규칙 (요약)

**작업 흐름**

```
이슈 고르기 → main 최신화(git pull) → 기능 브랜치 생성 → 구현 → 테스트 → 커밋 → PR → 다른 팀원 리뷰 → Merge
```

- **main에 직접 push 금지.** 모든 변경은 PR로 들어갑니다.
- 브랜치 이름: `feat/ee-08-auth-session`, `fix/ee-18-integration`, `chore/ee-02-bootstrap` 처럼 `종류/이슈코드-짧은설명`
- PR 병합 방식: **"Create a merge commit"** 사용 (**Squash 금지**)
  → Squash는 여러 커밋을 하나로 합쳐 버려서, 과제의 "개인별 커밋 10회 이상" 증빙이 사라집니다.
- 커밋은 **의미 있는 단위**로 (기능 하나, 테스트 추가, 버그 수정 등). 공백 수정·빈 커밋으로 개수 채우기 X
- 커밋 작성자는 **본인 GitHub 계정**이어야 합니다. 처음 한 번 설정:
  ```bash
  git config --local user.name "본인 이름"
  git config --local user.email "본인 GitHub에 연결된 이메일"
  ```
- AI 코딩 도구(Codex, Claude Code 등)를 써도 되지만, **코드는 본인이 이해하고 설명할 수 있어야** 합니다. 발표·평가 때 각자 설명해야 합니다.

---

## 7. 앞으로 채워질 내용

- [ ] 시스템 구조도, 폴더 구조
- [ ] API 명세 (요청/응답 예시)
- [ ] DB 구조 (테이블·필드 설명)
- [ ] 실행·배포 방법, 서비스 URL
- [ ] DB 확인 가이드 (`scripts/check_logs.sql` 등)
- [ ] 팀원별 작업 요약

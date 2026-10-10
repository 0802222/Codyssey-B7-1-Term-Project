# EasyExplain

> 모르는 개념을 물어보면 **설명 수준(아주 쉽게 / 입문자 / 전공자)** 에 맞춰 풀어 주고,
> "더 쉽게", "예시 하나 더" 같은 후속 질문으로 이해를 넓혀 가는 AI 챗봇입니다.

Codyssey **B7-1 Term Project「웹 기반 AI 챗봇 서비스 개발 프로젝트」** · 4인 팀

> **현재 상태:** 앱 뼈대, 회원가입·로그인 API 까지 구현. 채팅·기록·배포는 진행 중입니다. 과제 요구사항별 근거와 진행 상태는 [6장](#6-과제-요구사항과-제출-점검).

<details>
<summary><b>👥 팀원용 문서 안내 — 언제 무엇을 읽나요?</b></summary>

| 언제 | 문서 | 내용 |
|---|---|---|
| ① 첫 회의 | [docs/team/1-kickoff.md](docs/team/1-kickoff.md) | 과제 소개, 역할 정하기, 커밋·API·DB 합의 |
| ② 착수할 때 + 매번 | [CONTRIBUTING.md](CONTRIBUTING.md) | 처음 할 일·뼈대 둘러보기, **매번 하는 루틴 11단계**, 역할별 안내 |
| 매번 | [작업 보드](https://github.com/orgs/easy-explain/projects/1) | 24개 작업 이슈와 진행 상황 (내 작업: `assignee:@me`) |
| 작업 중 수시로 | [docs/spec/api.md](docs/spec/api.md) · [docs/spec/db.md](docs/spec/db.md) | API 명세, DB 구조 (바꾸려면 PR 먼저) |
| ③ 평가 전 | [docs/team/2-evaluation-example.md](docs/team/2-evaluation-example.md) | 예상 진행 대본, 내 코드 설명 준비 |
| 읽지 않아도 됨 | `AGENTS.md`, `CLAUDE.md` | AI 코딩 도구가 읽는 규칙 (CONTRIBUTING 요약본) |

</details>

---

## 1. 과제 소개

**"AI 챗봇 웹사이트를 4명이 만들어서, 누구나 접속할 수 있게 인터넷에 올리는 것"** 입니다.
AI 를 직접 만드는 게 아니라, 이미 있는 AI(Claude)를 **우리 서버가 대신 불러 주는 서비스**를 만듭니다.

```
 웹 화면 (브라우저)  ──질문──▶  우리 서버 (FastAPI)  ──질문 + 이전 대화──▶  AI API (Claude)
                    ◀─답변──                       ◀────────답변────────
                                       │
                                       ▼ 질문·답변·시각 저장 / 조회
                                   DB (SQLite)
```

| 부품 | 비유 | 하는 일 |
|---|---|---|
| 웹 화면 | 🍽️ 손님 테이블과 메뉴판 | 질문을 입력하고 답을 보는 곳 |
| 우리 서버 (FastAPI) | 🧑‍💼 홀 직원 | 손님 확인(로그인), 주문을 요리사에게 전달, 기록, 문제 생기면 안내 |
| AI API (Claude) | 👨‍🍳 요리사 | 실제 설명(요리)을 만듦. 손님은 주방에 직접 못 들어감 (🔑 키는 서버만 가짐) |
| DB (SQLite) | 📒 주문 장부 | 누가 언제 무엇을 묻고 어떤 답을 받았는지 기록 |

### 반드시 지켜야 할 요구사항

| # | 요구사항 | 쉽게 말하면 |
|---|---|---|
| ① | 웹 UI | 질문을 입력하고 같은 화면에서 답을 봄 |
| ② | 인증 | 회원가입·로그인, **로그인한 사람만** 챗봇 사용 |
| ③ | AI 처리 | AI 호출은 **서버에서만**, **이전 대화를 기억** |
| ④ | 대화 기록 | 질문·답변·사용자·시각을 DB 에 쌓고 **사용자별로 조회** |
| ⑤ | 안정성 | 서버 로그, AI 실패·지연에도 **서버가 안 죽고 안내**, 입력 검증 |
| ⑥ | 배포 | 평가 때 **외부에서 접속 가능한 URL** |
| ⑦ | 협업 | 브랜치·PR 머지, **1인당 의미 있는 커밋 10개 이상** |

과제 원문 항목마다 어디서 만족하는지는 [6장 과제 요구사항과 제출 점검](#6-과제-요구사항과-제출-점검)에 있습니다.

---

## 2. 폴더 구조

```
app/
├─ main.py            # 앱 조립 (모든 부품 연결)
├─ health.py          # 서버 상태 확인 GET /health
├─ core/              # 설정 · 공통 오류 · 요청 ID · 서버 로그
├─ db/                # DB 연결, 테이블 정의
├─ auth/              # 회원가입·로그인 API, 로그인 확인
├─ conversations/     # 대화 만들기·내 기록 API
├─ chat/              # 채팅 API, AI 호출
├─ web/               # 페이지 주소
├─ templates/         # HTML
└─ static/            # CSS · JS
tests/                # 영역별 자동 테스트
docs/                 # API 명세 · DB 구조 · 평가 대비 가이드
scripts/              # DB 확인 SQL
CONTRIBUTING.md       # 작업 길잡이 (환경 준비 → 매번 하는 루틴)
AGENTS.md             # AI 코딩 도구용 규칙
```

- API 요청·응답 예시와 오류 코드: [docs/spec/api.md](docs/spec/api.md)
- DB 테이블·필드 설명: [docs/spec/db.md](docs/spec/db.md)

---

## 3. 주요 기능과 역할 분담

### 팀

| <img src="https://avatars.githubusercontent.com/u/132190391?v=4" width="100"> | <img src="https://avatars.githubusercontent.com/u/174287228?v=4" width="100"> | <img src="https://avatars.githubusercontent.com/u/25141255?v=4" width="100"> | <img src="https://avatars.githubusercontent.com/u/117568075?v=4" width="100"> |
|:---:|:---:|:---:|:---:|
| 이초롱<br>[@0802222](https://github.com/0802222) | 송지윤<br>[@js910](https://github.com/js910) | 나현준<br>[@vivleon](https://github.com/vivleon) | 유민규<br>[@Minkyu01](https://github.com/Minkyu01) |
| **L 팀장**<br>공통 뼈대 · 오류·로그 · CI · 통합 · 배포 | **A 인증·DB**<br>회원·로그인 · 접근 제어 · DB · 내 기록 | **B AI·채팅**<br>AI 호출 · 설명 수준 · 문맥 유지 · AI 오류 | **C 화면**<br>웹 화면 · API 연결 · 사용성 |

| 역할 | 이름 | 담당 |
|---|---|---|
| **L** 팀장 | 이초롱 | 공통 뼈대, 오류·로그, CI, 통합, 배포 |
| **A** | 송지윤 | 회원·로그인·접근 제어, DB, 내 기록 (서버) |
| **B** | 나현준 | AI 호출, 설명 수준, 문맥 유지, AI 오류 (서버) |
| **C** | 유민규 | 웹 화면, API 연결, 사용성 (화면) |

### 기능

로그인한 사용자가 **설명 수준을 골라 개념을 질문하면, AI 가 이전 대화를 기억하며 쉽게 설명**해 주는 챗봇입니다.
대화는 저장되어 나중에 다시 보고 이어서 질문할 수 있습니다. 자세한 기능과 담당은 아래 표를 참고하세요.

**사용 흐름:** 로그인 → 설명 수준 선택 → "API가 뭐야?" 질문 → 답변 → [더 쉽게]·후속 질문 → 내 기록에서 이어 보기

| 대분류 | 기능 | 설명 | 담당 | API · 화면 | 상태 | PR |
|---|---|---|---|---|---|---|
| **계정** | 회원가입 | 이메일·비밀번호, 비밀번호는 해시로 저장 | A 가입 API·DB<br>C 가입 화면 | `POST /api/auth/signup`<br>`/signup` | 🟨 | [#35](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/35) |
| | 로그인·로그아웃 | 세션 쿠키 발급·삭제 | A 세션 처리<br>C 로그인 화면 | `POST /api/auth/login`<br>`POST /api/auth/logout`<br>`/login` | 🟨 | [#37](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/37) |
| | 접근 제어 | 비로그인은 API 401, 페이지는 로그인으로 이동 | A | `GET /api/auth/me` | 🟨 | [#37](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/37) |
| **채팅** | 질문·답변 | 같은 화면에 답 표시, 대기 중 버튼 잠금 | B 채팅 API·AI 호출<br>C 채팅 화면 | `POST /api/chat`<br>`/chat` | ⬜ | |
| | 설명 수준 | 아주 쉽게 / 입문자 / 전공자 | B 수준별 프롬프트<br>C 수준 선택 UI | `POST /api/chat` 의 `level` | 🟨 | [#8](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/8) |
| | 문맥 유지 | 같은 대화의 최근 5턴을 기억 | B | (서버 내부) | 🟨 | [#8](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/8) |
| | 후속 버튼 | 더 쉽게 / 예시 하나 더 / 핵심만 | C | `/chat` | ⬜ | |
| **대화 기록** | 대화 만들기 | 새 대화 시작 | A | `POST /api/conversations` | ⬜ | |
| | 내 기록 조회 | 내 대화 목록·상세, 남의 대화는 볼 수 없음 | A 조회 API·권한<br>C 기록 화면 | `GET /api/me/conversations`<br>`GET /api/me/chats`<br>`/history` | ⬜ | |
| | DB 확인 도구 | 사용자별 최근 대화 조회 SQL | A | `scripts/check_logs.sql` | ⬜ | |
| **안정성** | 오류 안내 | AI 지연·실패·DB 오류에도 서버 유지, 공통 형식으로 안내 | L 공통 오류 형식<br>B AI 오류 처리<br>C 오류 메시지 표시 | 모든 API | 🟨 | [#4](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/4) |
| | 입력 검증 | 빈 질문, 2,000자 초과, 잘못된 값 차단 | B 서버 검증<br>C 화면 입력 제한 | `POST /api/chat` | 🟨 | [#4](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/4) |
| | 서버 로그 | 요청·AI 호출·DB 저장을 요청 ID 로 묶어 기록 | L 요청 로그<br>B AI 호출 로그<br>A DB 저장 로그 | 서버 로그 | 🟨 | [#4](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/4) |
| | 상태 확인 | 서버·DB 정상 여부 | L | `GET /health` | ✅ | [#4](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/4) |
| **배포·협업** | 외부 배포 | 공개 URL, 재시작해도 기록 유지 | L | 서비스 URL | ⬜ | |
| | 자동 검사 (CI) | PR 마다 코드 검사·테스트 자동 실행 | L | GitHub Actions | 🟨 | [#4](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/4) |

⬜ 미착수 · 🟨 일부 완료 · ✅ 완료 — 기능을 머지할 때 상태와 PR 번호를 함께 적습니다.

### 비제공 기능

과제의 핵심인 **로그인 → AI 질문 → 기록 저장 → 배포**를 안정적으로 완성하는 데 집중하기 위해,
아래 기능은 제공하지 않습니다. 필수 기능이 끝나도 기능을 늘리기보다 안정화를 우선합니다.

- PDF·파일 업로드
- 웹 검색 (최신 정보 반영)
- 음성·이미지 입력
- 소셜 로그인 (카카오, 구글 등)
- 결제
- 실시간 스트리밍 응답 (답변이 한 글자씩 나오는 방식)
- 관리자 화면 — 모든 사용자의 대화를 보는 화면은 공개 URL 에서 개인정보 노출 위험이 커서 만들지 않습니다.
  과제의 "DB 확인 가이드"(3가지 중 1개 이상)는 **내 기록 API**(`GET /api/me/chats`)와 **확인용 SQL**(`scripts/check_logs.sql`)로 제공합니다.
- 의료·법률·투자 조언 — AI 설명은 틀릴 수 있어 학습용 개념 설명으로만 제공합니다

---

## 4. 기술 스택

| 도구 | 무엇인가 | 왜 썼나 |
|---|---|---|
| **Python 3.12** | 프로그래밍 언어 | 과제 지정 |
| **FastAPI** | 파이썬으로 웹 서버를 만드는 도구 | 과제 지정 (아래 설명) |
| **Uvicorn** | FastAPI 서버를 실제로 켜 주는 프로그램 | FastAPI 표준 실행기 |
| **Jinja2** | HTML 에 데이터를 끼워 넣는 템플릿 도구 | 별도 프런트 서버(React 등) 없이 화면 제공 |
| **SQLite** | 파일 하나로 동작하는 DB | 과제 권장 (아래 설명) |
| **SQLModel** | 파이썬 클래스로 DB 테이블을 다루는 도구 | SQL 을 덜 쓰고 실수 줄이기 |
| **Claude (anthropic SDK)** | AI 모델과 공식 연결 도구 | 코디세이 AI 게이트웨이 제공 |
| **Argon2 (pwdlib)** | 비밀번호를 안전하게 해시하는 방식 | 비밀번호 평문 저장 방지 |
| **uv** | 파이썬 버전·패키지를 맞춰 주는 도구 | 4명의 개발 환경을 똑같이 |
| **pytest · ruff** | 자동 테스트 · 코드 검사 | PR 마다 품질 확인 |

### FastAPI 는 뭔가요?

**"이 주소로 요청이 오면 이 함수를 실행해라"** 를 파이썬으로 쉽게 적게 해 주는 웹 서버 도구입니다.

```python
@router.get("/health")          # 누군가 /health 로 접속하면
def health():
    return {"status": "ok"}     # 이 결과를 JSON 으로 돌려준다
```

- **라우팅:** 주소(`/api/chat`)와 함수를 연결
- **입력 검증:** "level 은 easy/beginner/advanced 중 하나" 같은 규칙을 적어 두면 틀린 요청을 자동으로 거절
- **자동 문서:** 서버를 켜고 `/docs` 에 들어가면 모든 API 를 보고 직접 호출해 볼 수 있음

### SQLite 와 MySQL 은 뭐가 다른가요?

둘 다 SQL 로 쓰는 관계형 DB 지만, **동작 방식이 다릅니다.**

| | SQLite | MySQL |
|---|---|---|
| 형태 | **파일 하나** (`easyexplain.db`) | 따로 설치해서 켜 두는 **DB 서버 프로그램** |
| 설치·설정 | 없음 (파이썬에 내장) | 설치, 계정·비밀번호·포트 설정 필요 |
| 접속 | 우리 서버가 파일을 직접 읽고 씀 | 네트워크로 DB 서버에 접속 |
| 동시 쓰기 | 한 번에 하나씩 (작은 서비스엔 충분) | 많은 사용자가 동시에 써도 됨 |
| 어울리는 곳 | 소규모 서비스, 학습, 앱 내장 | 사용자가 많은 서비스, 여러 서버가 같은 DB 사용 |

**우리가 SQLite 를 고른 이유:** 과제 권장이고, 설정이 거의 없어 기능 개발에 집중할 수 있으며,
평가 규모(수십 명)에는 충분합니다. 단, **DB 가 파일이므로 배포 서버에서 파일이 지워지지 않는 저장 공간**에 둬야 합니다.

---

## 5. 실행 방법

EasyExplain **웹 서버를 내 컴퓨터에서 실행**하는 방법입니다. (Python 3.12 는 uv 가 자동으로 준비합니다)

```bash
# 1) 패키지 관리 도구 uv 설치
brew install uv                       # macOS (Windows: https://docs.astral.sh/uv/ 참고)

# 2) 프로젝트 코드를 내려받고, 필요한 파이썬 패키지 설치
git clone https://github.com/easy-explain/Codyssey-B7-1-Term-Project.git
cd Codyssey-B7-1-Term-Project
uv sync

# 3) 서버 설정 파일(.env) 만들기 — 값을 비워 두면 가짜 AI 응답으로 동작
cp .env.example .env

# 4) 서버 실행 → 브라우저에서 http://localhost:8000/health (API 문서: /docs)
uv run uvicorn app.main:app --reload

# (선택) 자동 테스트 실행
uv run pytest
```

### 서버 설정 값 (환경 변수)

API 키 같은 비밀 값은 코드에 쓰지 않고 **`.env` 파일**에 둡니다. `.env` 는 Git 에 올라가지 않습니다.
전체 목록과 기본값은 [.env.example](.env.example) 에 있습니다.

| 이름 | 용도 |
|---|---|
| `APP_ENV` | 실행 환경: development / test / production |
| `DATABASE_URL` | DB 파일 위치 |
| `AI_PROVIDER` | `fake`(키 없이 가짜 응답) 또는 `anthropic`(실제 AI) |
| `ANTHROPIC_BASE_URL` | AI 게이트웨이 주소 |
| `ANTHROPIC_API_KEY` | AI 키 (**비밀**) |
| `AI_MODEL` | 사용할 AI 모델 |
| `AI_TIMEOUT_SECONDS` | AI 응답 최대 대기 시간 (기본 30초) |
| `AI_MAX_OUTPUT_TOKENS` | AI 답변 최대 길이 |
| `CONTEXT_TURNS` · `CONTEXT_MAX_CHARS` | AI 에 함께 보낼 이전 대화 수(기본 5턴)·최대 글자 수 |
| `SITE_ORIGIN` | 서비스 주소. 가입·로그인 요청의 출처(Origin) 검사에 사용 |
| `SESSION_TTL_SECONDS` | 로그인 유지 시간 (기본 2시간) |
| `COOKIE_SECURE` | 로그인 쿠키를 HTTPS 로만 보냄 (운영은 `true` 필수) |
| `USER_REQUESTS_PER_MINUTE` · `DAILY_REQUEST_LIMIT` | 질문 횟수 제한 (1인 1분 · 전체 하루) |
| `LOG_LEVEL` | 서버 로그 수준 |

서버 배포 방법과 서비스 URL 은 배포 후 추가합니다.

---

## 6. 과제 요구사항과 제출 점검

과제 원문(B7-1) 항목마다 **어디서 만족하는지(근거)와 진행 상태**를 적습니다. 기능을 머지할 때 상태와 근거를 함께 갱신합니다.
✅ 완료 · 🟨 일부 완료 · ⬜ 예정 (담당 이슈)

### 기능 요구사항 (원문 4장)

| 원문 요구사항 | 근거 (코드 · 문서 · 테스트) | 상태 |
|---|---|---|
| 4-1 질문 입력 웹 페이지, 같은 화면에서 응답 확인 | `/chat` 화면 (`app/templates/`, `app/static/js/`) | ⬜ [EE-12][i19] · [EE-14][i21] |
| 4-2 회원가입·로그인 | API: [app/auth/router.py](app/auth/router.py), [tests/auth/](tests/auth/) · 화면: `/signup` `/login` | 🟨 API ✅ [#35][p35] [#37][p37] · 화면 [EE-09][i17] |
| 4-2 로그인 여부로 기능 구분, 챗봇은 로그인 사용자만 | `CurrentUserDep` → 비로그인 API 는 401, 상태 변경은 CSRF 없으면 403 ([app/auth/dependencies.py](app/auth/dependencies.py), [tests/core/test_fixtures.py](tests/core/test_fixtures.py)) | 🟨 API ✅ [#37][p37] · 페이지 이동 [EE-12][i19] |
| 4-3 AI 는 서버에서 호출 (키 노출 방지) | 화면은 우리 서버만 부르고, AI 는 [app/chat/provider.py](app/chat/provider.py) 경계로 서버에서만 호출. 키는 환경 변수 `ANTHROPIC_API_KEY` | 🟨 경계·가짜 AI ✅ [#6][p6] · 실제 연결 [EE-13][i20] |
| 4-3 문맥 유지 전략 | 같은 대화의 최근 5턴, 최대 12,000자 ([app/chat/context.py](app/chat/context.py), [tests/chat/test_context.py](tests/chat/test_context.py)) | 🟨 ✅ [#8][p8] · 채팅 연결 [EE-13][i20] |
| 4-4 질문·응답 누적 저장 (사용자·시각·질문·응답) | `chat_turns` 의 `user_id` `created_at` `question` `answer` ([docs/spec/db.md](docs/spec/db.md)) | 🟨 테이블 ✅ [#33][p33] · 저장 [EE-13][i20] |
| 4-4 사용자 기준 조회·추적 | 내 기록 API `GET /api/me/chats` · 확인용 SQL `scripts/check_logs.sql` | ⬜ [EE-11][i18] · [EE-20][i27] |
| 4-5 서버 로그: 요청 수신 / AI 호출 / AI 응답·실패 / DB 저장 성공·실패 | `request_received` · `ai_call_start` · `ai_call_success`·`ai_call_failed` · `db_save_success`·`db_save_failed`, 모두 같은 `request_id` ([app/core/logging.py](app/core/logging.py), [app/core/middleware.py](app/core/middleware.py)) | 🟨 요청 로그 ✅ [#4][p4] · AI·DB 로그 [EE-13][i20] |
| 4-5 AI 실패·타임아웃에도 서버 유지, 사용자에게 안내 | 모든 예외를 공통 JSON 오류로 변환 ([app/core/errors.py](app/core/errors.py)) · AI 오류는 504 `AI_TIMEOUT` 등 한국어 안내 | 🟨 공통 오류 ✅ [#4][p4] · AI 오류 [EE-16][i23] |
| 4-5 입력 검증 1개 이상 | 가입·로그인 이메일 형식·비밀번호 길이 → 422 ([tests/auth/](tests/auth/)) · 질문 1~2,000자 | ✅ [#35][p35] [#37][p37] · 질문 [EE-13][i20] |
| 4-6 외부 접속 URL, 배포·환경 변수 문서 | Railway + Volume ([배포 방식 결정](docs/team/3-deploy-options.md)) · 실행 방법·환경 변수 5장 | 🟨 결정 ✅ [#34][p34] · 배포 [EE-22][i29] |
| 4-7 브랜치 전략, 기능 단위 작업 브랜치 | `main` 보호 + 이슈별 `feat/ee-XX-…` 브랜치 ([CONTRIBUTING.md](CONTRIBUTING.md)) | ✅ |
| 4-7 PR 기반 Merge | main 직접 커밋 금지. 승인 1명 + CI `test` 통과 후 Merge commit ([.github/workflows/ci.yml](.github/workflows/ci.yml)) | ✅ |
| 4-7 1인 유의미한 커밋 10회 | `git shortlog -sne --no-merges origin/main` (아래 평가 전 확인) | ⬜ [EE-24][i31] |
| 4-7 역할·개인별 작업 요약 (Git 이력과 일치) | 3장 역할·기능 표(담당·PR 칸) | 🟨 역할 ✅ · 개인별 요약 [EE-24][i31] |

### 제출물 · 개발 환경 · 제약 사항 (원문 2·5·6장)

| 원문 요구사항 | 근거 | 상태 |
|---|---|---|
| GitHub 저장소 링크 | 공개 저장소, 주소는 5장 | ✅ |
| 외부 접속 서비스 URL | 4-6 참고 | ⬜ [EE-22][i29] |
| 문서: 프로젝트 개요 (문제 정의·대상 사용자·핵심 시나리오) | 1·3장 | ✅ |
| 문서: 시스템 구조 (아키텍처·컴포넌트 역할) | 1·2장 | 🟨 구조도 보강 [EE-24][i31] |
| 문서: API 명세 (요청·응답 예시) | [docs/spec/api.md](docs/spec/api.md) | ✅ 구현하며 갱신 |
| 문서: DB 구조 (테이블·필드) | [docs/spec/db.md](docs/spec/db.md) | ✅ 구현하며 갱신 |
| 문서: 배포·실행 방법, 환경 변수 이름·설정 방법 | 5장 (환경 변수 전체 목록) | 🟨 실행·환경 변수 ✅ · 배포 [EE-22][i29] |
| 문서: 민감정보 관리 / 민감정보는 환경 변수로, `.env` 는 Git 제외 | [.env.example](.env.example), [.gitignore](.gitignore), 설정은 [app/core/config.py](app/core/config.py) 에서만 읽음 | ✅ |
| DB 확인 가이드 (3가지 중 1개 이상) | 로그 조회 API(`GET /api/me/chats`) + 확인용 SQL(`scripts/check_logs.sql`). 관리자 화면은 비제공 (3장) | ⬜ [EE-11][i18] · [EE-20][i27] |
| Python & FastAPI, SQLite | 4장 기술 스택 | ✅ |
| 평가자가 DB 에 연결·조회 가능 | 배포 서버의 DB 에 확인용 SQL 실행 (`railway ssh`) | ⬜ [EE-20][i27] |
| AI 호출 타임아웃 설정, 실패 시 안내 | `AI_TIMEOUT_SECONDS` 기본 30초 ([app/core/config.py](app/core/config.py)) | 🟨 설정 ✅ · 적용 [EE-13][i20] · 안내 [EE-16][i23] |
| 과제 목표: 각자 맡은 부분을 설명 | [평가 대비](docs/team/2-evaluation-example.md) | ⬜ [EE-24][i31] |

### 평가 전 확인

표의 근거를 **실제로 돌려 보는** 마지막 점검입니다.
- [ ] 휴대폰 데이터(외부 네트워크)로 서비스 URL 접속 → 가입·로그인·질문·내 기록
- [ ] 서버 재시작 후에도 대화 기록 유지
- [ ] 1인당 의미 있는 커밋 10개 이상: `git shortlog -sne --no-merges origin/main`
- [ ] 모든 기능이 PR 로 머지됨 (3장 기능 표의 PR 칸)
- [ ] 각자 맡은 코드 설명 리허설 → [평가 대비](docs/team/2-evaluation-example.md)

[i17]: https://github.com/easy-explain/Codyssey-B7-1-Term-Project/issues/17
[i18]: https://github.com/easy-explain/Codyssey-B7-1-Term-Project/issues/18
[i19]: https://github.com/easy-explain/Codyssey-B7-1-Term-Project/issues/19
[i20]: https://github.com/easy-explain/Codyssey-B7-1-Term-Project/issues/20
[i21]: https://github.com/easy-explain/Codyssey-B7-1-Term-Project/issues/21
[i23]: https://github.com/easy-explain/Codyssey-B7-1-Term-Project/issues/23
[i27]: https://github.com/easy-explain/Codyssey-B7-1-Term-Project/issues/27
[i29]: https://github.com/easy-explain/Codyssey-B7-1-Term-Project/issues/29
[i31]: https://github.com/easy-explain/Codyssey-B7-1-Term-Project/issues/31
[p4]: https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/4
[p6]: https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/6
[p8]: https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/8
[p33]: https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/33
[p34]: https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/34
[p35]: https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/35
[p37]: https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/37

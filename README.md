# EasyExplain

> 모르는 개념을 물어보면 **설명 수준(아주 쉽게 / 입문자 / 전공자)** 에 맞춰 풀어 주고,
> "더 쉽게", "예시 하나 더" 같은 후속 질문으로 이해를 넓혀 가는 AI 챗봇입니다.

Codyssey **B7-1 Term Project「웹 기반 AI 챗봇 서비스 개발 프로젝트」** · 4인 팀

> **현재 상태:** 앱 뼈대(서버 실행, `/health`, 공통 오류·로그)까지 준비. 실제 기능은 아직 `501` 을 반환합니다.

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
| **계정** | 회원가입 | 이메일·비밀번호, 비밀번호는 해시로 저장 | A 가입 API·DB<br>C 가입 화면 | `POST /api/auth/signup`<br>`/signup` | ⬜ | |
| | 로그인·로그아웃 | 세션 쿠키 발급·삭제 | A 세션 처리<br>C 로그인 화면 | `POST /api/auth/login`<br>`POST /api/auth/logout`<br>`/login` | ⬜ | |
| | 접근 제어 | 비로그인은 API 401, 페이지는 로그인으로 이동 | A | `GET /api/auth/me` | ⬜ | |
| **채팅** | 질문·답변 | 같은 화면에 답 표시, 대기 중 버튼 잠금 | B 채팅 API·AI 호출<br>C 채팅 화면 | `POST /api/chat`<br>`/chat` | 🟨 | [#43](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/43) |
| | 설명 수준 | 아주 쉽게 / 입문자 / 전공자 | B 수준별 프롬프트<br>C 수준 선택 UI | `POST /api/chat` 의 `level` | 🟨 | [#8](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/8) · [#43](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/43) |
| | 문맥 유지 | 같은 대화의 최근 5턴을 기억 | B | (서버 내부) | 🟨 | [#8](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/8) · [#43](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/43) |
| | 설명 품질 증빙 | 실제 AI 수준별·후속 문맥 샘플과 수동 검토 | B | 수동 수집 | 🟨 | [#46](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/46) |
| | 후속 버튼 | 더 쉽게 / 예시 하나 더 / 핵심만 | C | `/chat` | ⬜ | |
| **대화 기록** | 대화 만들기 | 새 대화 시작 | A | `POST /api/conversations` | ⬜ | |
| | 내 기록 조회 | 내 대화 목록·상세, 남의 대화는 볼 수 없음 | A 조회 API·권한<br>C 기록 화면 | `GET /api/me/conversations`<br>`GET /api/me/chats`<br>`/history` | ⬜ | |
| | DB 확인 도구 | 사용자별 최근 대화 조회 SQL | A | `scripts/check_logs.sql` | ⬜ | |
| **안정성** | 오류 안내 | AI 지연·실패·DB 오류에도 서버 유지, 공통 형식으로 안내 | L 공통 오류 형식<br>B AI 오류 처리<br>C 오류 메시지 표시 | 모든 API | 🟨 | [#4](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/4) · [#43](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/43) |
| | 질문 횟수 제한 | 사용자별 최근 60초·서비스 전체 UTC 하루 한도, 단일 worker·인스턴스 기준 | B | `POST /api/chat` | 🟨 | [#44](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/44) |
| | 입력 검증 | 빈 질문, 2,000자 초과, 잘못된 값 차단 | B 서버 검증<br>C 화면 입력 제한 | `POST /api/chat` | 🟨 | [#4](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/4) · [#43](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/43) |
| | 서버 로그 | 요청·AI 호출·DB 저장을 요청 ID 로 묶어 기록 | L 요청 로그<br>B AI 호출 로그<br>A DB 저장 로그 | 서버 로그 | 🟨 | [#4](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/4) · [#43](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/43) |
| | 상태 확인 | 서버·DB 정상 여부 | L | `GET /health` | ✅ | [#4](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/4) |
| **배포·협업** | 외부 배포 | 공개 URL, 재시작해도 기록 유지 | L | 서비스 URL | 🟨 | [EE-22](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/issues/29) |
| | 자동 검사 (CI) | PR 마다 코드 검사·테스트 자동 실행 | L | GitHub Actions | 🟨 | [#4](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/4) |

⬜ 미착수 · 🟨 일부 완료 · ✅ 완료 — 기능을 머지할 때 상태와 PR 번호를 함께 적습니다.

EE-13 서버 구현과 Fake 기반 검증은 [#43](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/43)에서 진행했습니다.
횟수 제한과 오류·중복 요청 검증은 [#44](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/44)에서 진행했습니다.
EE-13·EE-16 서버 구현은 병합됐습니다. 수준별·후속 문맥의 실제 AI 샘플 15개와
프롬프트 보완 전후 검토 결과는 [EE-19 안내](app/chat/EE-19.md)에 모았습니다.
해요체·일반 텍스트 출력 보완과 이전 지도 예시·비유의 한계도 함께 기록했습니다. EE-19는 PR 리뷰·병합 전이므로 🟨입니다.
처리 순서와 설명 자료는 [EE-13 안내](app/chat/EE-13.md)를 참고합니다.
한도 집계 대상과 단일 worker·재시작 초기화 제한은 [EE-16 안내](app/chat/EE-16.md)에 설명했습니다.

### 비제공 기능

과제의 핵심인 **로그인 → AI 질문 → 기록 저장 → 배포**를 안정적으로 완성하는 데 집중하기 위해,
아래 기능은 제공하지 않습니다. 필수 기능이 끝나도 기능을 늘리기보다 안정화를 우선합니다.

- PDF·파일 업로드
- 웹 검색 (최신 정보 반영)
- 음성·이미지 입력
- 소셜 로그인 (카카오, 구글 등)
- 결제
- 실시간 스트리밍 응답 (답변이 한 글자씩 나오는 방식)
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

### 배포

- **서비스 URL:** https://codyssey-b7-1-term-project-production.up.railway.app
- **배포된 커밋:** `24bf396` (2026-10-09, #48 머지 후 자동 배포)
- Railway + Volume 에 배포합니다. 설정 절차·업데이트 방법·주의점은 [배포 문서 8장](docs/team/3-deploy-options.md#8-railway-설정-절차)을 봅니다.

### 사용 가이드 (처음 쓰는 사람)

위 서비스 URL(또는 내 컴퓨터의 `http://localhost:8000`)에 들어가 아래 순서로 씁니다. 마우스 없이 키보드만으로도, 휴대폰에서도 같은 순서입니다.
캡처는 로컬 서버에서 가짜 계정(`guide@example.com`)으로 찍었고, 답변 글은 팀이 기록해 둔 실제 AI 답변 샘플([EE-19](app/chat/EE-19.md))을 다시 보여 준 것입니다.

1. **가입** — 첫 화면의 [시작하기] → 이메일과 비밀번호(8~64자, 영문·숫자·기호) → [가입하기]. 이미 가입한 이메일이거나 규칙에 맞지 않으면 안내 칸에 이유가 나오고, 입력한 내용은 지워지지 않으니 고쳐서 다시 누르면 됩니다.
2. **로그인** — 가입하면 로그인 화면으로 넘어가 "가입이 끝났어요" 안내가 보입니다. 같은 이메일·비밀번호로 [로그인]하면 채팅 화면이 열립니다.
3. **수준 고르기·질문** — 위의 [아주 쉽게]·[입문자]·[전공자] 중 하나를 고르고, 아래 칸에 궁금한 개념을 써서 Enter(줄바꿈은 Shift+Enter) 또는 [보내기]. 답을 만드는 동안은 "답변을 만드는 중"이 보이고 버튼이 잠깁니다.
4. **후속 버튼** — 답 아래의 [더 쉽게]·[예시 하나 더]·[핵심만]을 누르면 같은 대화에 이어서 묻습니다. 앞의 설명을 기억한 채 답합니다.
5. **내 기록** — 위쪽 메뉴의 [내 기록]. 최근에 질문한 대화가 위에 있고, 대화를 누르면 질문·답변이 시간 순서(한국 시간)로 보입니다.
6. **이어서 질문** — 기록 화면의 [이어서 질문]을 누르면 그 대화로 채팅이 열려, 앞의 내용을 기억한 채 계속 물을 수 있습니다.
7. **로그아웃** — 위쪽 메뉴의 [로그아웃].

| 가입 | 질문과 답변, 후속 버튼 |
|:---:|:---:|
| <img src="tests/web/screenshots/signup-desktop.webp" width="400" alt="가입 화면: 이메일·비밀번호 칸과 가입하기 버튼"> | <img src="tests/web/screenshots/chat-desktop.webp" width="400" alt="채팅 화면: 아주 쉽게를 고르고 보낸 질문과 답변, 아래에 더 쉽게·예시 하나 더·핵심만 버튼"> |
| **내 기록** | **대화 상세와 이어서 질문** |
| <img src="tests/web/screenshots/history-desktop.webp" width="400" alt="내 기록 화면: 최근에 질문한 대화 목록"> | <img src="tests/web/screenshots/detail-desktop.webp" width="400" alt="대화 상세: 질문·답변과 수준·한국 시간, 목록으로·이어서 질문 버튼"> |

**오류가 났을 때**
- 답이 늦거나 AI 오류가 나면 안내 칸에 이유와 [다시 보내기]가 나옵니다. 질문 글은 지워지지 않고, 누르면 같은 질문을 다시 보냅니다.
- 질문을 너무 자주 보내면(질문 한도) 10초(연달아 걸리면 최대 60초) 동안 보내기가 잠기고 남은 시간이 보입니다. 시간이 지나면 "이제 다시 보낼 수 있어요"가 나옵니다. 계속 나오면 오늘 서비스 전체 한도를 다 쓴 것이고, 매일 오전 9시에 다시 채워집니다.
- 로그인이 풀리면(시간이 지났거나 다른 탭에서 로그아웃) 로그인 화면으로 넘어가 "로그인이 풀렸어요" 안내가 나옵니다. 다시 로그인하면 됩니다.
- 인터넷이 끊기면 "서버에 연결하지 못했어요" 안내가 나옵니다. 연결을 확인하고 같은 버튼을 다시 누르면 됩니다.

| 오류 안내와 다시 보내기 | 휴대폰(375px) |
|:---:|:---:|
| <img src="tests/web/screenshots/chat-error-desktop.webp" width="400" alt="채팅 오류: AI 응답을 받지 못했다는 안내와 다시 보내기 버튼, 질문 칸에 남은 질문"> | <img src="tests/web/screenshots/chat-mobile.webp" width="200" alt="휴대폰 폭의 채팅 화면: 답변, 후속 버튼, 질문 칸"> |

**키보드로 쓰기** — 페이지마다 처음 Tab 을 누르면 왼쪽 위에 [본문으로 건너뛰기]가 나타나고, Enter 를 누르면 위쪽 메뉴를 건너뛰어 본문으로 갑니다. 그다음은 Tab·Shift+Tab 으로 옮겨 다니고 Enter·Space 로 누르며, 수준은 ←→ 화살표로 고릅니다. 지금 있는 곳은 보라색 테두리로 보입니다.

**휴대폰에서 쓰기** — 같은 주소로 들어가면 화면 폭(320px까지)에 맞춰지고, 버튼은 손가락으로 누르기 쉬운 크기(44px 이상)입니다. 브라우저 확대(200%·400%)나 큰 글자 설정(2배)에서도 가로로 넘치거나 잘리지 않습니다.

화면마다 무엇을 어떻게 확인했는지(키보드 접근, 375px 가로 넘침, 오류 안내 후 버튼 잠금 해제, 글자 대비 표, 데스크톱·휴대폰 캡처)는 [화면 검증 기록](tests/web/README.md)에 있습니다.

---

## 6. 제출 체크리스트

**제출물**
- [ ] GitHub 저장소 링크
- [ ] 외부 네트워크에서 접속되는 서비스 URL
- [x] DB 확인 방법 (7장, `scripts/check_logs.sql`)

**README / 기술 문서에 들어갈 것**
- [x] 프로젝트 개요 — 문제 정의, 대상 사용자, 핵심 시나리오 (1·3장)
- [ ] 시스템 구조 — 아키텍처, 주요 컴포넌트 역할 (1·2장, 구조도 보강 예정)
- [x] API 명세 — 요청·응답 예시 ([docs/spec/api.md](docs/spec/api.md), 구현하며 갱신)
- [x] DB 구조 — 테이블·필드 설명 ([docs/spec/db.md](docs/spec/db.md), 구현하며 갱신)
- [ ] 배포·실행 방법, 환경 변수 설정 (5장, 배포 방법 추가 예정)
- [ ] 팀 역할과 개인별 작업 (3장 — 역할 배정, 기능 표의 담당·PR 칸)
- [x] 민감정보 관리 — `.env.example` 제공, `.gitignore` 적용

**평가 전 확인**
- [ ] 1인당 의미 있는 커밋 10개 이상: `git shortlog -sne --no-merges origin/main`
- [ ] 모든 기능이 PR 로 머지됨 (3장 기능 표의 PR 칸)
- [ ] 각자 맡은 코드를 설명할 수 있음 → [docs/team/2-evaluation-example.md](docs/team/2-evaluation-example.md)
- [ ] 서버 재시작 후에도 대화 기록 유지

## 7. DB 확인·백업·복구

### 평가자가 배포된 DB 확인

평가자는 `/history` 또는 로그인 후 `GET /api/me/conversations`, `GET /api/me/chats`에서 본인 기록을 확인할 수 있습니다.
DB 원문을 직접 확인할 때는 담당자가 `railway ssh`로 접속한 뒤 컨테이너의 Python에서 아래 코드를 실행합니다.

```python
import sqlite3
from pathlib import Path

db = sqlite3.connect("/app/data/easyexplain.db")
sql = Path("/app/scripts/check_logs.sql").read_text(encoding="utf-8")
rows = db.execute(sql, {"email": "평가용 계정 이메일"}).fetchall()
print(*rows, sep="\n")
db.close()
```

이 방법은 `sqlite3` 명령이 없는 컨테이너에서도 동작합니다. 질문·답변 원문이 출력되므로 필요한 경우에만 실행합니다.

### Railway Volume 백업과 복구

평가 전 Railway 대시보드의 **서비스 → Volume → Backups**에서 수동 백업을 만들고 완료 여부를 확인합니다.
복구할 때는 백업을 선택해 **Restore → Deploy**하고, `/health`와 기록 조회로 복구 상태를 확인합니다.
복구 전에는 현재 DB도 백업합니다. 별도 파일 보관이 필요하면 SQLite `Connection.backup()`으로 복사본을 만든 뒤
`railway ssh`/`scp`로 내려받습니다.

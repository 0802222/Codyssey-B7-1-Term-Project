# 배포 방식 정하기 — 같이 결정할 안건

> ✅ **결정: Railway (Hobby + Volume)** — [PR #34](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/pull/34) 에서 4명 모두 동의했어요. 결정 내용은 [7. 결정 사항](#7-결정-사항) 에 있어요.
> 관련 작업: [EE-22 외부 배포·영속 DB·재시작 검증 (#29)](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/issues/29)

---

## 1. 왜 지금 정하나요?

배포는 M4 단계(EE-22) 작업이지만, **배포할 곳은 미리 정해 두려고** 해요.

- 과제 필수 요구사항: 평가 날 **외부에서 접속되는 URL**, 그리고 **서버를 재시작해도 대화 기록이 남아야** 해요.
- 마지막에 처음 배포하면 "내 컴퓨터에선 됐는데 서버에선 안 돼요" 같은 문제를 너무 늦게 발견해요.
- 그래서 EE-22 보다 앞서, **로그인·대화 저장·실제 AI 가 머지되면 바로 첫 배포**를 해 볼 거예요. ([6. 일정](#6-일정-선행-작업-기준))

## 2. 배포할 곳의 조건

| 조건 | 왜 필요한가요? |
|---|---|
| **영속 디스크** | 우리 DB(SQLite)는 **파일 하나**예요. 재시작할 때 파일이 지워지는 곳이면 기록이 다 사라져요 |
| **HTTPS** | 로그인 쿠키를 안전하게 보내려고 운영 설정에서 `COOKIE_SECURE=true` 가 필수예요. HTTPS 가 아니면 로그인이 안 돼요 |
| **외부 URL** | 평가자가 휴대폰 데이터로도 접속할 수 있어야 해요 |
| **비용·작업량** | 과제 기간 동안 부담 없는 비용, 그리고 기능 개발 시간을 뺏기지 않을 것 |

## 3. 두 가지 방식

식당에 비유하면 이래요.

| | 🏚️ 빈 건물 임대 (IaaS) | 🍜 푸드코트 입점 (PaaS) |
|---|---|---|
| 비유 | 건물만 빌려서 주방 설비·전기·간판·청소를 **직접** 준비 | 자리와 설비는 푸드코트가 준비, 우리는 **요리(코드)만** 가져감 |
| 예 | AWS EC2, Oracle Cloud | Railway, Render, Fly.io |
| 우리가 할 일 | 리눅스 설치·설정, 앱 실행 유지, 방화벽, HTTPS 인증서, 보안 업데이트 | 코드 연결, 환경 변수 입력 |

## 4. 후보 비교

(2026-10-06 기준 각 서비스 공식 문서 확인. 요금·무료 조건은 바뀔 수 있어요)

| | **Railway** | Render | Fly.io | AWS EC2 | Oracle Cloud |
|---|---|---|---|---|---|
| 방식 | PaaS | PaaS | PaaS | IaaS | IaaS |
| 영속 디스크 | ✅ Volume | ⚠️ **유료만** (무료는 재시작하면 DB 사라짐) | ✅ Volume | ✅ | ✅ |
| HTTPS | ✅ 자동 | ✅ 자동 | ✅ 자동 | ❌ 직접 (도메인 필요) | ❌ 직접 (도메인 필요) |
| 자동 배포 (CD) | ✅ main 머지하면 자동 | ✅ 자동 | 직접 구성 | 직접 구성 | 직접 구성 |
| 무료 | 체험 $5 (30일, 카드 없이) | 있음, 15분 쉬면 꺼짐 + 디스크 없음 | 체험 7일 | 크레딧 최대 $200 (6개월) | 무료 VM (가입 시 카드) |
| 유료 | **$5/월** (사용료 $5 포함) | $7/월 + 디스크 | 약 $2~3/월 + 디스크, 카드 필수 | 크레딧 소진 후 사용량만큼 | — |
| 가까운 지역 | 싱가포르 | 싱가포르 | 도쿄·싱가포르 | 서울 | 서울 |
| 첫 배포까지 | 30분~1시간 | 30분~1시간 | 반나절 | 하루 | 하루 이상 |
| 팀장 작업량 | 적음 | 적음 | 중간 | 많음 | 많음 |

- **Render** 는 무료로 하면 조건(영속 디스크)을 못 채우고, 유료로 하면 Railway 보다 비싸요.
- **EC2·Oracle** 은 비용은 거의 0 이지만, HTTPS 를 위해 도메인을 사고 인증서를 직접 설정해야 해요. 서버 관리를 놓치면 평가 당일 장애가 날 수도 있어요.

## 5. 제안: Railway

**좋은 점**
- 조건 4가지(영속 디스크·HTTPS·외부 URL·자동 배포)가 **설정 몇 번으로** 다 돼요
- main 에 머지할 때마다 자동으로 배포돼서, 배포된 서비스가 항상 최신이에요
- 서버 관리에 시간을 쓰지 않고 기능 개발에 집중할 수 있어요

**아쉬운 점**
- 서울이 아니라 싱가포르 서버라 조금 느릴 수 있어요 (채팅은 AI 응답 시간이 훨씬 길어서 체감은 작을 거예요)
- 유료예요: Hobby 는 월 $5 기본요금에 사용료 $5 가 포함되고, **넘게 쓰면 추가 청구**돼요.
  과제 규모에서는 거의 넘지 않을 것으로 보고, 1~2개월이면 **총 $5~10 (예상치)**
- 평가 때 "서버를 직접 다뤘다"고 말할 거리는 EC2 보다 적어요.
  대신 "왜 이 방식을 골랐는지"(이 문서의 비교)를 설명할 수 있어요

**나중에 바꾸기도 쉬워요.** 앱은 `DATABASE_URL` 같은 환경 변수만 맞추면 어디서든 뜨게 만들어 뒀어요. Railway 로 시작했다가 EC2 로 옮겨도 코드는 그대로이고 DB 파일만 옮기면 돼요.

## 6. 일정 (선행 작업 기준)

**지금 바로는 띄우지 않아요.** 지금 main 은 로그인·채팅 API 가 아직 `501 NOT_IMPLEMENTED` 라서,
띄워도 `/health` 말고는 확인할 게 없고 요금만 나가요. 그래서 날짜가 아니라 **선행 이슈가 닫히는 시점**에 맞춰 진행해요.

| 단계 | 언제 (선행 조건) | 할 일 | 누가 |
|---|---|---|---|
| 0 | 지금 | 배포 방식 결정, 이 문서 머지 | 팀장 |
| 1. 첫 배포 | [EE-08 로그인 (#16)](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/issues/16) · [EE-11 대화 저장 (#18)](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/issues/18) · [EE-13 실제 AI (#20)](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/issues/20) 머지 후 | Hobby 가입, [8. 설정 절차](#8-railway-설정-절차) 대로 배포 → HTTPS 로그인·대화 저장·Redeploy 후 기록 유지 확인 | 팀장 |
| 2. 자동 배포 | 1단계 직후 | main 머지 → 자동 배포 (Wait for CI). 각자 기능을 실제 서버에서 확인 | 전원 |
| 3. 본 배포 검증 | [EE-18 통합 검증 (#25)](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/issues/25) 닫힌 뒤 = [EE-22 (#29)](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/issues/29) | 휴대폰 데이터 접속, 재시작 검증 기록, README 에 URL·배포 방법 | 팀장 |
| 4. AI 검증 | EE-22 후 = [EE-23 (#30)](https://github.com/easy-explain/Codyssey-B7-1-Term-Project/issues/30) | 배포 환경에서 실제 AI·시간 초과 검증 기록 | B |
| 5. 백업 | EE-20 (#27) 진행 시, 평가 전날 | Volume 백업, DB 확인·복구 방법 확인 | A · 팀장 |
| 6. 정리 | 평가 다음 날 | DB 백업 후 프로젝트 삭제 (과금 중지), 비용 1/n 정산 | 팀장 |

- 1단계 전까지 Railway 결제는 하지 않아요. 결제일부터 월 요금이 나가기 때문이에요.
- 평가 직전에는 머지를 멈춰요. Volume 이 붙은 서비스는 재배포할 때 잠깐 끊겨요.

## 7. 결정 사항

| 안건 | 결정 |
|---|---|
| 배포 방식 | **Railway (Hobby + Volume)**. EC2 는 예비안 |
| 비용 | 4명이 1/n. 월 $5 + 초과분이 있으면 그것도 1/n |
| 운영 설정 | 처음부터 `APP_ENV=production`, 코디세이 AI 키는 Railway Variables 에만 |
| 자동 배포 | main 머지 → 자동 배포, **Wait for CI** 켜서 `test` 통과한 뒤에만 |
| 인스턴스 | 1개 (SQLite + Volume 은 한 인스턴스에만 붙어요) |
| 평가 후 | 다음 날 해지, DB 는 백업 후 삭제 |

## 8. Railway 설정 절차

1단계(첫 배포) 때 팀장이 이 순서대로 해요. 화면 이름은 Railway 가 바꿀 수 있어요.

1. **프로젝트 만들기**: GitHub 로 로그인 → New Project → Deploy from GitHub repo → 이 저장소 선택
   (조직 저장소라 GitHub App 권한 승인이 필요할 수 있어요)
2. **지역**: Service → Settings → Region 을 Southeast Asia (Singapore) 로
3. **Volume**: 서비스 우클릭 → Attach Volume → Mount path `/app/data`
   (Railpack 은 코드를 `/app` 에 둬요. Volume 은 실행 중에만 붙어서, DB 는 빌드가 아니라 앱 시작 때 만들어요 — `app/main.py` 의 `lifespan`)
4. **Variables** (Raw Editor 에 붙여 넣기, 키는 직접 입력)

   ```
   RAILPACK_PYTHON_VERSION=3.12
   APP_ENV=production
   DATABASE_URL=sqlite:////app/data/easyexplain.db
   SITE_ORIGIN=https://${{RAILWAY_PUBLIC_DOMAIN}}
   AI_PROVIDER=anthropic
   ANTHROPIC_API_KEY=(코디세이 키)
   COOKIE_SECURE=true
   ```

   - `RAILPACK_PYTHON_VERSION`: Railpack 은 `requires-python` 을 읽지 않고 기본 3.13 을 써요. 우리는 3.12 만 허용해요
   - `sqlite:////` 슬래시 **4개** = 절대 경로. 3개면 Volume 밖에 저장돼서 재배포 때 사라져요
   - production 인데 `AI_PROVIDER=fake` 거나 `COOKIE_SECURE=false` 면 앱이 일부러 안 떠요 (`app/core/config.py`)
   - 나머지 값(`AI_MODEL` 등)은 `.env.example` 기본값을 그대로 써요
5. **실행 설정** (Service → Settings)
   - Custom Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips="*"`
     (Railpack 은 `main:app` 만 자동으로 찾아서, 우리 `app.main:app` 은 직접 적어요)
   - Healthcheck Path: `/health`
   - Replicas: 1
   - Wait for CI: 켜기
6. **도메인**: Settings → Networking → Generate Domain → `https://xxx.up.railway.app` (HTTPS 자동)
7. **확인**
   - [ ] `/health` 가 `{"status":"ok","db":"ok"}`
   - [ ] 휴대폰 데이터로 회원가입 → 로그인 유지 → 질문 → 답변
   - [ ] Redeploy 후에도 계정·대화가 남아 있음 (Volume 확인)
   - [ ] Deploy Logs 에 키·질문 원문이 없음

---

### 참고한 자료

- [Railway 요금](https://railway.com/pricing) · [Railway 요금제 문서](https://docs.railway.com/pricing/plans) · [Railway 지역](https://docs.railway.com/platform/railway-metal) · [Railway Volume](https://docs.railway.com/volumes/reference)
- Railway 설정: [FastAPI 배포 가이드](https://docs.railway.com/guides/fastapi) · [Railpack Python](https://railpack.com/languages/python) · [Variables](https://docs.railway.com/variables) · [Public Networking](https://docs.railway.com/networking/public-networking) · [Healthchecks](https://docs.railway.com/deployments/healthchecks) · [GitHub 자동 배포](https://docs.railway.com/deployments/github-autodeploys) · [Volume 백업](https://docs.railway.com/volumes/backups) · [CLI](https://docs.railway.com/cli)
- [Render 무료 플랜](https://render.com/docs/free) · [Render 영속 디스크](https://render.com/docs/disks) · [Render vs Railway 2026](https://encore.dev/articles/render-vs-railway)
- [Fly.io 요금](https://docs.fly.io/about/pricing)
- [AWS 프리 티어 2026 변경점](https://infratally.com/articles/aws-free-tier-2026/) · [AWS 프리 티어 크레딧](https://cloudwebschool.com/docs/aws/fundamentals/aws-free-tier/)
- [Oracle Cloud 무료 티어 2026 변경점](https://terminalbytes.com/oracle-cloud-free-tier-changes-2026/)

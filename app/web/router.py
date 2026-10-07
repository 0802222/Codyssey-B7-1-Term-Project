"""웹 페이지 라우트. (C 담당, EE-04·EE-09·EE-12·EE-17)

템플릿은 app/templates/, CSS·JS 는 app/static/ 에 둔다. (/static/... 으로 제공)
/chat, /history 는 비로그인이면 /login 으로 303 이동한다.
(로그인 확인은 app.auth.dependencies.OptionalUserDep 사용)
"""

from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.core.errors import not_implemented

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)

router = APIRouter(tags=["web"], include_in_schema=False)


@dataclass(frozen=True)
class AuthInputRules:
    """가입·로그인 화면의 입력 규칙.

    템플릿이 이 값으로 안내 문구와 입력칸 속성(maxlength·pattern·minlength·data-ascii-only)을
    만들고, auth.js 는 그 속성을 읽어 보내기 전에 검사한다. 최종 검사는 서버(app/auth/router.py)가
    하므로 API 명세(docs/spec/api.md 2장)·서버와 같은 값이어야 한다.
    """

    email_max_length: int
    password_min_length: int
    password_max_length: int
    password_ascii_only: bool  # True 면 비밀번호에 영어(영문·숫자·기호·공백, ASCII 32~126)만 받는다
    # 이메일 형식. 서버(app/auth/router.py 의 _validate_email)와 같은 정규식이어야 한다
    email_pattern: str = r"[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+"


# 값을 바꿀 때는 여기만 고친다
AUTH_INPUT_RULES = AuthInputRules(
    email_max_length=100,
    password_min_length=8,
    password_max_length=64,
    password_ascii_only=True,
)


@router.get("/")
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@router.get("/signup")
def signup_page(request: Request):
    # 헤더 메뉴에 "가입" 항목이 없으므로 현재 위치(active)를 넘기지 않는다
    return templates.TemplateResponse(request, "signup.html", {"rules": AUTH_INPUT_RULES})


@router.get("/login")
def login_page(request: Request):
    # 가입하고 넘어오면(/login?joined=1) "가입이 끝났어요" 안내를 함께 보여 준다
    joined = request.query_params.get("joined") == "1"
    return templates.TemplateResponse(
        request, "login.html", {"active": "login", "joined": joined, "rules": AUTH_INPUT_RULES}
    )


@router.get("/chat")
def chat_page():
    raise not_implemented("EE-12")


@router.get("/history")
def history_page():
    raise not_implemented("EE-17")

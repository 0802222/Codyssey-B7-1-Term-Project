"""웹 페이지 라우트. (C 담당, EE-04·EE-09·EE-12·EE-17)

템플릿은 app/templates/, CSS·JS 는 app/static/ 에 둔다. (/static/... 으로 제공)
/chat, /history 는 비로그인이면 /login 으로 303 이동한다.
(로그인 확인은 app.auth.dependencies.OptionalUserDep 사용)
"""

from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth.dependencies import OptionalUserDep
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


@dataclass(frozen=True)
class LevelOption:
    """채팅 화면의 설명 수준 하나."""

    value: str  # API 로 보내는 값 (docs/spec/api.md 3장의 level)
    label: str  # 화면에 보이는 이름


@dataclass(frozen=True)
class ChatInputRules:
    """채팅 화면의 입력 규칙과 고를 수 있는 수준.

    템플릿이 이 값으로 질문 칸의 maxlength·글자 수 안내와 수준 선택을 만들고, chat.js 는 그 HTML 을
    읽어 보낸다. 최종 검사는 서버(POST /api/chat)가 하므로 API 명세 3장과 같은 값이어야 한다 —
    질문은 앞뒤 공백을 뺀 뒤 1~2,000자(빈 질문은 화면이 막는다),
    level 은 easy / beginner / advanced.
    """

    question_max_length: int
    levels: tuple[LevelOption, ...]
    default_level: str  # 화면을 열었을 때 골라 둔 수준


# 값을 바꿀 때는 여기만 고친다
CHAT_INPUT_RULES = ChatInputRules(
    question_max_length=2000,
    levels=(
        LevelOption("easy", "아주 쉽게"),
        LevelOption("beginner", "입문자"),
        LevelOption("advanced", "전공자"),
    ),
    default_level="easy",
)


# 모든 페이지는 user: OptionalUserDep 로 로그인 여부를 받아 logged_in 으로 넘긴다.
# base.html 헤더가 그 값으로 "로그인" 메뉴 또는 "로그아웃" 버튼을 보여 준다


@router.get("/")
def index(request: Request, user: OptionalUserDep):
    return templates.TemplateResponse(request, "index.html", {"logged_in": user is not None})


@router.get("/signup")
def signup_page(request: Request, user: OptionalUserDep):
    # 헤더 메뉴에 "가입" 항목이 없으므로 현재 위치(active)를 넘기지 않는다
    return templates.TemplateResponse(
        request, "signup.html", {"logged_in": user is not None, "rules": AUTH_INPUT_RULES}
    )


@router.get("/login")
def login_page(request: Request, user: OptionalUserDep):
    # 가입하고 넘어오면(/login?joined=1) "가입이 끝났어요" 안내를 함께 보여 준다
    joined = request.query_params.get("joined") == "1"
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "active": "login",
            "logged_in": user is not None,
            "joined": joined,
            "rules": AUTH_INPUT_RULES,
        },
    )


@router.get("/chat")
def chat_page(request: Request, user: OptionalUserDep):
    # 로그인하지 않았으면 로그인 화면으로 보낸다(303).
    # 화면을 열어도 질문 API 는 서버가 다시 로그인을 확인한다
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request,
        "chat.html",
        {"active": "chat", "logged_in": user is not None, "rules": CHAT_INPUT_RULES},
    )


@router.get("/history")
def history_page():
    raise not_implemented("EE-17")

"""웹 페이지 라우트. (C 담당, EE-04·EE-09·EE-12·EE-17)

템플릿은 app/templates/, CSS·JS 는 app/static/ 에 둔다. (/static/... 으로 제공)
/chat, /history 는 비로그인이면 /login 으로 303 이동한다.
(로그인 확인은 app.auth.dependencies.OptionalUserDep 사용)
"""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.core.errors import not_implemented

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)

router = APIRouter(tags=["web"], include_in_schema=False)


@router.get("/")
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@router.get("/signup")
def signup_page(request: Request):
    # 헤더 메뉴에 "가입" 항목이 없으므로 현재 위치(active)를 넘기지 않는다
    return templates.TemplateResponse(request, "signup.html")


@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"active": "login"})


@router.get("/chat")
def chat_page():
    raise not_implemented("EE-12")


@router.get("/history")
def history_page():
    raise not_implemented("EE-17")

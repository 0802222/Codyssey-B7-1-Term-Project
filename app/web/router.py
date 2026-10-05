"""웹 페이지 라우트. (C 담당, EE-04·EE-09·EE-12·EE-17)

템플릿은 app/templates/, CSS·JS 는 app/static/ 에 둔다. (/static/... 으로 제공)
/chat, /history 는 비로그인이면 /login 으로 303 이동한다.
(로그인 확인은 app.auth.dependencies.OptionalUserDep 사용)
"""

from fastapi import APIRouter

from app.core.errors import not_implemented

router = APIRouter(tags=["web"], include_in_schema=False)


@router.get("/")
def index():
    raise not_implemented("EE-04")


@router.get("/signup")
def signup_page():
    raise not_implemented("EE-09")


@router.get("/login")
def login_page():
    raise not_implemented("EE-09")


@router.get("/chat")
def chat_page():
    raise not_implemented("EE-12")


@router.get("/history")
def history_page():
    raise not_implemented("EE-17")

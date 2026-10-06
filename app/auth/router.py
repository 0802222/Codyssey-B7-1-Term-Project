"""회원가입·로그인 API. (A 담당, EE-07·EE-08)"""

from fastapi import APIRouter

from app.auth.signup import router as signup_router
from app.core.errors import not_implemented

router = APIRouter(prefix="/api/auth", tags=["auth"])

router.include_router(signup_router)


@router.post("/login")
def login():
    raise not_implemented("EE-08")


@router.get("/me")
def me():
    raise not_implemented("EE-08")


@router.post("/logout", status_code=204)
def logout():
    raise not_implemented("EE-08")

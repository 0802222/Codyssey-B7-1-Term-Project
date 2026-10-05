"""회원가입·로그인 API. (A 담당, EE-07·EE-08)"""

from fastapi import APIRouter

from app.core.errors import not_implemented

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", status_code=201)
def signup():
    raise not_implemented("EE-07")


@router.post("/login")
def login():
    raise not_implemented("EE-08")


@router.get("/me")
def me():
    raise not_implemented("EE-08")


@router.post("/logout", status_code=204)
def logout():
    raise not_implemented("EE-08")

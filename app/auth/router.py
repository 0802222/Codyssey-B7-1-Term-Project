"""회원가입·로그인 API. (A 담당, EE-07·EE-08)"""

import re

from fastapi import APIRouter, Request
from pwdlib import PasswordHash
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import select

from app.core.deps import SettingsDep
from app.core.errors import AppError, ErrorCode, not_implemented
from app.db.models import User
from app.db.session import SessionDep

router = APIRouter(prefix="/api/auth", tags=["auth"])

password_hash = PasswordHash.recommended()


class SignupRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=10, max_length=128)


@router.post("/signup", status_code=201)
def signup(
    request: SignupRequest,
    http_request: Request,
    session: SessionDep,
    settings: SettingsDep,
):
    origin = http_request.headers.get("origin")

    if origin != settings.site_origin:
        raise AppError(
            status_code=403,
            code=ErrorCode.CSRF_REJECTED,
            message="허용되지 않은 요청입니다.",
        )

    email = request.email.strip().lower()

    if not email:
        raise AppError(
            status_code=422,
            code=ErrorCode.VALIDATION_ERROR,
            message="이메일을 입력해 주세요.",
        )

    if not re.fullmatch(r"[^@\s]+@(?:[^@\s.]+\.)+[^@\s.]+", email):
        raise AppError(
            status_code=422,
            code=ErrorCode.VALIDATION_ERROR,
            message="올바른 이메일 형식을 입력해 주세요.",
        )

    try:
        existing_user = session.exec(
            select(User).where(User.email == email)
        ).first()
    except SQLAlchemyError:
        session.rollback()
        raise AppError(
            status_code=503,
            code=ErrorCode.DB_ERROR,
            message="데이터베이스 오류가 발생했어요. 잠시 후 다시 시도해 주세요.",
        ) from None

    if existing_user is not None:
        raise AppError(
            status_code=409,
            code=ErrorCode.ACCOUNT_EXISTS,
            message="이미 가입된 이메일이에요.",
        )

    hashed_password = password_hash.hash(request.password)

    user = User(
        email=email,
        password_hash=hashed_password,
    )

    session.add(user)

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise AppError(
            status_code=409,
            code=ErrorCode.ACCOUNT_EXISTS,
            message="이미 가입된 이메일이에요.",
        ) from None
    except SQLAlchemyError:
        session.rollback()
        raise AppError(
            status_code=503,
            code=ErrorCode.DB_ERROR,
            message="데이터베이스 오류가 발생했어요. 잠시 후 다시 시도해 주세요.",
        ) from None

    try:
        session.refresh(user)
    except SQLAlchemyError:
        session.rollback()
        raise AppError(
            status_code=503,
            code=ErrorCode.DB_ERROR,
            message="데이터베이스 오류가 발생했어요. 잠시 후 다시 시도해 주세요.",
        ) from None

    return {
        "id": user.id,
        "email": user.email,
    }


@router.post("/login")
def login():
    raise not_implemented("EE-08")


@router.get("/me")
def me():
    raise not_implemented("EE-08")


@router.post("/logout", status_code=204)
def logout():
    raise not_implemented("EE-08")

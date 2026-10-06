"""회원가입 API. (A 담당, EE-07)"""

import re

from fastapi import APIRouter
from pydantic import BaseModel, Field
from pwdlib import PasswordHash
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.core.errors import AppError, ErrorCode
from app.db.models import User
from app.db.session import SessionDep

router = APIRouter()

password_hash = PasswordHash.recommended()


class SignupRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=10, max_length=128)


class SignupResponse(BaseModel):
    id: int
    email: str


def is_valid_email(email: str) -> bool:
    return re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) is not None


@router.post("/signup", status_code=201, response_model=SignupResponse)
def signup(data: SignupRequest, session: SessionDep):
    email = data.email.strip().lower()

    if not email:
        raise AppError(
            status_code=422,
            code=ErrorCode.VALIDATION_ERROR,
            message="이메일을 입력해 주세요.",
        )

    if not is_valid_email(email):
        raise AppError(
            status_code=422,
            code=ErrorCode.VALIDATION_ERROR,
            message="올바른 이메일 형식을 입력해 주세요.",
        )

    existing_user = session.exec(
        select(User).where(User.email == email)
    ).first()

    if existing_user is not None:
        raise AppError(
            status_code=409,
            code=ErrorCode.ACCOUNT_EXISTS,
            message="이미 가입된 이메일이에요.",
        )

    user = User(
        email=email,
        password_hash=password_hash.hash(data.password),
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
        )

    session.refresh(user)

    return SignupResponse(
        id=user.id,
        email=user.email,
    )

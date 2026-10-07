"""회원가입·로그인 API. (A 담당, EE-07·EE-08)"""

import re
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request, Response
from pwdlib import PasswordHash
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import select

from app.auth.dependencies import (
    SESSION_COOKIE_NAME,
    CsrfDep,
    CurrentUserDep,
    hash_token,
)
from app.core.deps import SettingsDep
from app.core.errors import AppError, ErrorCode
from app.db.models import AuthSession, User
from app.db.session import SessionDep

router = APIRouter(prefix="/api/auth", tags=["auth"])

password_hash = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = password_hash.hash("dummy-password")


class SignupRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(
        min_length=10,
        max_length=128,
    )


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(
        min_length=10,
        max_length=128,
    )


def _validate_origin(
    request: Request,
    settings,
) -> None:
    """요청 Origin이 허용된 사이트인지 확인한다.

    허용되지 않은 Origin이면 CSRF_REJECTED 오류를 발생시킨다.
    """
    origin = request.headers.get("origin")

    if origin != settings.site_origin:
        raise AppError(
            status_code=403,
            code=ErrorCode.CSRF_REJECTED,
            message="허용되지 않은 요청입니다.",
        )


def _validate_email(email: str) -> str:
    """이메일 형식을 검증하고 정규화한다.

    앞뒤 공백을 제거하고 소문자로 변환한다.
    """
    email = email.strip().lower()

    if not email:
        raise AppError(
            status_code=422,
            code=ErrorCode.VALIDATION_ERROR,
            message="이메일을 입력해 주세요.",
        )

    if not re.fullmatch(
        r"[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+",
        email,
    ):
        raise AppError(
            status_code=422,
            code=ErrorCode.VALIDATION_ERROR,
            message="올바른 이메일 형식을 입력해 주세요.",
        )

    return email


@router.post("/signup", status_code=201)
def signup(
    request: SignupRequest,
    http_request: Request,
    session: SessionDep,
    settings: SettingsDep,
):
    """회원가입을 처리하고 새로운 사용자를 생성한다.

    이메일 중복과 입력값을 검증한 뒤 비밀번호를 해시하여 저장한다.
    """

    _validate_origin(
        http_request,
        settings,
    )

    email = _validate_email(request.email)

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

    user = User(
        email=email,
        password_hash=password_hash.hash(
            request.password
        ),
    )

    session.add(user)

    try:
        session.commit()
        session.refresh(user)
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

    return {
        "id": user.id,
        "email": user.email,
    }


@router.post("/login")
def login(
    request: LoginRequest,
    http_request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
):
    """이메일과 비밀번호를 검증하여 로그인 세션을 생성한다.

    세션 토큰과 CSRF 토큰을 발급하고 세션 쿠키를 설정한다.
    """

    _validate_origin(
        http_request,
        settings,
    )

    email = _validate_email(request.email)

    try:
        user = session.exec(
            select(User).where(User.email == email)
        ).first()
    except SQLAlchemyError:
        session.rollback()
        raise AppError(
            status_code=503,
            code=ErrorCode.DB_ERROR,
            message="데이터베이스 오류가 발생했어요. 잠시 후 다시 시도해 주세요.",
        ) from None

    password_hash_value = (
        user.password_hash
        if user is not None
        else DUMMY_PASSWORD_HASH
    )

    password_valid = password_hash.verify(
        request.password,
        password_hash_value,
    )

    if user is None or not password_valid:
        raise AppError(
            status_code=401,
            code=ErrorCode.INVALID_CREDENTIALS,
            message="이메일 또는 비밀번호가 올바르지 않습니다.",
        )

    user_id = user.id
    user_email = user.email

    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)

    auth_session = AuthSession(
        user_id=user_id,
        token_hash=hash_token(session_token),
        csrf_token=csrf_token,
        expires_at=(
            datetime.now(UTC)
            + timedelta(
                seconds=settings.session_ttl_seconds
            )
        ),
    )

    session.add(auth_session)

    try:
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise AppError(
            status_code=503,
            code=ErrorCode.DB_ERROR,
            message="데이터베이스 오류가 발생했어요. 잠시 후 다시 시도해 주세요.",
        ) from None

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_seconds,
        path="/",
    )

    return {
        "user": {
            "id": user_id,
            "email": user_email,
        },
        "csrf_token": csrf_token,
    }


@router.get("/me")
def me(
    user: CurrentUserDep,
    request: Request,
):
    """현재 로그인한 사용자의 정보를 조회한다.

    인증된 세션의 사용자 정보와 CSRF 토큰을 반환한다.
    """

    auth_session = getattr(
        request.state,
        "auth_session",
        None,
    )

    if auth_session is None:
        raise AppError(
            status_code=401,
            code=ErrorCode.AUTH_REQUIRED,
            message="로그인이 필요합니다.",
        )

    return {
        "user": {
            "id": user.id,
            "email": user.email,
        },
        "csrf_token": auth_session.csrf_token,
    }


@router.post("/logout", status_code=204)
def logout(
    user: CurrentUserDep,
    _: CsrfDep,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
):
    """현재 로그인한 사용자의 세션을 종료한다.

    세션을 삭제하고 브라우저의 세션 쿠키를 제거한다.
    """

    auth_session = getattr(
        request.state,
        "auth_session",
        None,
    )

    if auth_session is not None:
        session.delete(auth_session)

        try:
            session.commit()
        except SQLAlchemyError:
            session.rollback()
            raise AppError(
                status_code=503,
                code=ErrorCode.DB_ERROR,
                message="데이터베이스 오류가 발생했어요. 잠시 후 다시 시도해 주세요.",
            ) from None

    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )

    return None

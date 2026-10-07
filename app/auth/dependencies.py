"""인증 의존성. (A 담당, EE-08)

다른 영역은 인증을 직접 구현하지 않고 이 의존성만 사용한다.
    def handler(user: CurrentUserDep): ...      # 로그인 필수
    def handler(user: CurrentUserDep, _: CsrfDep): ...   # 로그인 + 상태 변경 요청
    def page(user: OptionalUserDep): ...         # 페이지: None 이면 /login 으로 이동
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from app.core.errors import AppError, ErrorCode
from app.db.models import AuthSession, User
from app.db.session import SessionDep

SESSION_COOKIE_NAME = "session"


@dataclass(frozen=True)
class CurrentUser:
    id: int
    email: str


def hash_token(token: str) -> str:
    """세션 토큰을 SHA-256으로 해시한다."""
    return sha256(token.encode("utf-8")).hexdigest()


def _get_auth_session(
    request: Request,
    session: SessionDep,
) -> AuthSession | None:
    """세션 쿠키로 인증 세션을 조회하고 유효성을 확인한다.

    쿠키가 없거나 세션이 존재하지 않거나 만료된 경우 None을 반환한다.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)

    if not token:
        return None

    try:
        auth_session = session.exec(
            select(AuthSession).where(
                AuthSession.token_hash == hash_token(token)
            )
        ).first()
    except SQLAlchemyError:
        session.rollback()
        raise AppError(
            status_code=503,
            code=ErrorCode.DB_ERROR,
            message="데이터베이스 오류가 발생했어요. 잠시 후 다시 시도해 주세요.",
        ) from None

    if auth_session is None:
        return None

    if auth_session.expires_at <= datetime.now(UTC):
        return None

    request.state.auth_session = auth_session

    return auth_session


def get_current_user(
    request: Request,
    session: SessionDep,
) -> CurrentUser:
    """세션 쿠키로 로그인 사용자를 찾는다.

    없거나 만료된 세션이면 AppError(401, AUTH_REQUIRED)를 raise 한다.
    """
    auth_session = _get_auth_session(request, session)

    if auth_session is None:
        raise AppError(
            status_code=401,
            code=ErrorCode.AUTH_REQUIRED,
            message="로그인이 필요합니다.",
        )

    try:
        user = session.get(User, auth_session.user_id)
    except SQLAlchemyError:
        session.rollback()
        raise AppError(
            status_code=503,
            code=ErrorCode.DB_ERROR,
            message="데이터베이스 오류가 발생했어요. 잠시 후 다시 시도해 주세요.",
        ) from None

    if user is None:
        raise AppError(
            status_code=401,
            code=ErrorCode.AUTH_REQUIRED,
            message="로그인이 필요합니다.",
        )

    return CurrentUser(
        id=user.id,
        email=user.email,
    )


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def get_optional_user(
    request: Request,
    session: SessionDep,
) -> CurrentUser | None:
    """페이지용. 로그인했으면 사용자, 아니면 None을 돌려준다."""

    auth_session = _get_auth_session(request, session)

    if auth_session is None:
        return None

    try:
        user = session.get(User, auth_session.user_id)
    except SQLAlchemyError:
        session.rollback()
        raise AppError(
            status_code=503,
            code=ErrorCode.DB_ERROR,
            message="데이터베이스 오류가 발생했어요. 잠시 후 다시 시도해 주세요.",
        ) from None

    if user is None:
        return None

    return CurrentUser(
        id=user.id,
        email=user.email,
    )


OptionalUserDep = Annotated[CurrentUser | None, Depends(get_optional_user)]


def require_csrf(
    request: Request,
    user: CurrentUserDep,
) -> None:
    """로그인 후 상태 변경 요청의 X-CSRF-Token 헤더를 검증한다.

    실패하면 AppError(403, CSRF_REJECTED)를 raise 한다.
    """
    csrf_token = request.headers.get("X-CSRF-Token")
    auth_session = getattr(
        request.state,
        "auth_session",
        None,
    )

    if (
        not csrf_token
        or auth_session is None
        or csrf_token != auth_session.csrf_token
    ):
        raise AppError(
            status_code=403,
            code=ErrorCode.CSRF_REJECTED,
            message="CSRF 토큰이 유효하지 않습니다.",
        )


CsrfDep = Annotated[None, Depends(require_csrf)]

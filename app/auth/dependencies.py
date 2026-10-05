"""인증 의존성. (A 담당, EE-08)

다른 영역은 인증을 직접 구현하지 않고 이 의존성만 사용한다.
    def handler(user: CurrentUserDep): ...      # 로그인 필수
    def handler(user: CurrentUserDep, _: CsrfDep): ...   # 로그인 + 상태 변경 요청
    def page(user: OptionalUserDep): ...         # 페이지: None 이면 /login 으로 이동
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from app.core.errors import not_implemented
from app.db.session import SessionDep


@dataclass(frozen=True)
class CurrentUser:
    id: int
    email: str


def get_current_user(request: Request, session: SessionDep) -> CurrentUser:
    """세션 쿠키로 로그인 사용자를 찾는다.

    없거나 만료된 세션이면 AppError(401, AUTH_REQUIRED) 를 raise 한다.
    """
    raise not_implemented("EE-08")


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def get_optional_user(request: Request, session: SessionDep) -> CurrentUser | None:
    """페이지용. 로그인했으면 사용자, 아니면 None 을 돌려준다. (오류를 내지 않음)"""
    raise not_implemented("EE-08")


OptionalUserDep = Annotated[CurrentUser | None, Depends(get_optional_user)]


def require_csrf(request: Request, user: CurrentUserDep) -> None:
    """로그인 후 상태 변경 요청의 X-CSRF-Token 헤더를 검증한다.

    실패하면 AppError(403, CSRF_REJECTED) 를 raise 한다.
    """
    raise not_implemented("EE-08")


CsrfDep = Annotated[None, Depends(require_csrf)]

"""채팅 API. (B 담당, EE-13)"""

from fastapi import APIRouter

from app.auth.dependencies import CsrfDep, CurrentUserDep
from app.core.errors import not_implemented

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat")
def chat(user: CurrentUserDep, _csrf: CsrfDep):
    raise not_implemented("EE-13")

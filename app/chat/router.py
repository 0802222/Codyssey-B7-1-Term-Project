"""채팅 API. (B 담당, EE-13)"""

from fastapi import APIRouter, Request

from app.auth.dependencies import CsrfDep, CurrentUserDep
from app.chat.provider import AIProviderDep
from app.chat.rate_limit import RateLimiterDep
from app.chat.schemas import ChatRequest, ChatResponse
from app.chat.service import answer_question
from app.core.deps import SettingsDep
from app.db.session import SessionDep

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    request: Request,
    user: CurrentUserDep,
    _csrf: CsrfDep,
    session: SessionDep,
    settings: SettingsDep,
    provider: AIProviderDep,
    rate_limiter: RateLimiterDep,
):
    return await answer_question(
        body,
        user_id=user.id,
        request_id=request.state.request_id,
        session=session,
        settings=settings,
        provider=provider,
        rate_limiter=rate_limiter,
    )

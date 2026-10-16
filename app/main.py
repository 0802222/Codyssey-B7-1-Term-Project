"""앱 생성·라우터 조립. (L 담당)

실행: uv run uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import health
from app.auth.router import router as auth_router
from app.chat.router import router as chat_router
from app.conversations.router import router as conversations_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, log_event
from app.core.middleware import RequestIdMiddleware
from app.db.session import create_db_engine, init_db
from app.web.router import router as web_router

STATIC_DIR = Path(__file__).parent / "static"


class RevalidatingStaticFiles(StaticFiles):
    """정적 파일(CSS·JS·이미지)을 쓰기 전에 브라우저가 매번 서버에 바뀌었는지 묻게 한다.

    배포마다 파일 주소가 같아서, 캐시 지시가 없으면 브라우저가 예전 JS 를 잠시 그대로 쓸 수 있다.
    no-cache 는 "저장은 하되 쓰기 전에 확인"이라,
    바뀌지 않았으면 ETag 비교로 304(본문 없음)만 받는다.
    """

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    # DB 는 build 단계가 아니라 실행 시점에 만든다. (영속 디스크는 실행 중에만 연결됨)
    settings: Settings = app.state.settings
    init_db(app.state.engine)
    log_event("app_started", env=settings.app_env, ai_provider=settings.ai_provider)
    yield
    app.state.engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    is_production = settings.app_env == "production"
    app = FastAPI(
        title="EasyExplain",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if is_production else "/docs",
        redoc_url=None if is_production else "/redoc",
        openapi_url=None if is_production else "/openapi.json",
    )
    app.state.settings = settings
    app.state.engine = create_db_engine(settings.database_url)

    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(auth_router)
    app.include_router(conversations_router)
    app.include_router(chat_router)
    app.include_router(web_router)
    app.mount("/static", RevalidatingStaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()

"""배포 확인용 /health. 키·DB 경로·개인정보는 출력하지 않는다."""

import logging

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import AppError, ErrorCode
from app.core.logging import log_event
from app.db.session import SessionDep

router = APIRouter(tags=["health"])


@router.get("/health")
def health(session: SessionDep) -> dict[str, str]:
    try:
        session.connection().execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        log_event("health_db_failed", level=logging.ERROR, error_type=type(exc).__name__)
        raise AppError(503, ErrorCode.DB_ERROR, "DB 에 연결할 수 없어요.") from exc
    return {"status": "ok", "db": "ok"}

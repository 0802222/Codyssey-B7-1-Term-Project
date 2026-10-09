"""DB 엔진·세션. (L 이 뼈대 작성, 이후 A 담당)

라우터에서는 SessionDep 으로 세션을 받는다.
    def handler(session: SessionDep): ...
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Engine, event
from sqlmodel import Session, SQLModel, create_engine, select

from app.db.models import ChatTurn


def create_db_engine(database_url: str) -> Engine:
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _record) -> None:
        # SQLite 는 외래키 제약이 기본으로 꺼져 있다.
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def init_db(engine: Engine) -> None:
    """앱 시작 시 테이블을 만든다. 운영 DB 를 지우거나 스키마를 바꾸지 않는다."""
    database = engine.url.database
    if database and database != ":memory:":
        Path(database).parent.mkdir(parents=True, exist_ok=True)

    from app.db import models  # noqa: F401  (테이블 정의를 metadata 에 등록)

    SQLModel.metadata.create_all(engine)

    # 프로세스가 종료될 때 처리 중이던 턴은 다시 AI에 보내지 않고 중단 상태로 복구한다.
    with Session(engine) as session:
        pending_turns = session.exec(
            select(ChatTurn).where(ChatTurn.status == "pending")
        ).all()
        now = datetime.now(UTC)
        for turn in pending_turns:
            turn.status = "interrupted"
            turn.completed_at = now
        if pending_turns:
            session.add_all(pending_turns)
            session.commit()


def get_session(request: Request):
    with Session(request.app.state.engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]

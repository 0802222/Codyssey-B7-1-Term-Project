import sqlite3
from pathlib import Path
from uuid import uuid4

from sqlmodel import Session, SQLModel, create_engine

from app.db.models import ChatTurn, Conversation, User


def test_check_logs_sql_and_sqlite_backup_restore(tmp_path: Path):
    database_path = tmp_path / "source.db"
    backup_path = tmp_path / "backup.db"
    engine = create_engine(f"sqlite:///{database_path}")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = User(email="ee20-check@example.invalid", password_hash="test")
        session.add(user)
        session.commit()
        session.refresh(user)

        conversation = Conversation(user_id=user.id, title="임시 검증 대화")
        session.add(conversation)
        session.commit()
        session.refresh(conversation)

        session.add(
            ChatTurn(
                conversation_id=conversation.id,
                user_id=user.id,
                client_request_id=uuid4(),
                request_id="ee20-test",
                level="easy",
                question="임시 검증 질문",
                answer="임시 검증 답변",
                status="completed",
            )
        )
        session.commit()

    engine.dispose()
    sql_path = Path(__file__).resolve().parents[2] / "scripts" / "check_logs.sql"
    sql = sql_path.read_text(encoding="utf-8")
    expected_row = (
        "ee20-check@example.invalid",
        "임시 검증 대화",
        "easy",
        "completed",
        "임시 검증 질문",
        "임시 검증 답변",
    )

    with sqlite3.connect(database_path) as source:
        rows = source.execute(sql, {"email": "ee20-check@example.invalid"}).fetchall()
        assert len(rows) == 1
        assert (rows[0][0], rows[0][1], *rows[0][3:]) == expected_row

        with sqlite3.connect(backup_path) as backup:
            source.backup(backup)

        source.execute("DELETE FROM chat_turns")
        source.commit()

        with sqlite3.connect(backup_path) as backup:
            backup.backup(source)

        restored_rows = source.execute(
            sql, {"email": "ee20-check@example.invalid"}
        ).fetchall()
        assert restored_rows == rows
        assert source.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

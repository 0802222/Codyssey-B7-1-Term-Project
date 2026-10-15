
"""SQLite 데이터베이스 수동 백업 스크립트

uv run python scripts/backup_db.py 로 실행
"""

import sys
from pathlib import Path

# 프로젝트 루트를 Python 모듈 검색 경로에 추가
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

import sqlite3
from datetime import datetime

from app.core.config import get_settings


BACKUP_DIR = BASE_DIR / "backups"


def backup_database() -> Path:
    settings = get_settings()
    database_url = settings.database_url

    if not database_url.startswith("sqlite:///"):
        raise ValueError("이 스크립트는 SQLite 데이터베이스만 지원합니다.")

    database_path = Path(database_url.removeprefix("sqlite:///"))

    if not database_path.is_absolute():
        database_path = (BASE_DIR / database_path).resolve()

    if not database_path.is_file():
        raise FileNotFoundError(f"DB 파일을 찾을 수 없습니다: {database_path}")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"backup_{timestamp}.db"

    with sqlite3.connect(database_path) as source:
        with sqlite3.connect(backup_path) as target:
            source.backup(target)

    print(f"백업 완료: {backup_path}")
    return backup_path


if __name__ == "__main__":
    backup_database()

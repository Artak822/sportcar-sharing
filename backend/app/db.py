import os
import sqlite3
from pathlib import Path

HERE = Path(__file__).parent
DEFAULT_PATH = HERE.parent / "pitlane.db"


def db_path() -> str:
    return os.environ.get("PITLANE_DB", str(DEFAULT_PATH))


def connect(path: str | None = None) -> sqlite3.Connection:
    # isolation_level=None: транзакции открываем сами (см. main.get_db)
    conn = sqlite3.connect(path or db_path(), isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init(conn: sqlite3.Connection) -> None:
    conn.executescript((HERE / "schema.sql").read_text())

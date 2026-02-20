import sqlite3
from datetime import datetime, timezone

DB_PATH = "tasks.db"


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT NOT NULL,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                last_nudge_at TEXT
            )
        """)
        conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_task(description: str) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO tasks (description, created_at) VALUES (?, ?)",
            (description, _now()),
        )
        conn.commit()
        return cur.lastrowid


def complete_task(task_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE tasks SET completed_at = ? WHERE id = ? AND completed_at IS NULL",
            (_now(), task_id),
        )
        conn.commit()
        return cur.rowcount > 0


def list_open_tasks() -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM tasks WHERE completed_at IS NULL ORDER BY created_at ASC"
        ).fetchall()


def list_todays_completed() -> list[sqlite3.Row]:
    today = datetime.now(timezone.utc).date().isoformat()
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM tasks WHERE completed_at LIKE ? ORDER BY completed_at ASC",
            (f"{today}%",),
        ).fetchall()


def get_stale_tasks(hours: int = 24) -> list[sqlite3.Row]:
    """Return open tasks that haven't been nudged (or were last nudged) more than `hours` ago."""
    with _connect() as conn:
        return conn.execute(
            """
            SELECT * FROM tasks
            WHERE completed_at IS NULL
              AND (
                last_nudge_at IS NULL
                OR (julianday('now') - julianday(last_nudge_at)) * 24 >= ?
              )
              AND (julianday('now') - julianday(created_at)) * 24 >= ?
            ORDER BY created_at ASC
            """,
            (hours, hours),
        ).fetchall()


def update_nudge_time(task_id: int):
    with _connect() as conn:
        conn.execute(
            "UPDATE tasks SET last_nudge_at = ? WHERE id = ?",
            (_now(), task_id),
        )
        conn.commit()

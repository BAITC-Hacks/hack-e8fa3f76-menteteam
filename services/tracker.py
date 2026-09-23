"""Private, local persistence for action item status and in-app reminders."""
import hashlib
import sqlite3
from datetime import date
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "tasks.sqlite3"


def _key(meeting: str, evidence: str, owner: str) -> str:
    return hashlib.sha256(f"{meeting}\0{evidence}\0{owner}".encode("utf-8")).hexdigest()


def save_status(meeting: str, evidence: str, owner: str, title: str, deadline: str,
                due_date: date | None, status: str) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS action_items (
            id TEXT PRIMARY KEY, meeting TEXT NOT NULL, title TEXT NOT NULL,
            owner TEXT NOT NULL, deadline TEXT NOT NULL, due_date TEXT,
            status TEXT NOT NULL CHECK(status IN ('В работе', 'Выполнено'))
        )""")
        db.execute("""INSERT INTO action_items VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET title=excluded.title, deadline=excluded.deadline,
            due_date=excluded.due_date, status=excluded.status""",
            (_key(meeting, evidence, owner), meeting, title, owner, deadline,
             due_date.isoformat() if due_date else None, status))


def get_status(meeting: str, evidence: str, owner: str) -> str | None:
    if not DB_PATH.exists():
        return None
    with sqlite3.connect(DB_PATH) as db:
        row = db.execute("SELECT status FROM action_items WHERE id=?",
                          (_key(meeting, evidence, owner),)).fetchone()
    return row[0] if row else None


def list_action_items() -> list[dict]:
    if not DB_PATH.exists():
        return []
    with sqlite3.connect(DB_PATH) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute(
            "SELECT meeting, title, owner, deadline, due_date, status FROM action_items ORDER BY due_date")]

"""SQLite aggregate persistence with stable meeting/task identities."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from core.models import MeetingResult


class SQLiteMeetings:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS meetings (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS notifications (
                    id TEXT PRIMARY KEY, sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            """)
        self.path.chmod(0o600)

    def connect(self):
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA secure_delete=ON")
        return connection

    def save(self, result: MeetingResult) -> None:
        with self.connect() as db:
            db.execute("""INSERT INTO meetings(id, payload) VALUES (?, ?)
                ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, updated_at=CURRENT_TIMESTAMP""",
                       (result.id, result.model_dump_json()))

    def get(self, meeting_id: str) -> MeetingResult | None:
        with self.connect() as db:
            row = db.execute("SELECT payload FROM meetings WHERE id=?", (meeting_id,)).fetchone()
        return MeetingResult.model_validate_json(row[0]) if row else None

    def list(self) -> list[MeetingResult]:
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM meetings ORDER BY created_at DESC, rowid DESC").fetchall()
        return [MeetingResult.model_validate_json(row[0]) for row in rows]

    def delete(self, meeting_id: str) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM meetings WHERE id=?", (meeting_id,))

    @contextmanager
    def notification(self, key: str, meeting: MeetingResult | None = None):
        """Serialize workers and commit the receipt only after successful delivery."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            pending = not db.execute("SELECT 1 FROM notifications WHERE id=?", (key,)).fetchone()
            if pending and meeting is not None:
                current = db.execute("SELECT payload FROM meetings WHERE id=?", (meeting.id,)).fetchone()
                pending = current is not None and current[0] == meeting.model_dump_json()
            yield pending
            if pending:
                db.execute("INSERT INTO notifications(id) VALUES (?)", (key,))

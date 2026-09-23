"""SQLite aggregate persistence with stable meeting/task identities."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from core.models import DirectionReport, MeetingResult


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

    def save_reports(self, meeting_id: str, reports: list[DirectionReport], questions: list[str]) -> None:
        """A long model job must not overwrite newer names, roles or task edits."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM meetings WHERE id=?", (meeting_id,)).fetchone()
            if row is None:
                raise ValueError("Совещание уже удалено.")
            current = MeetingResult.model_validate_json(row[0])
            current.reports = reports
            current.questions = list(dict.fromkeys([*current.questions, *questions]))
            db.execute("UPDATE meetings SET payload=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                       (current.model_dump_json(), meeting_id))

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
                # Compare the loaded schema so older records with missing new
                # optional fields still match; changed approvals/recipients do not.
                pending = current is not None and MeetingResult.model_validate_json(current[0]) == meeting
            yield pending
            if pending:
                db.execute("INSERT INTO notifications(id) VALUES (?)", (key,))

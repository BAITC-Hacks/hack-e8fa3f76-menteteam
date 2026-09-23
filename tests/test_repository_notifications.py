from datetime import date

from core.models import MeetingResult, Task


def test_same_title_meetings_and_review_survive_reload(tmp_path):
    from adapters.repository import SQLiteMeetings
    repo = SQLiteMeetings(tmp_path / "meetings.db")
    first = MeetingResult(title="Планёрка", summary="A", tasks=[Task(title="Отчёт", evidence="Отчёт")])
    second = MeetingResult(title="Планёрка", summary="B")
    repo.save(first)
    repo.save(second)
    first.tasks[0].status = "Выполнено"
    first.tasks[0].approved = True
    repo.save(first)
    fresh = SQLiteMeetings(tmp_path / "meetings.db")
    assert len(fresh.list()) == 2
    assert fresh.get(first.id).tasks[0].status == "Выполнено"
    assert fresh.get(first.id).tasks[0].approved
    assert fresh.get(second.id).summary == "B"


def test_notifications_require_approval_and_deduplicate(tmp_path):
    from adapters.repository import SQLiteMeetings
    from services.notifications import dispatch
    repo = SQLiteMeetings(tmp_path / "meetings.db")
    meeting = MeetingResult(title="Совещание", summary="", tasks=[
        Task(title="Отчёт", owner="Айжан", evidence="Отчёт", email="a@example.test",
             due_date=date(2026, 9, 24))])
    repo.save(meeting)
    outbox = tmp_path / "outbox"
    assert dispatch(repo, outbox, date(2026, 9, 23)) == 0
    meeting.tasks[0].approved = True
    repo.save(meeting)
    assert dispatch(repo, outbox, date(2026, 9, 23)) == 2  # assignment and upcoming
    assert len(list(outbox.glob("*.eml"))) == 2
    assert dispatch(repo, outbox, date(2026, 9, 23)) == 0
    assert dispatch(repo, outbox, date(2026, 9, 25)) == 1  # overdue
    meeting.tasks[0].status = "Выполнено"
    repo.save(meeting)
    assert dispatch(repo, outbox, date(2026, 9, 26)) == 0


def test_failed_delivery_can_retry(tmp_path):
    from adapters.repository import SQLiteMeetings
    from services.notifications import dispatch
    repo = SQLiteMeetings(tmp_path / "meetings.db")
    repo.save(MeetingResult(title="M", summary="", tasks=[
        Task(title="T", evidence="T", email="a@example.test", approved=True)]))
    def fail(message):
        raise OSError("SMTP unavailable")
    import pytest
    with pytest.raises(OSError):
        dispatch(repo, tmp_path / "mail", date(2026, 9, 23), send=fail)
    assert dispatch(repo, tmp_path / "mail", date(2026, 9, 23)) == 1


def test_revoked_approval_after_snapshot_prevents_delivery(tmp_path, monkeypatch):
    from adapters.repository import SQLiteMeetings
    from services.notifications import dispatch
    repo = SQLiteMeetings(tmp_path / "meetings.db")
    meeting = MeetingResult(title="M", summary="", tasks=[
        Task(title="Private", evidence="Private", email="old@example.test", approved=True)])
    repo.save(meeting)
    original_list = repo.list

    def snapshot_then_revoke():
        snapshot = original_list()
        meeting.tasks[0].approved = False
        meeting.tasks[0].email = "new@example.test"
        repo.save(meeting)
        return snapshot

    monkeypatch.setattr(repo, "list", snapshot_then_revoke)
    assert dispatch(repo, tmp_path / "mail", date(2026, 9, 23)) == 0
    assert not list((tmp_path / "mail").glob("*.eml"))

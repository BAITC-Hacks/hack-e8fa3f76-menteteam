from datetime import date

from core.models import Segment


def test_grounding_rejects_fabrication_and_uses_real_timestamp():
    from core.grounding import build_result
    segments = [Segment(id="s1", speaker="SPEAKER_00", start=12, end=15,
                        text="Айжан, подготовь отчёт завтра."),
                Segment(id="s2", speaker="SPEAKER_01", start=15, end=17,
                        text="Хорошо, подготовлю.")]
    result = build_result("Встреча", segments, "ru", {
        "summary": "Отчёт", "tasks": [
            {"title": "Отчёт", "owner": "Айжан", "deadline": "завтра",
             "evidence": "Айжан, подготовь отчёт завтра.", "timestamp": 999},
            {"title": "Выдумка", "evidence": "Купить самолёт"},
        ]}, date(2026, 9, 23))
    assert len(result.tasks) == 1
    task = result.tasks[0]
    assert task.timestamp == 12
    assert task.speaker_id == "SPEAKER_00"
    assert task.owner == "Айжан"
    assert task.due_date == date(2026, 9, 24)
    assert not task.approved
    assert any("цитат" in q.lower() for q in result.questions)


def test_unknown_owner_and_invented_date_require_review():
    from core.grounding import build_result
    result = build_result("Встреча", [Segment(id="s", text="Нужно подготовить отчёт.")], "ru",
                          {"tasks": [{"title": "Отчёт", "owner": "Борис", "deadline": "завтра",
                                      "due_date": "2030-01-01", "evidence": "Нужно подготовить отчёт."}]})
    assert result.tasks[0].owner == "Ответственный не определён"
    assert result.tasks[0].due_date is None


def test_cross_segment_quote_normalizes_whitespace_and_keeps_start():
    from core.grounding import build_result
    result = build_result("Встреча", [Segment(id="s1", start=4, text="Мен есепті"),
                                    Segment(id="s2", start=8, text="ертең жіберемін.")], "kk",
                          {"tasks": [{"title": "Есеп", "evidence": "Мен есепті  ертең жіберемін.",
                                      "deadline": "ертең"}]}, date(2026, 9, 23))
    assert result.tasks[0].timestamp == 4
    assert result.tasks[0].due_date == date(2026, 9, 24)


def test_speaker_rename_does_not_reassign_named_recipient():
    from core.grounding import rename_participants
    from core.models import MeetingResult, Task
    meeting = MeetingResult(title="M", summary="", tasks=[
        Task(title="Отчёт", owner="Айжан", evidence="Айжан, сделай", speaker_id="SPEAKER_00"),
        Task(title="Письмо", owner="SPEAKER_00", evidence="Я отправлю", speaker_id="SPEAKER_00")])
    updated = rename_participants(meeting, {"SPEAKER_00": "Борис"})
    assert [t.owner for t in updated.tasks] == ["Айжан", "Борис"]
    assert meeting.tasks[1].owner == "SPEAKER_00"


def test_cache_key_accepts_local_model_paths_and_varies_with_settings(tmp_path):
    from application.process import cache_key
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"audio")
    key = cache_key(audio, {"model": "/models/gemma", "compute": "int8"})
    assert len(key) == 64 and "/" not in key
    assert key != cache_key(audio, {"model": "/models/gemma", "compute": "float32"})


def test_substrings_do_not_confirm_different_person_or_day():
    from core.grounding import build_result
    result = build_result("M", [Segment(id="s", text="Жанна, подготовь отчёт послезавтра.")], "ru",
                          {"tasks": [{"title": "Отчёт", "owner": "Анна", "deadline": "завтра",
                                      "evidence": "Жанна, подготовь отчёт послезавтра."}]}, date(2026, 9, 23))
    assert result.tasks[0].owner == "Ответственный не определён"
    assert result.tasks[0].due_date is None


def test_cross_speaker_quote_cannot_assign_questioner():
    from core.grounding import build_result
    segments = [Segment(id="1", speaker="SPEAKER_00", text="Кто подготовит отчёт?"),
                Segment(id="2", speaker="SPEAKER_01", text="Я подготовлю завтра.")]
    result = build_result("M", segments, "ru", {"tasks": [
        {"title": "Отчёт", "owner": "SPEAKER_00", "deadline": "завтра",
         "evidence": "Кто подготовит отчёт? Я подготовлю завтра."}]}, date(2026, 9, 23))
    assert result.tasks[0].owner == "Ответственный не определён"
    assert result.tasks[0].owner_speaker_id == ""

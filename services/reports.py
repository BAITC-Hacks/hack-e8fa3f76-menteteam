"""Refresh report rows from an existing transcript without replacing reviewed tasks."""
from adapters.gemma import LocalGemma
from core.grounding import build_result
from core.models import MeetingResult


def rebuild_reports(meeting: MeetingResult, model_id: str, token: str | None = None) -> MeetingResult:
    if not meeting.transcript:
        raise ValueError("Стенограмма отсутствует.")
    transcript = "\n".join(f"[{segment.id}] [{segment.start:.1f}-{segment.end:.1f}] {segment.speaker}: {segment.text}"
                           for segment in meeting.transcript)
    extracted = LocalGemma(model_id, token).extract(transcript)
    grounded = build_result(meeting.title, meeting.transcript, meeting.language,
                            {"reports": extracted.get("reports", [])}, meeting.meeting_date)
    updated = meeting.model_copy(deep=True)
    updated.reports = grounded.reports
    updated.questions = list(dict.fromkeys([*meeting.questions, *grounded.questions]))
    return updated

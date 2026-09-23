"""Refresh report rows from an existing transcript without replacing reviewed tasks."""
from adapters.gemma import LocalGemma
from application.security_gate import ERROR_MESSAGE, REVIEW_MESSAGE, check_transcript
from core.grounding import build_result
from core.models import MeetingResult


def rebuild_reports(meeting: MeetingResult, model_id: str, token: str | None = None) -> MeetingResult:
    # A previously blocked, already-redacted transcript is not a new approval.
    if meeting.security is not None and meeting.security.requires_review:
        updated = meeting.model_copy(deep=True)
        updated.warnings.append(
            ERROR_MESSAGE if meeting.security.status == "security_error" else REVIEW_MESSAGE,
        )
        return updated
    if not meeting.transcript:
        raise ValueError("Стенограмма отсутствует.")
    checked = check_transcript(
        " ".join(segment.text for segment in meeting.transcript), meeting.transcript,
    )
    updated = meeting.model_copy(deep=True)
    updated.security = checked.decision
    updated.transcript = checked.segments
    if checked.decision.requires_review:
        updated.warnings.append(
            ERROR_MESSAGE if checked.decision.status == "security_error" else REVIEW_MESSAGE,
        )
        return updated
    extracted = LocalGemma(model_id, token).extract(checked.text, segments=checked.segments)
    grounded = build_result(meeting.title, checked.segments, meeting.language,
                            {"reports": extracted.get("reports", [])}, meeting.meeting_date)
    updated.reports = grounded.reports
    updated.questions = list(dict.fromkeys([*meeting.questions, *grounded.questions]))
    return updated

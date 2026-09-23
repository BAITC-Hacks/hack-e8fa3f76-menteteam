"""Adapt the existing security API to backend segments and response models.

Detection, redaction, risk scoring and auditing remain in security/. This
module only routes decisions and projects existing findings onto segment text.
"""

from dataclasses import dataclass

from core.models import SecurityDecision, Segment
from security.audit_logger import AuditLogger
from security.pii_detector import Finding
from security.sanitizer import redact_findings
from security.security_pipeline import analyze_transcript

REVIEW_MESSAGE = "Требуется проверка безопасности. Текст не передан в LLM."
ERROR_MESSAGE = "Проверка безопасности не завершена. Текст не передан в LLM."


@dataclass
class CheckedTranscript:
    """Sanitized text plus unchanged segment attribution and timing."""

    text: str
    segments: list[Segment]
    decision: SecurityDecision


def check_transcript(
    text: str, segments: list[Segment] | None = None,
) -> CheckedTranscript:
    """Fail closed, including on invalid security responses or audit failure.

    When segments are supplied, text must be their space-joined text. Scan
    before inserting speaker labels so instructions split across turns remain
    detectable and numeric timestamps cannot be mistaken for personal data.
    """
    segments = segments or []
    try:
        if segments and text != " ".join(s.text for s in segments):
            raise ValueError("Transcript and segments do not match.")
        result = analyze_transcript(text)
        if (type(result["requires_review"]) is not bool
                or not isinstance(result["sanitized_text"], str)):
            raise ValueError("Invalid security response.")
        decision = SecurityDecision(
            status="requires_review" if result["requires_review"] else "passed",
            requires_review=result["requires_review"],
            risk_level=result["risk_level"],
            llm_input_policy=result["llm_input_policy"],
            pii_detected=result["pii_detected"],
            prompt_injection_detected=result["prompt_injection_detected"],
        )
        sanitized = result["sanitized_text"]
        safe_segments = []
        offset = 0
        for segment in segments:
            end = offset + len(segment.text)
            # Reuse the existing redactor for spans crossing segment boundaries.
            # Only text is changed; id, speaker, start and end stay intact.
            local_findings = [
                Finding(
                    type=item["type"], value="",
                    start=max(item["start"], offset) - offset,
                    end=min(item["end"], end) - offset,
                    risk=item["risk"],
                )
                for item in result["findings"]
                if item["start"] < end and item["end"] > offset
            ]
            safe_segments.append(segment.model_copy(update={
                "text": redact_findings(segment.text, local_findings),
            }))
            offset = end + 1
        return CheckedTranscript(sanitized, safe_segments, decision)
    except Exception:
        # Never expose the exception: it can contain the original transcript.
        # The pipeline normally audits its own failures; this also covers
        # failures at this integration boundary. A broken logger cannot reopen it.
        try:
            AuditLogger().log_event(
                "SECURITY_ERROR", "HIGH", {"error_code": "PROCESSING_FAILED"},
            )
        except Exception:
            pass
        return CheckedTranscript(
            "", [s.model_copy(update={"text": ""}) for s in segments],
            SecurityDecision(
                status="security_error", requires_review=True,
                risk_level="CRITICAL", error_code="SECURITY_PROCESSING_FAILED",
            ),
        )

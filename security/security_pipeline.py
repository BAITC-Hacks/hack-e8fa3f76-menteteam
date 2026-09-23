"""Security boundary between local transcription and a future local LLM."""

from collections import Counter

from .audit_logger import AuditLogError, AuditLogger
from .prompt_guard import analyze_prompt_injection
from .sanitizer import sanitize_with_findings

_RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
# Bound synchronous regex work and audit count sizes for a single request.
MAX_TRANSCRIPT_CHARS = 1_000_000


def analyze_transcript(text: str, *,
                       audit_logger: AuditLogger | None = None) -> dict:
    """Analyze untrusted data without calling an LLM or any network service.

    Pipeline findings omit raw values; the low-level detector exposes them for
    in-memory consumers. Invalid input and unavailable auditing fail closed.
    Empty transcripts are valid. Whitespace and offsets are preserved.
    """
    logger = audit_logger if audit_logger is not None else AuditLogger()
    if not isinstance(text, str) or len(text) > MAX_TRANSCRIPT_CHARS:
        logger.log_event("SECURITY_ERROR", "HIGH",
                         {"error_code": "INVALID_INPUT"})
        raise ValueError(
            "Transcript must be a string of at most 1000000 characters."
        )
    try:
        sanitized, findings = sanitize_with_findings(text)
        injection = analyze_prompt_injection(text)
        risk = max([injection["risk"], *(item.risk for item in findings)],
                   key=_RISK_ORDER.__getitem__)
        suspicious = injection["is_suspicious"]
        result = {
            "risk_level": risk,
            "pii_detected": bool(findings),
            "prompt_injection_detected": suspicious,
            "findings": [
                {"type": item.type, "start": item.start, "end": item.end,
                 "risk": item.risk}
                for item in findings
            ],
            "prompt_injection": injection,
            "sanitized_text": sanitized,
            "llm_input_policy": "UNTRUSTED",
            "requires_review": suspicious or risk == "CRITICAL",
            "recommendation": (
                "Hold for review; keep transcript separate from "
                "trusted instructions."
                if suspicious or risk == "CRITICAL" else
                "Use sanitized transcript only as untrusted data, "
                "separate from "
                "system and application instructions."
            ),
        }
        if findings:
            logger.log_event("PII_DETECTED", risk, {
                "pii_counts": dict(Counter(item.type for item in findings)),
                "finding_count": len(findings),
            })
            logger.log_event("TRANSCRIPT_SANITIZED", risk,
                             {"finding_count": len(findings)})
        if suspicious:
            logger.log_event("PROMPT_INJECTION_DETECTED", "HIGH",
                             {"match_count": len(injection["matches"])})
        logger.log_event("SECURITY_PIPELINE_COMPLETED", risk, {
            "pii_detected": bool(findings),
            "prompt_injection_detected": suspicious,
            "llm_input_policy": "UNTRUSTED",
        })
        return result
    except AuditLogError:
        raise
    except Exception:
        logger.log_event("SECURITY_ERROR", "HIGH",
                         {"error_code": "PROCESSING_FAILED"})
        raise RuntimeError("Security processing failed.") from None

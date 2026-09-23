"""Local JSONL audit events using a closed metadata schema, never free text."""

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

_LOCK = Lock()
_EVENTS = frozenset({
    "PII_DETECTED", "TRANSCRIPT_SANITIZED", "PROMPT_INJECTION_DETECTED",
    "SECURITY_PIPELINE_COMPLETED", "SECURITY_ERROR",
})
_RISKS = frozenset({"LOW", "MEDIUM", "HIGH", "CRITICAL"})
_KINDS = frozenset({
    "EMAIL", "PHONE", "IIN", "PASSWORD", "API_KEY", "CREDIT_CARD",
})


class AuditLogError(RuntimeError):
    """The mandatory local audit could not be written."""


class AuditLogger:
    """Write only approved counts and flags; reject arbitrary metadata.

    No root logger is used: host applications may attach remote handlers.
    File paths are trusted application configuration, never transcript content.
    """

    def __init__(self, path: str | Path = "security_audit.jsonl") -> None:
        self.path = Path(path)

    def log_event(self, event_type: str, severity: str,
                  metadata: dict | None = None) -> None:
        """Append an event or raise a fixed, content-free error."""
        if event_type not in _EVENTS or severity not in _RISKS:
            raise ValueError("Invalid audit event or severity.")
        safe: dict = {}
        for key, value in (metadata or {}).items():
            if key in {"finding_count", "match_count"}:
                valid = type(value) is int and 0 <= value <= 1_000_000
            elif key in {"pii_detected", "prompt_injection_detected"}:
                valid = type(value) is bool
            elif key == "llm_input_policy":
                valid = type(value) is str and value == "UNTRUSTED"
            elif key == "error_code":
                valid = type(value) is str and value in {
                    "INVALID_INPUT", "PROCESSING_FAILED",
                }
            elif key == "pii_counts":
                valid = type(value) is dict and all(
                    kind in _KINDS and type(count) is int
                    and 0 <= count <= 1_000_000
                    for kind, count in value.items()
                )
                if valid:
                    value = dict(value)
            else:
                valid = False
            if not valid:
                raise ValueError("Unsafe audit metadata rejected.")
            safe[key] = value
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type, "severity": severity, "metadata": safe,
        }
        try:
            with _LOCK, self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=True) + "\n")
        except (OSError, ValueError):
            raise AuditLogError("Local security audit write failed.") from None

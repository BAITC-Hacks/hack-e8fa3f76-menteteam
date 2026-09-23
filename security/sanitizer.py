"""Replace sensitive spans without retaining a reverse mapping."""

from .pii_detector import Finding, detect_pii

_PRIORITY = {
    "EMAIL": 0, "PHONE": 1, "IIN": 2, "CREDIT_CARD": 3,
    "API_KEY": 4, "PASSWORD": 5,
}


def redact_findings(text: str, findings: list[Finding]) -> str:
    """Merge overlapping spans so no part of an overlapping secret leaks."""
    spans: list[tuple[int, int, str]] = []
    for item in sorted(findings, key=lambda finding: finding.start):
        if spans and item.start < spans[-1][1]:
            start, end, kind = spans[-1]
            kind = max((kind, item.type), key=_PRIORITY.__getitem__)
            spans[-1] = (start, max(end, item.end), kind)
        else:
            spans.append((item.start, item.end, item.type))
    pieces: list[str] = []
    cursor = 0
    for start, end, kind in spans:
        pieces.extend((text[cursor:start], f"[REDACTED_{kind}]"))
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)


def sanitize_with_findings(text: str) -> tuple[str, list[Finding]]:
    """Return sanitized text and original sensitive findings (do not log)."""
    findings = detect_pii(text)
    return redact_findings(text, findings), findings


def sanitize_text(text: str) -> str:
    """Return text with detected PII replaced by typed placeholders."""
    return sanitize_with_findings(text)[0]

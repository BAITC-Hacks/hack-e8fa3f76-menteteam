"""Local PII detection; findings contain secrets and stay in memory."""

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Finding:
    """A half-open character span in the original transcript."""

    type: str
    value: str = field(repr=False)
    start: int
    end: int
    risk: str


_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.UNICODE)
_NUMBER = re.compile(r"(?<!\w)\+?\d(?:[ \t().-]*\d){6,18}(?!\w)")
_IIN = re.compile(r"(?<!\w)\d{12}(?!\w)")
_PASSWORD_LABEL = r"(?:password|passwd|pwd|пароль)"
_KEY_LABEL = (
    r"(?:api[ _-]?(?:key|token)|access[ _-]?token|auth[ _-]?token|"
    r"token|api[ _-]?ключ|ключ[ _-]?api|токен(?:\s+доступа)?)"
)


def _credential_pattern(label: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?<!\w){label}\b\s*(?:[:=]|\bis\b|это)\s*"
        r"(?:\"(?P<double>[^\"\r\n]+)\"|'(?P<single>[^'\r\n]+)'|"
        r"(?P<bare>[^\s,;\"'<>]+))",
        re.IGNORECASE,
    )


_PASSWORD = _credential_pattern(_PASSWORD_LABEL)
_API_KEY = _credential_pattern(_KEY_LABEL)
_BARE_TOKEN = re.compile(
    r"(?<![\w-])(?:sk-[A-Za-z0-9_-]{12,}|"
    r"gh[pousr]_[A-Za-z0-9]{20,}|"
    r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)(?![\w-])"
)
_BEARER = re.compile(r"\bBearer\s+([A-Za-z0-9._~+/-]+=*)", re.IGNORECASE)


def detect_pii(text: str) -> list[Finding]:
    """Find candidates locally, including overlaps; never log their values.

    Numeric detection intentionally uses shape rather than checksum validation:
    an invalid or mistyped identifier must still be redacted. Arbitrary secrets
    without a label or recognizable token prefix cannot reliably be detected.
    """
    if not isinstance(text, str):
        raise TypeError("Transcript must be a string.")
    findings: list[Finding] = []

    def add(kind: str, start: int, end: int, risk: str) -> None:
        findings.append(Finding(kind, text[start:end], start, end, risk))

    for match in _EMAIL.finditer(text):
        add("EMAIL", *match.span(), "MEDIUM")
    for match in _IIN.finditer(text):
        add("IIN", *match.span(), "HIGH")
    for match in _NUMBER.finditer(text):
        digits = sum(char.isdigit() for char in match.group())
        if 13 <= digits <= 19:
            add("CREDIT_CARD", *match.span(), "HIGH")
        elif digits == 12 and not match.group().startswith("+"):
            add("IIN", *match.span(), "HIGH")
        elif 7 <= digits <= 15:
            add("PHONE", *match.span(), "MEDIUM")
    for kind, pattern in (("PASSWORD", _PASSWORD), ("API_KEY", _API_KEY)):
        for match in pattern.finditer(text):
            group = next(name for name in ("double", "single", "bare")
                         if match.group(name) is not None)
            add(kind, *match.span(group), "CRITICAL")
    for match in _BARE_TOKEN.finditer(text):
        add("API_KEY", *match.span(), "CRITICAL")
    for match in _BEARER.finditer(text):
        add("API_KEY", *match.span(1), "CRITICAL")
    return sorted(
        set(findings), key=lambda item: (item.start, item.end, item.type),
    )

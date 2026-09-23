"""Heuristic instruction detection, not a guarantee of LLM containment."""

import re
import unicodedata

_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    r"\b(?:ignore|forget|disregard)\s+(?:(?:all|the|your)\s+)*"
    r"(?:previous|prior|above)\s+instructions\b",
    r"\b(?:reveal|show|print|expose)\s+(?:me\s+)?"
    r"(?:(?:your|the)\s+)?system\s+prompt\b",
    r"\b(?:show|reveal|print|expose)\s+(?:me\s+)?"
    r"(?:(?:your|the)\s+)?(?:api\s*key|access\s*token|password)\b",
    r"\b(?:игнорируй|забудь|выполни)\s+(?:все\s+)?"
    r"предыдущие\s+инструкции\b",
    r"\b(?:покажи|раскрой)\s+(?:мне\s+)?(?:свой\s+)?"
    r"системный\s+(?:промпт|prompt)\b",
    r"\b(?:покажи|раскрой)\s+(?:мне\s+)?(?:свой\s+)?"
    r"(?:api[\s-]*ключ|ключ\s+api|пароль|токен)\b",
))


def analyze_prompt_injection(text: str) -> dict:
    """Return suspicious matched phrases without executing any instructions.

    Quoted discussion can trigger false positives; unmatched attacks can evade
    patterns. The backend must keep the transcript untrusted in every case.
    """
    if not isinstance(text, str):
        raise TypeError("Transcript must be a string.")
    normalized = unicodedata.normalize("NFKC", text)
    normalized = "".join(char for char in normalized
                         if unicodedata.category(char) != "Cf")
    normalized = " ".join(normalized.split())
    matches = list(dict.fromkeys(
        match.group().lower()
        for pattern in _PATTERNS for match in pattern.finditer(normalized)
    ))
    return {
        "is_suspicious": bool(matches),
        "risk": "HIGH" if matches else "LOW",
        "matches": matches,
    }

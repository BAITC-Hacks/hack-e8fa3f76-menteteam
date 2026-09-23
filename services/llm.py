"""Compatibility facade for the direct Python Gemma adapter."""
from adapters.gemma import LocalGemma, parse_minutes as _extract_json
from application.security_gate import check_transcript


def extract_minutes(transcript: str, model_id: str) -> dict:
    checked = check_transcript(transcript)
    if checked.decision.requires_review:
        return {"summary": "", "tasks": [], "security": checked.decision.model_dump()}
    result = LocalGemma(model_id).extract(checked.text)
    result["security"] = checked.decision.model_dump()
    return result

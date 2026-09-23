"""Compatibility facade for the direct Python Gemma adapter."""
from adapters.gemma import LocalGemma, parse_minutes as _extract_json


def extract_minutes(transcript: str, model_id: str) -> dict:
    return LocalGemma(model_id).extract(transcript)

"""Composition root: the public local processing entry point."""
import os
from datetime import date
from pathlib import Path
from uuid import uuid4

from adapters.gemma import LocalGemma
from adapters.speech import LocalSpeech
from application.process import ProcessMeeting, cache_key
from core.models import MeetingResult
from settings import DATA

PIPELINE_VERSION = "local-4"


def analyze(path: str, title: str, asr_model: str, llm_model: str,
            compute_type: str = "int8_float16", language: str = "auto", hf_token: str | None = None,
            meeting_date: date | None = None, progress=lambda _: None, use_cache: bool = True):
    source = Path(path)
    if source.stat().st_size == 0:
        raise ValueError("Аудиофайл пуст.")
    diarization = os.getenv("DIARIZATION_MODEL", "pyannote/speaker-diarization-community-1")
    settings = dict(asr=asr_model, llm=llm_model, compute=compute_type, language=language,
                    diarization=diarization, date=str(meeting_date), version=PIPELINE_VERSION,
                    device=os.getenv("AI_DEVICE", "cuda"))
    cached = DATA / "cache" / f"{cache_key(source, settings)}.json"
    if use_cache and cached.exists():
        progress("Использую локальный результат предыдущей обработки…")
        result = MeetingResult.model_validate_json(cached.read_text(encoding="utf-8"))
        result.id, result.title, result.source_path = uuid4().hex, title, str(source.resolve())
        return result
    result = ProcessMeeting(LocalSpeech(asr_model, compute_type, language, hf_token, diarization),
                            LocalGemma(llm_model, hf_token)).run(path, title, meeting_date, progress)
    if not result.warnings:
        cached.parent.mkdir(parents=True, exist_ok=True)
        temporary = cached.with_name(f".{uuid4().hex}.tmp")
        temporary.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(cached)
    return result

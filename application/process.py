"""Recording → grounded minutes. All IO adapters are injected."""
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Callable

from application.ports import MinutesExtractor, Transcriber
from application.security_gate import ERROR_MESSAGE, REVIEW_MESSAGE, check_transcript
from core.grounding import build_result
from core.models import MeetingResult


def cache_key(path: Path, settings: dict) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    digest.update(json.dumps(settings, sort_keys=True, ensure_ascii=False).encode())
    return digest.hexdigest()


class ProcessMeeting:
    def __init__(self, transcriber: Transcriber, extractor: MinutesExtractor):
        self.transcriber = transcriber
        self.extractor = extractor

    def run(self, path: str, title: str, meeting_date: date | None = None,
            progress: Callable[[str], None] = lambda _: None) -> MeetingResult:
        if Path(path).stat().st_size == 0:
            raise ValueError("Аудиофайл пуст.")
        progress("Whisper распознаёт речь; pyannote различает спикеров…")
        segments, language, warning = self.transcriber.transcribe(path)
        if not segments:
            raise ValueError("В записи не обнаружена речь.")
        progress("Проверяю безопасность стенограммы…")
        checked = check_transcript(" ".join(s.text for s in segments), segments)
        if checked.decision.requires_review:
            message = (ERROR_MESSAGE if checked.decision.status == "security_error"
                       else REVIEW_MESSAGE)
            return MeetingResult(
                title=title, summary="", meeting_date=meeting_date,
                language=language, transcript=checked.segments,
                security=checked.decision, source_path=str(Path(path).resolve()),
                warnings=[message, *([warning] if warning else [])],
            )
        progress("Gemma составляет протокол локально…")
        data = self.extractor.extract(checked.text, segments=checked.segments)
        progress("Проверяю цитаты, ответственных и сроки…")
        result = build_result(title, checked.segments, language, data, meeting_date)
        result.security = checked.decision
        result.source_path = str(Path(path).resolve())
        if warning:
            result.warnings.append(warning)
        return result

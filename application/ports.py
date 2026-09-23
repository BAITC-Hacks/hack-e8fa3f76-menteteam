from pathlib import Path
from typing import Protocol

from core.models import MeetingResult, Segment


class Transcriber(Protocol):
    def transcribe(self, path: str) -> tuple[list[Segment], str, str | None]: ...


class MinutesExtractor(Protocol):
    def extract(self, transcript: str, *, segments: list[Segment] | None = None) -> dict: ...


class MeetingRepository(Protocol):
    def save(self, result: MeetingResult) -> None: ...
    def get(self, meeting_id: str) -> MeetingResult | None: ...
    def list(self) -> list[MeetingResult]: ...

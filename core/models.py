from datetime import date
from typing import Literal
from uuid import uuid4
from pydantic import BaseModel, Field

class Segment(BaseModel):
    id: str
    speaker: str = "Спикер"
    start: float = 0
    end: float = 0
    text: str

class Task(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    title: str
    owner: str = "Ответственный не определён"
    deadline: str = "Срок не определён"
    evidence: str
    timestamp: float = 0
    due_date: date | None = None
    status: Literal["В работе", "Выполнено"] = "В работе"
    speaker_id: str = ""
    owner_speaker_id: str = ""
    email: str = ""
    approved: bool = False
    urgency: Literal["Обычная", "Высокая", "Низкая"] = "Обычная"
    area: str = "Общее"

class MeetingResult(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    title: str
    summary: str
    meeting_date: date | None = None
    participants: dict[str, str] = Field(default_factory=dict)
    source_path: str = ""
    warnings: list[str] = Field(default_factory=list)
    language: str = "unknown"
    decisions: list[str] = Field(default_factory=list)
    tasks: list[Task] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    transcript: list[Segment] = Field(default_factory=list)

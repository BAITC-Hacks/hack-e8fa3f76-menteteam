from datetime import date
from typing import Literal
from pydantic import BaseModel, Field

class Segment(BaseModel):
    id: str
    speaker: str = "Спикер"
    start: float = 0
    end: float = 0
    text: str

class Task(BaseModel):
    title: str
    owner: str = "Ответственный не определён"
    deadline: str = "Срок не определён"
    evidence: str
    timestamp: float = 0
    due_date: date | None = None
    status: Literal["В работе", "Выполнено"] = "В работе"

class MeetingResult(BaseModel):
    title: str
    summary: str
    language: str = "unknown"
    decisions: list[str] = Field(default_factory=list)
    tasks: list[Task] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    transcript: list[Segment] = Field(default_factory=list)

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

class MeetingTopic(BaseModel):
    title: str
    summary: str = ""
    start_segment_id: str

class DirectionReport(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    direction: str
    speaker_id: str = ""
    indicator: str = ""
    problem: str = ""
    evidence: str = ""
    review_required: bool = False

class MeetingResult(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    title: str
    summary: str
    meeting_date: date | None = None
    organization: str = ""
    participants: dict[str, str] = Field(default_factory=dict)
    participant_roles: dict[str, str] = Field(default_factory=dict)
    topics: list[MeetingTopic] = Field(default_factory=list)
    reports: list[DirectionReport] = Field(default_factory=list)
    source_path: str = ""
    warnings: list[str] = Field(default_factory=list)
    language: str = "unknown"
    decisions: list[str] = Field(default_factory=list)
    tasks: list[Task] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    transcript: list[Segment] = Field(default_factory=list)

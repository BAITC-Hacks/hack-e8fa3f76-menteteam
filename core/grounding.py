"""Evidence and identity rules; no model, UI or persistence dependencies."""
import re
from datetime import date, timedelta

from core.models import MeetingResult, Segment, Task

UNKNOWN_OWNER = "Ответственный не определён"
UNKNOWN_DEADLINE = "Срок не определён"


def normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def contains_phrase(text: str, phrase: str) -> bool:
    return bool(re.search(r"(?<!\w)" + re.escape(normalize(phrase)) + r"(?!\w)", normalize(text)))


def resolve_date(deadline: str, meeting_date: date | None) -> date | None:
    """Only explicit calendar dates or unambiguous relative days are automatic."""
    for pattern, order in [(r"\b(\d{4})-(\d{2})-(\d{2})\b", (0, 1, 2)),
                           (r"\b(\d{2})\.(\d{2})\.(\d{4})\b", (2, 1, 0))]:
        match = re.search(pattern, deadline)
        if match:
            values = match.groups()
            try:
                return date(*(int(values[i]) for i in order))
            except ValueError:
                return None
    if meeting_date:
        for word, days in [("послезавтра", 2), ("бүрсігүні", 2), ("завтра", 1),
                           ("ертең", 1), ("сегодня", 0), ("бүгін", 0)]:
            if re.search(r"\b" + word + r"\b", normalize(deadline)):
                return meeting_date + timedelta(days=days)
    return None


def build_result(title: str, segments: list[Segment], language: str, data: dict,
                 meeting_date: date | None = None) -> MeetingResult:
    text = " ".join(normalize(s.text) for s in segments)
    questions = list(data.get("questions", []))
    tasks, seen = [], set()
    offsets, pos = [], 0
    for segment in segments:
        offsets.append((pos, pos + len(normalize(segment.text)), segment))
        pos += len(normalize(segment.text)) + 1
    for raw in data.get("tasks", []):
        quote = str(raw.get("evidence") or "").strip()
        quote_norm = normalize(quote)
        task_title = str(raw.get("title") or "Поручение").strip()
        offset = text.find(quote_norm) if quote_norm else -1
        if offset < 0:
            questions.append(f"Поручение «{task_title}» не показано: цитата не найдена в речи.")
            continue
        cited = next((s for start, end, s in offsets if start <= offset < end), segments[0])
        owner = str(raw.get("owner") or UNKNOWN_OWNER).strip()
        owner_speaker = ""
        quoted_speakers = {s.speaker for start, end, s in offsets
                           if start < offset + len(quote_norm) and end > offset}
        if (owner.startswith("SPEAKER_") and quoted_speakers == {owner}
                and re.search(r"\b(я|мен)\b", quote_norm)):
            owner_speaker = cited.speaker
        elif owner.startswith("SPEAKER_") or not contains_phrase(quote_norm, owner):
            owner = UNKNOWN_OWNER
        deadline = str(raw.get("deadline") or UNKNOWN_DEADLINE).strip()
        if not contains_phrase(quote_norm, deadline):
            deadline = UNKNOWN_DEADLINE
        due_date = resolve_date(deadline, meeting_date)
        if owner == UNKNOWN_OWNER:
            questions.append(f"Кто отвечает за поручение «{task_title}»?")
        if due_date is None:
            questions.append(f"Уточните календарный срок поручения «{task_title}»: {deadline}.")
        signature = (normalize(task_title), normalize(owner), quote_norm)
        if signature in seen:
            continue
        seen.add(signature)
        urgency = raw.get("urgency", "Обычная")
        tasks.append(Task(title=task_title, owner=owner, deadline=deadline,
                          evidence=quote, timestamp=cited.start, speaker_id=cited.speaker,
                          owner_speaker_id=owner_speaker, due_date=due_date,
                          urgency=urgency if urgency in {"Высокая", "Обычная", "Низкая"} else "Обычная",
                          area=str(raw.get("area") or "Общее")))
    return MeetingResult(title=title, meeting_date=meeting_date, summary=data.get("summary", ""),
                         language=language, decisions=data.get("decisions", []), tasks=tasks,
                         questions=list(dict.fromkeys(questions)), transcript=segments)


def rename_participants(meeting: MeetingResult, names: dict[str, str]) -> MeetingResult:
    result = meeting.model_copy(deep=True)
    result.participants = {k: v.strip() for k, v in names.items() if v.strip()}
    for task in result.tasks:
        key = task.owner_speaker_id or (task.owner if task.owner.startswith("SPEAKER_") else "")
        if key:
            task.owner_speaker_id = key
            new_owner = result.participants.get(key, key)
            if task.owner != new_owner:
                task.owner = new_owner
                task.approved = False
    return result

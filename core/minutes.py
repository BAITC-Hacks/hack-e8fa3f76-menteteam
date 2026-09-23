"""Shared document structure for the screen, DOCX, PDF and plain text."""
from dataclasses import dataclass, field

from core.models import MeetingResult, Task


@dataclass
class MinutesBlock:
    kind: str
    text: str = ""
    rows: list[list[str]] = field(default_factory=list)
    column_widths: list[float] = field(default_factory=list)


def deadline_text(task: Task) -> str:
    if not task.due_date:
        return "Не указан" if task.deadline in {"", "Срок не определён"} else task.deadline
    calendar_date = task.due_date.strftime("%d.%m.%Y")
    if task.deadline in {"", "Срок не определён", calendar_date, task.due_date.isoformat()}:
        return calendar_date
    return f"{calendar_date} ({task.deadline})"


def minutes_blocks(meeting: MeetingResult, include_details: bool = False) -> list[MinutesBlock]:
    blocks = [MinutesBlock("title", "Протокол совещания")]
    if meeting.organization:
        blocks.append(MinutesBlock("paragraph", meeting.organization))
    blocks.append(MinutesBlock("paragraph", f"Тема: {meeting.title}"))
    if meeting.meeting_date:
        blocks.append(MinutesBlock("paragraph", f"Дата: {meeting.meeting_date:%d.%m.%Y}"))

    blocks.append(MinutesBlock("heading", "Текст совещания"))
    if not meeting.transcript:
        blocks.append(MinutesBlock("paragraph", "Стенограмма отсутствует."))
    previous_speaker, introduced = None, set()
    for segment in meeting.transcript:
        if segment.speaker == previous_speaker:
            blocks[-1].text += " " + segment.text
            continue
        speaker = meeting.participants.get(segment.speaker, segment.speaker)
        role = meeting.participant_roles.get(segment.speaker, "") if segment.speaker not in introduced else ""
        blocks.append(MinutesBlock("speaker", f"{speaker} ({role})" if role else speaker))
        blocks.append(MinutesBlock("paragraph", segment.text))
        previous_speaker = segment.speaker
        introduced.add(segment.speaker)

    blocks.append(MinutesBlock("heading", "Саммари по ключевым пунктам"))
    blocks.append(MinutesBlock("paragraph", meeting.summary or "Саммари не заполнено."))
    if meeting.reports:
        rows = [["Направление / доклад", "Показатель", "Проблема"]]
        for report in meeting.reports:
            name = meeting.participants.get(report.speaker_id, report.speaker_id)
            direction = f"{report.direction} ({name})" if name else report.direction
            rows.append([direction, report.indicator or "Не указан", report.problem or "Не указана"])
        blocks.append(MinutesBlock("table", rows=rows, column_widths=[0.36, 0.23, 0.41]))
    else:
        blocks.append(MinutesBlock("paragraph", "Показатели и проблемы по направлениям не заполнены."))

    blocks.append(MinutesBlock("heading", "Поручения"))
    if meeting.tasks:
        rows = [["Поручение", "Ответственный", "Срок"]]
        rows.extend([[task.title, task.owner, deadline_text(task)] for task in meeting.tasks])
        blocks.append(MinutesBlock("table", rows=rows, column_widths=[0.50, 0.29, 0.21]))
    else:
        blocks.append(MinutesBlock("paragraph", "Поручения не зафиксированы."))
    if meeting.warnings:
        blocks.append(MinutesBlock("heading", "Примечания"))
        blocks.extend(MinutesBlock("paragraph", warning) for warning in meeting.warnings)
    if include_details:
        blocks.append(MinutesBlock("heading", "Приложение. Проверка и контроль поручений"))
        if meeting.decisions:
            blocks.append(MinutesBlock("subheading", "Принятые решения"))
            blocks.extend(MinutesBlock("paragraph", f"{index}. {decision}")
                          for index, decision in enumerate(meeting.decisions, 1))
        if meeting.tasks:
            rows = [["Поручение", "Ответственный", "Срок", "Дата", "Статус"]]
            rows.extend([[task.title, task.owner, task.deadline,
                          task.due_date.isoformat() if task.due_date else "—", task.status] for task in meeting.tasks])
            blocks.append(MinutesBlock("table", rows=rows))
        for task in meeting.tasks:
            blocks.append(MinutesBlock("paragraph", f"{task.title} · {task.urgency} · {task.area} · "
                                       f"{'Проверено' if task.approved else 'Черновик'}"))
            blocks.append(MinutesBlock("paragraph", f"Цитата [{task.timestamp:.1f} сек]: {task.evidence}"))
        if meeting.questions:
            blocks.append(MinutesBlock("subheading", "Нужно уточнить"))
            blocks.extend(MinutesBlock("paragraph", question) for question in meeting.questions)
        blocks.append(MinutesBlock("subheading", "Стенограмма с таймкодами"))
        for segment in meeting.transcript:
            speaker = meeting.participants.get(segment.speaker, segment.speaker)
            blocks.append(MinutesBlock("paragraph", f"[{segment.start:.1f}–{segment.end:.1f}] {speaker}: {segment.text}"))
    return blocks

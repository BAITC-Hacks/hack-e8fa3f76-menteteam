"""Shared document structure for the screen, DOCX, PDF and plain text."""
from dataclasses import dataclass, field

from core.models import MeetingResult, MeetingTopic, Task


@dataclass
class MinutesBlock:
    kind: str
    text: str = ""
    rows: list[list[str]] = field(default_factory=list)


def ordered_topics(meeting: MeetingResult) -> list[MeetingTopic]:
    """Always cover the transcript once, including older meetings without topics."""
    positions = {segment.id: index for index, segment in enumerate(meeting.transcript)}
    unique = {}
    for topic in meeting.topics:
        if topic.start_segment_id in positions:
            unique.setdefault(topic.start_segment_id, topic)
    topics = sorted(unique.values(), key=lambda topic: positions[topic.start_segment_id])
    if not topics:
        return [MeetingTopic(title=meeting.title, summary=meeting.summary,
                             start_segment_id=meeting.transcript[0].id if meeting.transcript else "")]
    if positions[topics[0].start_segment_id] > 0:
        topics.insert(0, MeetingTopic(title="Вступление", start_segment_id=meeting.transcript[0].id))
    return topics


def deadline_text(task: Task) -> str:
    if not task.due_date:
        return task.deadline
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

    topics = ordered_topics(meeting)
    positions = {segment.id: index for index, segment in enumerate(meeting.transcript)}
    starts = [positions.get(topic.start_segment_id, 0) for topic in topics]
    groups = [meeting.transcript[start:starts[index + 1] if index + 1 < len(starts) else None]
              for index, start in enumerate(starts)]
    task_groups = [[] for _ in topics]
    for task in meeting.tasks:
        # Use the grounded quote's position, independently of an AI area label.
        index = max((i for i, group in enumerate(groups) if group and group[0].start <= task.timestamp), default=0)
        task_groups[index].append(task)

    for index, (topic, segments) in enumerate(zip(topics, groups), 1):
        blocks.append(MinutesBlock("heading", f"Часть {index}. {topic.title}"))
        if not segments:
            blocks.append(MinutesBlock("paragraph", "Стенограмма отсутствует."))
        previous_speaker = None
        for segment in segments:
            if segment.speaker == previous_speaker:
                blocks[-1].text += " " + segment.text
                continue
            speaker = meeting.participants.get(segment.speaker, segment.speaker)
            role = meeting.participant_roles.get(segment.speaker, "")
            blocks.append(MinutesBlock("speaker", f"{speaker} ({role})" if role else speaker))
            blocks.append(MinutesBlock("paragraph", segment.text))
            previous_speaker = segment.speaker

    blocks.append(MinutesBlock("heading", "Саммари по ключевым пунктам"))
    if len(topics) > 1 and meeting.summary:
        blocks.append(MinutesBlock("paragraph", meeting.summary))
    for index, (topic, tasks) in enumerate(zip(topics, task_groups), 1):
        blocks.append(MinutesBlock("subheading", f"Тема {index} — {topic.title}"))
        summary = meeting.summary if len(topics) == 1 else topic.summary
        blocks.append(MinutesBlock("paragraph", summary or "Саммари темы не заполнено."))
        if tasks:
            rows = [["Поручение", "Ответственный", "Срок"]]
            rows.extend([[task.title, task.owner, deadline_text(task)] for task in tasks])
            blocks.append(MinutesBlock("table", rows=rows))
        else:
            blocks.append(MinutesBlock("paragraph", "Поручения по этой теме не зафиксированы."))

    if meeting.decisions:
        blocks.append(MinutesBlock("heading", "Принятые решения"))
        blocks.extend(MinutesBlock("paragraph", f"{index}. {decision}")
                      for index, decision in enumerate(meeting.decisions, 1))
    if meeting.warnings:
        blocks.append(MinutesBlock("heading", "Примечания"))
        blocks.extend(MinutesBlock("paragraph", warning) for warning in meeting.warnings)
    if include_details:
        blocks.append(MinutesBlock("heading", "Приложение. Проверка и контроль поручений"))
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

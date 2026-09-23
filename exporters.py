"""Portable minutes exports; no model or storage dependencies."""
import re
from datetime import datetime, timedelta, timezone
from html import escape
from io import BytesIO
from pathlib import Path

from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from core.models import MeetingResult


def _content(result: MeetingResult):
    rows = [["Поручение", "Ответственный", "Срок", "Дата", "Статус"]]
    rows.extend([[t.title, t.owner, t.deadline,
                  t.due_date.isoformat() if t.due_date else "—", t.status] for t in result.tasks])
    return rows


def export_docx(result: MeetingResult) -> bytes:
    doc = Document()
    doc.add_heading(f"Протокол: {result.title}", 0)
    doc.add_paragraph(f"Дата: {result.meeting_date or 'не указана'} · Язык: {result.language}")
    doc.add_heading("Саммари", level=1)
    doc.add_paragraph(result.summary or "Не сформировано")
    doc.add_heading("Решения", level=1)
    for item in result.decisions:
        doc.add_paragraph(item, style="List Bullet")
    doc.add_heading("Поручения", level=1)
    table = doc.add_table(rows=1, cols=5)
    table.style = "Light Shading Accent 1"
    for cell, value in zip(table.rows[0].cells, _content(result)[0]):
        cell.text = value
    for values in _content(result)[1:]:
        for cell, value in zip(table.add_row().cells, values):
            cell.text = value
    for task in result.tasks:
        doc.add_paragraph(f"{task.title} · {task.urgency} · {task.area} · "
                          f"{'Проверено' if task.approved else 'Черновик'}")
        doc.add_paragraph(f"Цитата [{task.timestamp:.1f} сек]: {task.evidence}")
    doc.add_heading("Транскрипт", level=1)
    for segment in result.transcript:
        speaker = result.participants.get(segment.speaker, segment.speaker)
        doc.add_paragraph(f"[{segment.start:.1f}–{segment.end:.1f}] {speaker}: {segment.text}")
    if result.questions or result.warnings:
        doc.add_heading("Нужно уточнить", level=1)
        for question in result.questions + result.warnings:
            doc.add_paragraph(question, style="List Bullet")
    stream = BytesIO()
    doc.save(stream)
    return stream.getvalue()


def export_pdf(result: MeetingResult) -> bytes:
    candidates = [Path(__file__).parent / "assets" / "DejaVuSans.ttf",
                  Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
                  Path("/usr/share/fonts/TTF/DejaVuSans.ttf")]
    font = next((path for path in candidates if path.exists()), None)
    if font is None:
        raise RuntimeError("Для PDF установите шрифт DejaVu Sans или поместите его в assets/DejaVuSans.ttf.")
    if "AlemUnicode" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("AlemUnicode", str(font)))
    styles = getSampleStyleSheet()
    for name in ("Normal", "Title", "Heading2"):
        styles[name].fontName = "AlemUnicode"
    styles["Normal"].leading = 15
    story = []

    def add(text: str, style="Normal"):
        story.append(Paragraph(escape(text).replace("\n", "<br/>"), styles[style]))
        story.append(Spacer(1, 6))

    add(f"Протокол: {result.title}", "Title")
    add(f"Дата: {result.meeting_date or 'не указана'} · Язык: {result.language}")
    add("Саммари", "Heading2")
    add(result.summary or "Не сформировано")
    add("Решения", "Heading2")
    for decision in result.decisions:
        add(f"• {decision}")
    add("Поручения", "Heading2")
    for index, task in enumerate(result.tasks, 1):
        add(f"{index}. {task.title}")
        add(f"Ответственный: {task.owner} · Срок: {task.deadline} · Дата: {task.due_date or '—'}")
        add(f"{task.status} · {task.urgency} · {task.area} · {'Проверено' if task.approved else 'Черновик'}")
        add(f"Цитата [{task.timestamp:.1f} сек]: {task.evidence}")
    add("Транскрипт", "Heading2")
    for segment in result.transcript:
        speaker = result.participants.get(segment.speaker, segment.speaker)
        add(f"[{segment.start:.1f}–{segment.end:.1f}] {speaker}: {segment.text}")
    if result.questions or result.warnings:
        add("Нужно уточнить", "Heading2")
        for question in result.questions + result.warnings:
            add(question)
    stream = BytesIO()
    SimpleDocTemplate(stream, pagesize=A4, title=result.title).build(story)
    return stream.getvalue()


def anonymize(result: MeetingResult) -> MeetingResult:
    names = list(dict.fromkeys([*result.participants.values(), *[task.owner for task in result.tasks
                                  if task.owner != "Ответственный не определён"]]))
    substitutions = {name: f"Участник {i}" for i, name in enumerate(names, 1) if name}

    def clean(value):
        if isinstance(value, str):
            for name in sorted(substitutions, key=len, reverse=True):
                value = re.sub(re.escape(name), substitutions[name], value, flags=re.IGNORECASE)
            value = re.sub(r"[^\s@]+@[^\s@]+\.[^\s@]+", "[email скрыт]", value)
            value = re.sub(r"(?<!\w)\+?\d[\d ()-]{8,}\d(?!\w)", "[телефон скрыт]", value)
            return value
        if isinstance(value, list):
            return [clean(item) for item in value]
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items()}
        return value

    # Never redact structural ISO dates or identifiers with the phone-number rule.
    copy = result.model_copy(deep=True)
    fields = ("title", "summary", "decisions", "questions", "warnings", "participants")
    for field in fields:
        setattr(copy, field, clean(getattr(copy, field)))
    for segment in copy.transcript:
        segment.text = clean(segment.text)
    for task in copy.tasks:
        for field in ("title", "owner", "deadline", "evidence", "area"):
            setattr(task, field, clean(getattr(task, field)))
        task.email = ""
    copy.source_path = ""
    return copy


def export_json(result: MeetingResult) -> bytes:
    public = result.model_copy(update={"source_path": ""})
    return public.model_dump_json(indent=2).encode("utf-8")


def export_ics(result: MeetingResult) -> bytes:
    def escaped(text):
        return str(text).replace("\\", "\\\\").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,").replace("\r", "")

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Alem Minutes//RU", "CALSCALE:GREGORIAN"]
    for task in result.tasks:
        if not task.due_date:
            continue
        lines += ["BEGIN:VEVENT", f"UID:{result.id}-{task.id}@alem.local",
                  f"DTSTAMP:{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}",
                  f"DTSTART;VALUE=DATE:{task.due_date:%Y%m%d}",
                  f"DTEND;VALUE=DATE:{task.due_date + timedelta(days=1):%Y%m%d}",
                  f"SUMMARY:{escaped(task.title)}", f"DESCRIPTION:{escaped(task.owner + ': ' + task.evidence)}",
                  "END:VEVENT"]
    lines.append("END:VCALENDAR")
    folded = []
    for line in lines:
        chunk = ""
        for char in line:
            if len((chunk + char).encode("utf-8")) > 75:
                folded.append(chunk)
                chunk = " "
            chunk += char
        folded.append(chunk)
    return ("\r\n".join(folded) + "\r\n").encode("utf-8")

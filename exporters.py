"""Portable minutes exports; no model or storage dependencies."""
import re
from datetime import datetime, timedelta, timezone
from html import escape
from io import BytesIO
from pathlib import Path

from docx import Document
from docx.shared import Cm, Pt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

from core.minutes import minutes_blocks
from core.models import MeetingResult


def export_docx(result: MeetingResult, include_details: bool = True) -> bytes:
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.left_margin = section.right_margin = Cm(2)
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)
    for block in minutes_blocks(result, include_details):
        if block.kind in {"title", "heading", "subheading"}:
            doc.add_heading(block.text, {"title": 0, "heading": 1, "subheading": 2}[block.kind])
        elif block.kind == "table":
            table = doc.add_table(rows=0, cols=len(block.rows[0]))
            table.style = "Light Shading Accent 1"
            widths = [17 * fraction for fraction in block.column_widths] if block.column_widths else [5.5, 3.5, 3, 2.5, 2.5]
            table.autofit = False
            for column, width in zip(table.columns, widths):
                column.width = Cm(width)
            for index, values in enumerate(block.rows):
                for cell, value, width in zip(table.add_row().cells, values, widths):
                    cell.width = Cm(width)
                    cell.text = value
                    if index == 0:
                        for run in cell.paragraphs[0].runs:
                            run.bold = True
            # Repeat table headings if a list of assignments spans multiple pages.
            from docx.oxml import OxmlElement
            table.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
            doc.add_paragraph()
        elif block.kind == "speaker":
            paragraph = doc.add_paragraph()
            paragraph.paragraph_format.keep_with_next = True
            paragraph.add_run(block.text).bold = True
        else:
            doc.add_paragraph(block.text)
    stream = BytesIO()
    doc.save(stream)
    return stream.getvalue()


def export_pdf(result: MeetingResult, include_details: bool = True) -> bytes:
    candidates = [Path(__file__).parent / "assets" / "DejaVuSans.ttf",
                  Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
                  Path("/usr/share/fonts/TTF/DejaVuSans.ttf")]
    font = next((path for path in candidates if path.exists()), None)
    if font is None:
        raise RuntimeError("Для PDF установите шрифт DejaVu Sans или поместите его в assets/DejaVuSans.ttf.")
    if "AlemUnicode" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("AlemUnicode", str(font)))
    styles = getSampleStyleSheet()
    for name in ("Normal", "Title", "Heading2", "Heading3"):
        styles[name].fontName = "AlemUnicode"
    styles["Normal"].fontSize = 10
    styles["Normal"].leading = 15
    story = []
    stream = BytesIO()
    document = SimpleDocTemplate(stream, pagesize=A4, title=result.title,
                                 leftMargin=48, rightMargin=48, topMargin=48, bottomMargin=48)

    def paragraph(text, style="Normal"):
        return Paragraph(escape(text).replace("\n", "<br/>"), styles[style])

    for block in minutes_blocks(result, include_details):
        if block.kind == "table":
            fractions = block.column_widths or [0.31, 0.20, 0.19, 0.15, 0.15]
            table = LongTable([[paragraph(cell) for cell in row] for row in block.rows],
                              colWidths=[document.width * fraction for fraction in fractions],
                              repeatRows=1, splitByRow=1, splitInRow=1, hAlign="LEFT")
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8edf5")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c5ccd8")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]))
            story.append(table)
        else:
            style = {"title": "Title", "heading": "Heading2", "subheading": "Heading3", "speaker": "Heading3"}.get(block.kind, "Normal")
            story.append(paragraph(block.text, style))
        story.append(Spacer(1, 6))
    document.build(story)
    return stream.getvalue()


def export_txt(result: MeetingResult, include_details: bool = False) -> bytes:
    parts = []
    for block in minutes_blocks(result, include_details):
        if block.kind == "table":
            parts.append("\n".join("\t".join(cell.replace("\n", " ").replace("\t", " ") for cell in row)
                                   for row in block.rows))
        else:
            parts.append(block.text)
    return ("\n\n".join(parts) + "\n").encode("utf-8")


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
    fields = ("title", "summary", "organization", "decisions", "questions", "warnings", "participants", "participant_roles")
    for field in fields:
        setattr(copy, field, clean(getattr(copy, field)))
    for segment in copy.transcript:
        segment.text = clean(segment.text)
    for topic in copy.topics:
        topic.title, topic.summary = clean(topic.title), clean(topic.summary)
    for report in copy.reports:
        for field in ("direction", "indicator", "problem", "evidence"):
            setattr(report, field, clean(getattr(report, field)))
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

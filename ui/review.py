from datetime import date
from pathlib import Path
import re

import streamlit as st

from core.grounding import UNKNOWN_OWNER, rename_participants
from core.minutes import minutes_blocks, ordered_topics
from core.models import MeetingTopic
from exporters import anonymize, export_docx, export_ics, export_json, export_pdf, export_txt
from services.notifications import valid_email


def _render_editor(meeting, repo):
    st.subheader(meeting.title)
    st.caption(f"{meeting.meeting_date or 'Дата не указана'} · {meeting.language} · ID {meeting.id[:8]}")
    for warning in meeting.warnings:
        st.warning(warning)
    speakers = list(dict.fromkeys(s.speaker for s in meeting.transcript if s.speaker != "Спикер не определён"))
    with st.expander("Участники и голоса", expanded=bool(speakers) and not meeting.participants):
        st.caption("Прослушайте реплику и подтвердите имя. Автор реплики и ответственный за поручение могут различаться.")
        with st.form(f"participants-{meeting.id}"):
            names, roles = {}, {}
            for speaker in speakers:
                segment = next(s for s in meeting.transcript if s.speaker == speaker)
                names[speaker] = st.text_input(speaker, value=meeting.participants.get(speaker, ""), key=f"name-{meeting.id}-{speaker}")
                roles[speaker] = st.text_input("Должность / роль (необязательно)", value=meeting.participant_roles.get(speaker, ""), key=f"role-{meeting.id}-{speaker}")
                st.caption(f"[{segment.start:.1f} с] {segment.text[:160]}")
                if meeting.source_path and Path(meeting.source_path).is_file():
                    st.audio(meeting.source_path, start_time=int(segment.start), end_time=max(int(segment.start) + 1, int(segment.end) + 1))
            if st.form_submit_button("Подтвердить имена"):
                updated = rename_participants(meeting, names)
                updated.participant_roles = {key: value.strip() for key, value in roles.items() if value.strip()}
                repo.save(updated)
                st.rerun()
    revision_key = f"protocol-revision-{meeting.id}"
    revision = st.session_state.get(revision_key, 0)
    topics = ordered_topics(meeting)
    with st.form(f"summary-{meeting.id}-{revision}"):
        title = st.text_input("Тема совещания", meeting.title)
        organization = st.text_input("Организация", meeting.organization)
        summary = st.text_area("Саммари", meeting.summary, height=130)
        decisions = st.text_area("Решения — по одному на строку", "\n".join(meeting.decisions))
        edited_topics = []
        segment_ids = [segment.id for segment in meeting.transcript]
        segment_labels = {segment.id: f"[{segment.start:.0f} с] {segment.text[:90]}" for segment in meeting.transcript}
        with st.expander("Темы: заголовки, саммари и границы стенограммы"):
            st.caption("Каждая тема продолжается до начала следующей. Поручения распределяются по месту цитаты в записи.")
            for index, topic in enumerate(topics, 1):
                topic_title = st.text_input(f"Название темы {index}", topic.title)
                if len(topics) == 1:
                    topic_summary = summary
                    st.caption("Для одной темы используется поле «Саммари» выше.")
                else:
                    topic_summary = st.text_area(f"Саммари темы {index}", topic.summary)
                start = topic.start_segment_id
                if segment_ids:
                    start = st.selectbox(f"Первая реплика темы {index}", segment_ids,
                                         index=segment_ids.index(start), format_func=segment_labels.get)
                remove = st.checkbox(f"Убрать тему {index}", value=False)
                if not remove:
                    edited_topics.append(MeetingTopic(title=topic_title.strip(), summary=topic_summary.strip(), start_segment_id=start))
            if segment_ids:
                st.markdown("**Добавить тему**")
                new_title = st.text_input("Название новой темы", value="")
                new_start = st.selectbox("Первая реплика новой темы", segment_ids, format_func=segment_labels.get)
                new_summary = st.text_area("Саммари новой темы", value="")
                if new_title.strip():
                    edited_topics.append(MeetingTopic(title=new_title.strip(), summary=new_summary.strip(), start_segment_id=new_start))
        if st.form_submit_button("Сохранить протокол"):
            starts = [topic.start_segment_id for topic in edited_topics]
            if not title.strip() or any(not topic.title for topic in edited_topics):
                st.error("Укажите тему совещания и названия разделов.")
            elif len(starts) != len(set(starts)):
                st.error("Две темы не могут начинаться с одной реплики. Выберите разные границы.")
            else:
                if len(edited_topics) == 1:
                    edited_topics[0].summary = summary
                meeting.title, meeting.organization = title.strip(), organization.strip()
                meeting.summary = summary
                meeting.topics = edited_topics
                meeting.decisions = [line.strip() for line in decisions.splitlines() if line.strip()]
                repo.save(meeting)
                # A fresh form resets successful additions; invalid submissions
                # retain their widget values under the unchanged form revision.
                st.session_state[revision_key] = revision + 1
                st.rerun()
    st.subheader("Проверка поручений")
    st.caption("Цитаты привязаны к распознанной речи. Перед подтверждением проверьте ответственного, дату и адрес получателя.")
    for task in meeting.tasks:
        with st.container(border=True):
            speaker = meeting.participants.get(task.speaker_id, task.speaker_id)
            st.caption(f"Реплика: {speaker or 'спикер не определён'} · {task.timestamp:.1f} с")
            st.write(f"«{task.evidence}»")
            if meeting.source_path and Path(meeting.source_path).is_file():
                st.audio(meeting.source_path, start_time=max(0, int(task.timestamp) - 2))
            with st.form(f"task-{meeting.id}-{task.id}"):
                title = st.text_input("Поручение", task.title)
                left, right = st.columns(2)
                owner = left.text_input("Ответственный", task.owner)
                email = right.text_input("Email для уведомлений", task.email)
                deadline = left.text_input("Исходный срок", task.deadline)
                due = right.date_input("Подтверждённая дата срока", value=task.due_date, format="YYYY-MM-DD")
                status = left.selectbox("Статус", ["В работе", "Выполнено"], index=int(task.status == "Выполнено"))
                urgency = right.selectbox("Срочность", ["Обычная", "Высокая", "Низкая"], index=["Обычная", "Высокая", "Низкая"].index(task.urgency))
                area = st.text_input("Направление", task.area)
                approved = st.checkbox("Проверено: поручение и получатель подтверждены; разрешаю уведомления настроенным worker", value=task.approved)
                if st.form_submit_button("Сохранить поручение"):
                    if not title.strip() or not owner.strip():
                        st.error("Укажите поручение и ответственного или оставьте «Ответственный не определён».")
                    elif email and not valid_email(email.strip()):
                        st.error("Проверьте email получателя.")
                    elif approved and (owner == UNKNOWN_OWNER or owner.startswith("SPEAKER_")):
                        st.error("Перед подтверждением укажите имя или роль ответственного.")
                    else:
                        if task.owner != owner.strip():
                            task.owner_speaker_id = ""
                        task.title, task.owner, task.email = title.strip(), owner.strip(), email.strip()
                        task.deadline, task.due_date, task.status = deadline, due, status
                        task.urgency, task.area, task.approved = urgency, area, approved
                        repo.save(meeting)
                        st.rerun()
            if task.status == "В работе" and task.due_date and task.due_date < date.today():
                st.error(f"Просрочено: {(date.today() - task.due_date).days} дн.")
    if not meeting.tasks:
        st.info("Поручения с подтверждёнными цитатами не обнаружены.")
    with st.expander("Вопросы для проверки"):
        for question in meeting.questions:
            st.write(f"• {question}")
        st.caption("Это вопросы, возникшие при извлечении. Исправления сохраняются в карточках поручений.")
    with st.expander(f"Транскрипт · {len(meeting.transcript)} реплик"):
        query = st.text_input("Найти в транскрипте", key=f"search-{meeting.id}")
        for segment in meeting.transcript:
            if query.casefold() in segment.text.casefold():
                speaker = meeting.participants.get(segment.speaker, segment.speaker)
                st.write(f"[{segment.start:.1f}–{segment.end:.1f}] {speaker}: {segment.text}")


def _render_document(meeting, include_details):
    def literal(text):
        return re.sub(r"([\\`*_{}\[\]<>()#+!|>~])", r"\\\1", text)

    for block in minutes_blocks(meeting, include_details):
        if block.kind == "title":
            st.subheader(block.text)
        elif block.kind in {"heading", "subheading"}:
            st.markdown(f"### {literal(block.text)}")
        elif block.kind == "speaker":
            st.markdown(f"**{literal(block.text)}**")
        elif block.kind == "table":
            st.table([dict(zip(block.rows[0], row)) for row in block.rows[1:]])
        else:
            st.markdown(literal(block.text))


def render_review(meeting, repo):
    include_details = st.checkbox("Включить приложение: цитаты, таймкоды и статусы поручений", key=f"details-{meeting.id}")
    redacted = st.checkbox("Обезличенная копия для демонстрации", key=f"redact-{meeting.id}")
    output = anonymize(meeting) if redacted else meeting
    if redacted:
        st.caption("Подтверждённые имена и контакты заменены. Перед публикацией проверьте свободный текст на оставшиеся персональные данные.")
    preview, edit = st.tabs(["Готовый протокол", "Проверка и правки"])
    with preview:
        st.caption("Структура как в образце: реплики по темам → саммари → таблицы поручений. Имена и должности можно подтвердить во вкладке «Проверка и правки».")
        _render_document(output, include_details)
    with edit:
        _render_editor(meeting, repo)
    st.subheader("Скачать протокол")
    cols = st.columns(5)
    stem = f"minutes-{meeting.id[:8]}"
    cols[0].download_button("DOCX", export_docx(output, include_details), f"{stem}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    try:
        cols[1].download_button("PDF", export_pdf(output, include_details), f"{stem}.pdf", "application/pdf")
    except RuntimeError as exc:
        cols[1].error(str(exc))
    cols[2].download_button("TXT", export_txt(output, include_details), f"{stem}.txt", "text/plain; charset=utf-8")
    cols[3].download_button("JSON / СЭД", export_json(output), f"{stem}.json", "application/json")
    cols[4].download_button("Календарь", export_ics(output), f"{stem}.ics", "text/calendar")

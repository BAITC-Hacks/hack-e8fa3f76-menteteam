from datetime import date
from pathlib import Path
import re

import streamlit as st

from core.grounding import UNKNOWN_OWNER, rename_participants
from core.minutes import minutes_blocks
from core.models import DirectionReport
from exporters import anonymize, export_docx, export_ics, export_json, export_pdf, export_txt
from services.notifications import valid_email


def _render_protocol_form(meeting, repo, model_config=None):
    st.subheader("Имена, должности и протокол")
    st.caption("Измените данные и нажмите «Сохранить протокол и участников». Изменения появятся в тексте и скачиваемых файлах.")
    revision_key = f"protocol-revision-{meeting.id}"
    revision = st.session_state.get(revision_key, 0)
    if st.session_state.pop(f"protocol-saved-{meeting.id}", False):
        st.success("Имена, должности и протокол сохранены.")
    report_error = st.session_state.pop(f"report-error-{meeting.id}", "")
    if report_error:
        st.error(report_error)
    speakers = list(dict.fromkeys([*(segment.speaker for segment in meeting.transcript),
                                   *meeting.participants, *meeting.participant_roles,
                                   *(report.speaker_id for report in meeting.reports if report.speaker_id)]))
    speaker_choices = {"—": ""}
    for speaker in speakers:
        name = meeting.participants.get(speaker, speaker)
        speaker_choices[f"{name} · {speaker}" if name != speaker else speaker] = speaker
    speaker_labels = {value: key for key, value in speaker_choices.items()}
    existing_reports = {report.id: report for report in meeting.reports}
    with st.form(f"protocol-{meeting.id}-{revision}"):
        names, roles = {}, {}
        for index, speaker in enumerate(speakers, 1):
            st.markdown(f"**Голос {index} · {speaker}**")
            left, right = st.columns(2)
            names[speaker] = left.text_input("Имя участника", value=meeting.participants.get(speaker, ""),
                                            key=f"name-{meeting.id}-{speaker}-{revision}")
            roles[speaker] = right.text_input("Должность / роль", value=meeting.participant_roles.get(speaker, ""),
                                             key=f"role-{meeting.id}-{speaker}-{revision}")
            segment = next((segment for segment in meeting.transcript if segment.speaker == speaker), None)
            if segment:
                st.caption(f"[{segment.start:.1f} с] {segment.text[:160]}")
                if meeting.source_path and Path(meeting.source_path).is_file():
                    st.audio(meeting.source_path, start_time=int(segment.start),
                             end_time=max(int(segment.start) + 1, int(segment.end) + 1))
            if speaker == "Спикер не определён":
                st.caption("Эта метка объединяет неопределённые реплики. Указывайте имя, только если они принадлежат одному человеку.")
        if not speakers:
            st.info("В стенограмме пока нет участников.")
        with st.expander("Шапка, саммари и таблица показателей"):
            title = st.text_input("Тема совещания", meeting.title)
            organization = st.text_input("Организация", meeting.organization)
            summary = st.text_area("Саммари", meeting.summary, height=130)
            st.markdown("**Направления / доклады, показатели и проблемы**")
            st.caption("Можно исправлять ячейки, добавлять и удалять строки. Докладчик связывается с выбранным голосом; его имя обновляется при сохранении.")
            for report in meeting.reports:
                if report.review_required:
                    st.warning(f"{report.direction}: сверьте числа с цитатой. Неподтверждённые значения оставлены пустыми.")
                if report.evidence:
                    st.caption(f"Источник · {report.direction}")
                    st.write(report.evidence)
            report_rows = [{"id": report.id, "Направление / доклад": report.direction,
                            "Докладчик": speaker_labels.get(report.speaker_id, "—"),
                            "Показатель": report.indicator, "Проблема": report.problem}
                           for report in meeting.reports]
            if not report_rows:
                report_rows = [{"id": "", "Направление / доклад": "", "Докладчик": "—", "Показатель": "", "Проблема": ""}]
            edited_rows = st.data_editor(
                report_rows, num_rows="dynamic", hide_index=True, use_container_width=True,
                key=f"reports-{meeting.id}-{revision}", disabled=["id"],
                column_config={
                    "id": None,
                    "Направление / доклад": st.column_config.TextColumn("Направление / доклад"),
                    "Докладчик": st.column_config.SelectboxColumn("Докладчик", options=list(speaker_choices)),
                    "Показатель": st.column_config.TextColumn("Показатель"),
                    "Проблема": st.column_config.TextColumn("Проблема"),
                },
            )
            decisions = st.text_area("Решения — для приложения, по одному на строку", "\n".join(meeting.decisions))
        save_clicked = st.form_submit_button("Сохранить протокол и участников", type="primary")
        reports_clicked = False
        if model_config:
            reports_clicked = st.form_submit_button(
                "Сохранить и сформировать таблицу показателей",
                help="Сохраняет правки формы и заново заполняет таблицу по имеющейся стенограмме. Распознавание аудио не запускается.",
                disabled=not meeting.transcript,
            )
        if save_clicked or reports_clicked:
            reports, invalid = [], False
            for row in edited_rows:
                direction = str(row.get("Направление / доклад") or "").strip()
                indicator = str(row.get("Показатель") or "").strip()
                problem = str(row.get("Проблема") or "").strip()
                speaker = speaker_choices.get(row.get("Докладчик"), "")
                if not any((direction, indicator, problem, speaker)):
                    continue
                if not direction:
                    invalid = True
                    break
                original = existing_reports.get(row.get("id"))
                report = original.model_copy(deep=True) if original else DirectionReport(direction=direction)
                if original and (direction, speaker, indicator, problem) != (
                        original.direction, original.speaker_id, original.indicator, original.problem):
                    report.evidence = ""
                    report.review_required = False
                report.direction, report.speaker_id = direction, speaker
                report.indicator, report.problem = indicator, problem
                reports.append(report)
            if not title.strip():
                st.error("Укажите тему совещания. Введённые имена и должности сохранены в форме.")
            elif invalid:
                st.error("Заполните название направления в каждой непустой строке таблицы. Введённые данные остаются в форме.")
            else:
                updated = rename_participants(meeting, names)
                updated.participant_roles = {key: value.strip() for key, value in roles.items() if value.strip()}
                updated.title, updated.organization = title.strip(), organization.strip()
                updated.summary, updated.reports = summary, reports
                updated.decisions = [line.strip() for line in decisions.splitlines() if line.strip()]
                repo.save(updated)
                if reports_clicked:
                    from services.reports import rebuild_reports
                    try:
                        with st.spinner("Составляю таблицу показателей по стенограмме…"):
                            updated = rebuild_reports(updated, model_config["gemma"], model_config.get("token") or None)
                            repo.save_reports(updated.id, updated.reports, updated.questions)
                    except Exception as exc:
                        st.session_state[f"report-error-{meeting.id}"] = (
                            f"Правки сохранены. Таблицу показателей обновить не удалось: {exc}")
                st.session_state[revision_key] = revision + 1
                st.session_state[f"protocol-saved-{meeting.id}"] = True
                st.rerun()


def _render_editor(meeting, repo):
    st.subheader(meeting.title)
    st.caption(f"{meeting.meeting_date or 'Дата не указана'} · {meeting.language} · ID {meeting.id[:8]}")
    for warning in meeting.warnings:
        st.warning(warning)
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


def render_review(meeting, repo, model_config=None):
    _render_protocol_form(meeting, repo, model_config)
    include_details = st.checkbox("Включить приложение: цитаты, таймкоды и статусы поручений", key=f"details-{meeting.id}")
    redacted = st.checkbox("Обезличенная копия для демонстрации", key=f"redact-{meeting.id}")
    output = anonymize(meeting) if redacted else meeting
    if redacted:
        st.caption("Подтверждённые имена и контакты заменены. Перед публикацией проверьте свободный текст на оставшиеся персональные данные.")
    preview, edit = st.tabs(["Готовый протокол", "Проверка и правки"])
    with preview:
        st.caption("Текст совещания → саммари и таблица показателей → единая таблица поручений. Имена и должности редактируются выше.")
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

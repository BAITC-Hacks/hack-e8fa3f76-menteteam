import os
import shutil
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4
import streamlit as st
from dotenv import load_dotenv
from core.models import MeetingResult
from services.pipeline import analyze
from services.tracker import get_status, list_action_items, save_status
from exporters import export_docx, export_pdf

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
st.set_page_config(page_title="Alem Minutes", page_icon="🎙️", layout="wide")
st.title("🎙️ Alem Minutes")
st.caption("Локальная система протоколирования: транскрипт → поручения → контрольные вопросы")

st.subheader("Панель контроля")
tracked_items = list_action_items()
if tracked_items:
    today = date.today()
    overdue = [item for item in tracked_items if item["status"] == "В работе" and item["due_date"] and item["due_date"] < today.isoformat()]
    reminder_cutoff = today + timedelta(days=3)
    upcoming = [item for item in tracked_items if item["status"] == "В работе" and item["due_date"] and today.isoformat() <= item["due_date"] <= reminder_cutoff.isoformat()]
    x, y, z = st.columns(3)
    x.metric("В работе", sum(item["status"] == "В работе" for item in tracked_items))
    y.metric("Просрочено", len(overdue))
    z.metric("Срок в ближайшие 3 дня", len(upcoming))
    for item in overdue:
        st.error(f"Просрочено {item['due_date']}: {item['title']} · {item['owner']} · совещание: {item['meeting']}")
    for item in upcoming:
        st.warning(f"Скоро срок {item['due_date']}: {item['title']} · {item['owner']} · совещание: {item['meeting']}")
else:
    st.caption("После анализа и фиксации статусов здесь появятся поручения и напоминания.")

with st.sidebar:
    st.header("Обработка на этом компьютере")
    models = ["small", "base", "medium", "large-v3-turbo", "large-v3"]
    default_model = os.getenv("WHISPER_MODEL", "small")
    asr_model = st.selectbox("Whisper модель", models, index=models.index(default_model) if default_model in models else 0)
    llm_model = st.text_input("Локальная Gemma (Hugging Face model id или путь к весам)", os.getenv("GEMMA_MODEL", "google/gemma-4-E2B-it"))
    language = st.selectbox("Язык", ["auto", "ru", "kk"], format_func={"auto": "Авто (включая смешанную речь)", "ru": "Русский", "kk": "Казахский"}.get)
    compute_type = st.selectbox("Вычисления", ["int8", "float32"], index=0)
    hf_token = st.text_input("HF token для загрузки diarization-модели (не обязателен)", value=os.getenv("HF_TOKEN", ""), type="password")
    st.caption("Аудио и расшифровка обрабатываются локально. HF token используется только для получения весов pyannote; сама диаризация выполняется локально.")
    consent = st.checkbox("Я уведомил(а) участников о записи и ИИ-транскрибации и имею право обработать эту запись.", key="recording-consent")

files = [("Совещание №1", ROOT / "data" / "meeting1.mp3"), ("Совещание №2", ROOT / "data" / "meeting2.mp3")]
st.subheader("Записи")
selected = []
cols = st.columns(2)
for i, (title, path) in enumerate(files):
    with cols[i]:
        st.markdown(f"**{title}**")
        if path.exists():
            st.audio(str(path))
            if st.checkbox("Обработать", key=f"select-{title}", value=True): selected.append((title, path))
        else:
            st.info("Запись не найдена")
upload = st.file_uploader("Добавить MP3, WAV, M4A или MP4", type=["mp3", "wav", "m4a", "mp4", "mpeg", "mpga", "webm"])
if upload:
    selected.append((Path(upload.name).stem, upload))
    st.info("Загрузите запись только после уведомления участников. Файл обрабатывается на этом компьютере.")

if st.button("Распознать и составить протокол", type="primary", disabled=not selected or not consent):
    results = []
    progress = st.progress(0)
    for index, (title, path) in enumerate(selected):
        try:
            if hasattr(path, "getvalue"):
                upload_dir = ROOT / "data" / "uploads"
                upload_dir.mkdir(parents=True, exist_ok=True)
                suffix = Path(path.name).suffix.lower()
                safe_path = upload_dir / f"{uuid4().hex}{suffix}"
                safe_path.write_bytes(path.getvalue())
                path = safe_path
            with st.status(f"Обрабатываю локально: {title}", expanded=True) as status:
                st.write("1/3 Whisper распознаёт речь локально…")
                result = analyze(str(path), title, asr_model, llm_model,
                                 compute_type, language, hf_token or None)
                st.write("2/3 Локальная Gemma в Python извлекает поручения и саммари…")
                st.write("3/3 Сохраняю результат в локальный кэш…")
                status.update(label=f"Готово: {title}", state="complete", expanded=False)
            results.append(result)
            st.session_state.setdefault("source_audio", {})[title] = str(path)
        except Exception as exc:
            st.error(f"{title}: {exc}")
        progress.progress((index + 1) / len(selected))
    st.session_state["results"] = [r.model_dump() for r in results]

raw_results = st.session_state.get("results", [])
results = [MeetingResult.model_validate(r) for r in raw_results]
if not results:
    st.info("Выберите одну или обе записи и нажмите «Распознать и составить протокол». Первый запуск загрузит локальные модели; это может занять время.")
else:
    tabs = st.tabs([r.title for r in results])
    for tab, result in zip(tabs, results):
        with tab:
            st.caption(f"Распознанный язык: {result.language} · Спикеров: {len({s.speaker for s in result.transcript if s.speaker != 'Спикер не определён'})}")
            a, b, c = st.columns(3)
            a.metric("Решения", len(result.decisions)); b.metric("Поручения", len(result.tasks)); c.metric("Уточнения", len(result.questions))
            st.subheader("Контроль поручений")
            today = date.today()
            for task_index, task in enumerate(result.tasks):
                state_key = f"task-status-{result.title}-{task_index}"
                if state_key not in st.session_state:
                    st.session_state[state_key] = get_status(result.title, task.evidence, task.owner) or task.status
                status = st.selectbox(f"{task.title} · {task.owner} · {task.deadline}", ["В работе", "Выполнено"], key=state_key)
                save_status(result.title, task.evidence, task.owner, task.title, task.deadline, task.due_date, status)
                if status == "Выполнено":
                    st.success("Поручение выполнено")
                elif task.due_date:
                    days_left = (task.due_date - today).days
                    if days_left < 0:
                        st.error(f"Просрочено на {-days_left} дн. · ответственный: {task.owner}")
                    elif days_left <= 3:
                        st.warning(f"Срок через {days_left} дн. · ответственный: {task.owner}")
                else:
                    st.caption("Срок неоднозначен для календарного напоминания; исходная формулировка сохранена.")
            st.subheader("Саммари"); st.write(result.summary or "Саммари не сформировано")
            st.subheader("Решения")
            if result.decisions:
                for item in result.decisions: st.markdown(f"- {item}")
            else: st.caption("Решения в транскрипте не выделены.")
            st.subheader("Поручения")
            if not result.tasks: st.caption("Поручения не обнаружены.")
            for task in result.tasks:
                with st.container(border=True):
                    st.markdown(f"**{task.title}**")
                    st.write(f"Ответственный: {task.owner} · Срок: {task.deadline}")
                    st.caption(f"Цитата: «{task.evidence}» · {task.timestamp:.1f} сек")
                    source = st.session_state.get("source_audio", {}).get(result.title)
                    if source and Path(source).exists(): st.audio(source, start_time=max(0, int(task.timestamp - 2)))
            if result.questions:
                st.subheader("Требуют уточнения")
                for question in result.questions: st.warning(question)
            with st.expander(f"Транскрипт ({len(result.transcript)} фрагментов)"):
                for segment in result.transcript:
                    st.write(f"[{segment.start:.1f}–{segment.end:.1f}] {segment.speaker}: {segment.text}")
            x, y = st.columns(2)
            slug = "meeting"
            export_tasks = [task.model_copy(update={"status": get_status(result.title, task.evidence, task.owner) or task.status}) for task in result.tasks]
            export_result = result.model_copy(update={"tasks": export_tasks})
            x.download_button("Скачать DOCX", export_docx(export_result), file_name=f"{slug}_minutes.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", key=f"docx-{result.title}")
            y.download_button("Скачать PDF", export_pdf(export_result), file_name=f"{slug}_minutes.pdf", mime="application/pdf", key=f"pdf-{result.title}")

st.divider()
st.caption("Приватность: распознавание речи и языковой анализ выполняются локальными моделями. Внешние API для обработки аудио/текста не вызываются. Модельные веса загружаются в локальный кэш при первом запуске.")
with st.expander("Управление локальными данными"):
    st.write("Аудиозаписи, результаты протоколов и статусы поручений хранятся на этом компьютере. Кнопка ниже удалит загруженные аудио, кэш протоколов и базу статусов; скачанные веса моделей останутся.")
    if st.button("Удалить аудио, протоколы и статусы", type="secondary"):
        for directory in (ROOT / "data" / "uploads", ROOT / "data" / "cache"):
            shutil.rmtree(directory, ignore_errors=True)
        for database in (ROOT / "data" / "tasks.sqlite3", ROOT / "data" / "tasks.sqlite3-wal", ROOT / "data" / "tasks.sqlite3-shm"):
            database.unlink(missing_ok=True)
        st.session_state.pop("results", None)
        st.session_state.pop("source_audio", None)
        st.success("Локальные записи, протоколы и статусы удалены.")
        st.rerun()

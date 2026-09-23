"""Local UI; business rules and infrastructure live behind application interfaces."""
import os
import shutil
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from adapters.repository import SQLiteMeetings
from core.languages import LANGUAGE_MODES
from services.demo import demo_meeting
from services.notifications import dispatch
from settings import DATA, OFFLINE
from ui.dashboard import render_dashboard
from ui.intake import render_intake
from ui.review import render_review

st.set_page_config(page_title="Alem Minutes · Поручения под контролем", page_icon="◉", layout="wide")
st.markdown("""<style>
.block-container{max-width:1280px;padding-top:2rem}h1{letter-spacing:-.04em}
[data-testid="stMetric"]{background:#f2f5fa;border-radius:14px;padding:16px;border:1px solid #e3e9f3}
[data-testid="stMetricValue"]{color:#2457bc}div[data-testid="stSidebar"]{background:#f5f7fb}
</style>""", unsafe_allow_html=True)
st.caption("ALEM MINUTES  /  РУССКИЙ · ҚАЗАҚША · СМЕШАННАЯ РЕЧЬ")
st.title("Встреча закончилась. Поручения остались.")
st.write("Локальный протокол с цитатами, ответственными и сроками — от записи до контроля исполнения.")
repo = SQLiteMeetings(DATA / "meetings.sqlite3")

with st.sidebar:
    st.header("Alem Minutes")
    st.success("Офлайн-режим" if OFFLINE else "Локальный ИИ · загрузка весов разрешена")
    st.caption("Whisper + Gemma работают в Python на этом компьютере. При первом запуске нужны веса моделей.")
    with st.expander("Настройки моделей"):
        whisper = st.text_input("Whisper: модель или локальный каталог", os.getenv("WHISPER_MODEL", "large-v3"))
        gemma = st.text_input("Gemma: модель или локальный каталог", os.getenv("GEMMA_MODEL", "google/gemma-4-E2B-it"))
        language = st.selectbox(
            "Язык записи", LANGUAGE_MODES,
            format_func={"auto": "Авто: KZ / RU / EN · шала қазақша", "ru": "Русский", "kk": "Қазақша", "en": "English"}.get,
        )
        st.caption("Авто выбирает только қазақша, русский и English по фрагментам записи. Для шала қазақша оставьте «Авто».")
        compute_types = ["int8_float16", "float16", "int8", "float32"]
        default_compute = os.getenv("WHISPER_COMPUTE", "int8_float16")
        compute = st.selectbox("Точность Whisper", compute_types, index=compute_types.index(default_compute) if default_compute in compute_types else 0)
        st.caption(f"Устройство: {os.getenv('AI_DEVICE', 'cuda')}. T4: Gemma FP16; модели освобождают VRAM между этапами.")
        token_override = st.text_input("HF token для загрузки весов", value="", type="password",
                                       placeholder="Серверный токен настроен" if os.getenv("HF_TOKEN") else "Не задан")
        token = token_override or os.getenv("HF_TOKEN", "")
    st.divider()
    st.write("Попробовать без загрузки моделей")
    st.caption("Синтетический пример показывает проверку поручений и экспорт. Он не измеряет качество распознавания.")
    if st.button("Открыть демонстрацию", use_container_width=True):
        result = demo_meeting()
        repo.save(result)
        st.session_state["meeting_id"] = result.id
    st.divider()
    with st.expander("Уведомления"):
        st.write("Только для проверенных поручений с email. Worker можно запускать по расписанию независимо от интерфейса.")
        if st.button("Подготовить письма локально"):
            count = dispatch(repo, DATA / "outbox")
            st.success(f"Подготовлено: {count}. Письма в data/outbox; отправка не выполнялась.")
        st.code("uv run python notification_worker.py --interval 300", language="bash")
        st.caption("Доставка через SMTP включается отдельным параметром --send после настройки .env.")

meetings = repo.list()
intake, control, history = st.tabs(["Новое совещание", "Обзор поручений", "Протоколы"])
with control:
    render_dashboard(meetings)
with intake:
    render_intake(repo, DATA, dict(whisper=whisper, gemma=gemma, language=language, compute=compute, token=token))
with history:
    # Intake can have saved a result during this run.
    meetings = repo.list()
    if not meetings:
        st.info("История пока пуста. Загрузите запись или откройте демонстрацию.")
    else:
        labels = {m.id: f"{m.title} · {m.meeting_date or 'без даты'} · {m.id[:6]}" for m in meetings}
        if st.session_state.get("meeting_id") not in labels:
            st.session_state["meeting_id"] = meetings[0].id
        selected = st.selectbox("История совещаний", list(labels), format_func=labels.get, key="meeting_id")
        meeting = repo.get(selected)
        render_review(meeting, repo)

st.divider()
with st.expander("Локальные данные и приватность"):
    st.write("Данные хранятся на этом компьютере. Для публичной демонстрации скачайте обезличенную копию и проверьте её. Для закрытого контура подготовьте веса и включите ALEM_OFFLINE=1.")
    st.caption("Удаление очищает историю, загруженные записи, кэш и локальные письма. Веса моделей и примеры из репозитория остаются. Остановите запись и worker перед удалением.")
    confirmation = st.checkbox("Подтверждаю удаление загруженных записей, протоколов и статусов")
    if st.button("Удалить локальные данные", disabled=not confirmation):
        with repo.connect() as db:
            db.execute("DELETE FROM meetings")
            db.execute("DELETE FROM notifications")
        for folder in ("uploads", "cache", "outbox"):
            shutil.rmtree(DATA / folder, ignore_errors=True)
        for suffix in ("", "-wal", "-shm"):
            (DATA / f"tasks.sqlite3{suffix}").unlink(missing_ok=True)
        for key in list(st.session_state):
            del st.session_state[key]
        st.rerun()

import os
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

import streamlit as st

from services.pipeline import analyze
from settings import ROOT


MEDIA_FORMATS = {
    "mp3": "audio/mpeg", "wav": "audio/wav", "m4a": "audio/mp4",
    "flac": "audio/flac", "aac": "audio/aac", "ogg": "audio/ogg",
    "opus": "audio/ogg", "mpga": "audio/mpeg", "mp4": "video/mp4",
    "webm": "video/webm", "mpeg": "video/mpeg",
}


@st.cache_resource
def capture_service(directory: str, port: int):
    from services.capture import start_capture
    return start_capture(Path(directory), port)


def render_intake(repo, data_dir, config):
    st.subheader("Новое совещание")
    st.caption("1. Добавьте запись → 2. Запустите локальный анализ → 3. Проверьте и подтвердите поручения")
    title = st.text_input("Название совещания", placeholder="Например: планирование пилота")
    meeting_date = st.date_input("Дата совещания", value=date.today(), help="Используется для сроков «завтра» / «ертең».")
    consent = st.checkbox("Участники уведомлены о записи и ИИ-транскрибации; у меня есть право обработать запись.")
    source = st.radio("Источник", ["Файл", "Микрофон", "Teams / Zoom / Meet", "Примеры записей"], horizontal=True)
    audio, path = None, None
    if source == "Файл":
        st.caption("Загрузите запись с вашего устройства: MP3, WAV, M4A, FLAC, AAC, OGG, OPUS, MPGA, MP4, WebM или MPEG. До 200 МБ на файл.")
        if not consent:
            st.info("Чтобы выбрать файл, отметьте выше подтверждение права на обработку записи.")
        audio = st.file_uploader(
            "Загрузить MP3 или другую запись", type=list(MEDIA_FORMATS),
            help="Перетащите файл сюда или нажмите Browse files. Обработка выполняется на сервере.",
            disabled=not consent,
        )
    elif source == "Микрофон":
        audio = st.audio_input("Записать совещание", disabled=not consent)
    elif source == "Teams / Zoom / Meet":
        st.write("Откройте страницу записи, войдите во встречу участником и выберите вкладку со звуком. Анализ начнётся после сохранения записи.")
        if st.button("Открыть локальную запись", disabled=not consent):
            try:
                server = capture_service(str(data_dir / "uploads"), int(os.getenv("CAPTURE_PORT", "8765")))
                st.session_state["capture_url"] = f"http://127.0.0.1:{server.server_port}/?token={server.token}"
            except OSError as exc:
                st.error(f"Не удалось открыть порт записи: {exc}")
        if st.session_state.get("capture_url"):
            st.link_button("Перейти к записи встречи ↗", st.session_state["capture_url"])
        st.button("Обновить live-записи")
        recordings = sorted((data_dir / "uploads").glob("live-*"), key=lambda p: p.stat().st_mtime, reverse=True)
        recordings = [p for p in recordings if p.suffix in {".webm", ".ogg", ".m4a"}]
        if recordings:
            path = st.selectbox("Сохранённые live-записи", recordings,
                                format_func=lambda p: f"{datetime.fromtimestamp(p.stat().st_mtime):%d.%m %H:%M} · {p.name[:17]} · {p.stat().st_size // 1024} КБ")
        else:
            st.info("Сохранённых live-записей пока нет.")
    else:
        examples = [p for p in (ROOT / "data").glob("meeting*.mp3")]
        if examples:
            path = st.selectbox("Тестовая запись", examples, format_func=lambda p: p.name)
        else:
            st.info("Примеры не установлены — загрузите свою запись.")
    if audio:
        st.caption(f"Выбрано: {audio.name} · {audio.size / (1024 * 1024):.1f} МБ")
        media_format = MEDIA_FORMATS.get(Path(audio.name).suffix.lower().lstrip("."), "audio/wav")
        if media_format.startswith("video/"):
            st.video(audio, format=media_format)
        else:
            st.audio(audio, format=media_format)
        st.caption("Нажмите «Распознать и составить протокол», чтобы начать обработку.")
    elif path:
        st.audio(str(path))
    retry = st.checkbox("Повторить анализ без кэша")
    if st.button("Распознать и составить протокол", type="primary", disabled=not consent or not (audio or path)):
        try:
            if audio:
                if audio.size > 200 * 1024 * 1024:
                    raise ValueError("Максимальный размер записи — 200 МБ.")
                directory = data_dir / "uploads"
                directory.mkdir(parents=True, exist_ok=True)
                suffix = Path(audio.name).suffix.lower() or ".wav"
                path = directory / f"{uuid4().hex}{suffix}"
                path.write_bytes(audio.getvalue())
                path.chmod(0o600)
            with st.status("Обработка записи на сервере…", expanded=True) as status:
                result = analyze(str(path), title.strip() or f"Совещание {meeting_date}",
                                 config["whisper"], config["gemma"], config["compute"], config["language"],
                                 config["token"] or None, meeting_date, progress=st.write, use_cache=not retry)
                repo.save(result)
                status.update(label="Протокол готов к проверке", state="complete")
            st.session_state["meeting_id"] = result.id
            st.success("Результат сохранён. Откройте вкладку «Протоколы» и подтвердите участников и поручения.")
        except Exception as exc:
            st.error(f"Обработка не завершена: {exc}")

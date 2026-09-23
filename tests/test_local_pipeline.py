from core.models import MeetingResult, Segment, Task
from exporters import export_docx, export_pdf
from services.pipeline import _llama_cpp_extract
import pytest


def test_protocol_and_docx_pdf_export():
    result = MeetingResult(title="Тест", summary="Проверка", language="ru",
        tasks=[Task(title="Отправить документ", owner="Айжан", deadline="завтра", evidence="Я отправлю документ", timestamp=12)],
        transcript=[Segment(id="1", speaker="SPEAKER_00", start=12, end=13, text="Я отправлю документ")])
    assert export_docx(result).startswith(b"PK")
    assert export_pdf(result).startswith(b"%PDF")


def test_llama_cpp_rejects_remote_endpoint():
    with pytest.raises(RuntimeError, match="локально"):
        _llama_cpp_extract("test", "gemma4", "https://example.com/v1")


def test_quote_validation_is_case_insensitive():
    transcript = "Я отправлю документ"
    assert "я отправлю документ" in transcript.casefold()
    assert "отправлю завтра" not in transcript.casefold()


def test_empty_audio_is_rejected(tmp_path):
    from services.pipeline import analyze
    audio = tmp_path / "empty.mp3"
    audio.write_bytes(b"")
    with pytest.raises(RuntimeError, match="пуст"):
        analyze(str(audio), "empty", "small", "gemma4", "http://127.0.0.1:8080/v1")

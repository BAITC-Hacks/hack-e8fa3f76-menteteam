from types import SimpleNamespace

import pytest


def test_word_alignment_splits_speaker_change():
    from adapters.speech import align_speakers
    chunk = SimpleNamespace(start=0, end=4, text="Привет. Сәлем.", words=[
        SimpleNamespace(start=0, end=1, word="Привет."),
        SimpleNamespace(start=2, end=3, word=" Сәлем.")])
    result = align_speakers([chunk], [(0, 1.5, "SPEAKER_00"), (1.5, 4, "SPEAKER_01")])
    assert [(s.speaker, s.text, s.start) for s in result] == [
        ("SPEAKER_00", "Привет.", 0), ("SPEAKER_01", "Сәлем.", 2)]


def test_json_parser_validates_shape_and_accepts_fences():
    from adapters.gemma import parse_minutes
    assert parse_minutes('```json\n{"summary":"Сәлем", "tasks":[]}\n```')["summary"] == "Сәлем"
    with pytest.raises(ValueError):
        parse_minutes('{"summary": [], "tasks": "invalid"}')


def test_chunking_keeps_all_text_with_bounded_inputs():
    from adapters.gemma import transcript_batches
    text = "A" * 31 + "\n" + "B" * 18
    chunks = transcript_batches(text, limit=20)
    assert all(len(c) <= 20 for c in chunks)
    assert "".join(chunks).replace("\n", "") == text.replace("\n", "")

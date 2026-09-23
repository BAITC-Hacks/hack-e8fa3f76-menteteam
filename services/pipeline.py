"""Offline-first meeting processing. Audio and transcript are never sent to a web API."""
import hashlib
import json
from pathlib import Path
from faster_whisper import WhisperModel
from core.models import MeetingResult, Segment, Task
from services.llm import extract_minutes

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache"
PIPELINE_VERSION = "local-3"


def _llama_cpp_extract(transcript: str, model: str, server_url: str) -> dict:
    """Compatibility error for callers of the retired inference-server API."""
    from urllib.parse import urlparse
    if urlparse(server_url).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError("Внешние inference API запрещены: используйте Gemma из Python.")
    raise RuntimeError("Интерфейс llama.cpp удалён. Вызовите services.llm.extract_minutes().")


def _diarize(path: str, hf_token: str | None):
    if not hf_token:
        return None, "Диаризация не запущена: задайте HF_TOKEN и примите условия модели pyannote Community-1. Аудио при обработке остаётся локально."
    try:
        import torch
        from pyannote.audio import Pipeline
    except ImportError:
        return None, "Диаризация недоступна: установите опциональные зависимости `uv sync --extra diarization`."
    try:
        pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-community-1", token=hf_token)
        if torch.cuda.is_available():
            pipeline.to(torch.device("cuda"))
        # Feed decoded samples so pyannote does not need TorchCodec's optional
        # decoder (ffmpeg/faster-whisper handles MP3 decoding consistently).
        from faster_whisper.audio import decode_audio
        waveform = torch.from_numpy(decode_audio(path, sampling_rate=16000)).unsqueeze(0)
        diarization = pipeline({"waveform": waveform, "sample_rate": 16000})
        turns = getattr(diarization, "speaker_diarization", diarization)
        return [(float(turn.start), float(turn.end), str(speaker)) for turn, speaker in turns], None
    except Exception as exc:
        return None, f"Не удалось выполнить локальную диаризацию: {exc}"


def transcribe(path: str, model_name: str, compute_type: str = "int8", language: str = "auto", hf_token: str | None = None):
    """Whisper inference runs on CPU/GPU locally; model weights are cached by faster-whisper."""
    try:
        model = WhisperModel(model_name, device="auto", compute_type=compute_type,
                             download_root=str(ROOT / "data" / "models"))
        lang = None if language == "auto" else language
        chunks, info = model.transcribe(path, language=lang, task="transcribe", vad_filter=True,
                                        word_timestamps=True, beam_size=5)
        recognized = list(chunks)
        speakers, warning = _diarize(path, hf_token)
        result = []
        for i, chunk in enumerate(recognized, 1):
            speaker = "Спикер не определён"
            if speakers:
                durations = [(max(0, min(chunk.end, end)-max(chunk.start, start)), name) for start, end, name in speakers]
                if durations and max(durations)[0] > 0:
                    speaker = max(durations)[1]
            result.append(Segment(id=f"seg-{i}", speaker=speaker, start=float(chunk.start), end=float(chunk.end), text=chunk.text.strip()))
        if not result:
            raise RuntimeError("Модель распознавания не нашла речь в записи.")
        return result, info.language, warning
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Ошибка локальной транскрибации: {exc}") from exc


def analyze(path: str, title: str, asr_model: str, llm_model: str,
            compute_type: str = "int8", language: str = "auto", hf_token: str | None = None):
    p = Path(path)
    if p.stat().st_size == 0:
        raise RuntimeError("Аудиофайл пуст.")
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    key = f"{digest}-{asr_model}-{llm_model}-{language}-{int(bool(hf_token))}-{PIPELINE_VERSION}"
    cached = CACHE / f"{key}.json"
    if cached.exists():
        return MeetingResult.model_validate_json(cached.read_text(encoding="utf-8"))
    segments, detected_language, diarization_warning = transcribe(str(p), asr_model, compute_type, language, hf_token)
    transcript = "\n".join(f"[{s.start:.1f}-{s.end:.1f}] {s.speaker}: {s.text}" for s in segments)
    data = extract_minutes(transcript, llm_model)
    # Evidence quotes are checked against recognized speech before claims are shown.
    transcript_flat = " ".join(s.text for s in segments).casefold()
    tasks = []
    questions = list(data.get("questions", []))
    for raw in data.get("tasks", []):
        quote = str(raw.get("evidence", "")).strip()
        if not quote or quote.casefold() not in transcript_flat:
            questions.append(f"Поручение «{raw.get('title', 'без названия')}» не показано: цитату нельзя подтвердить по распознанной речи.")
            continue
        owner = raw.get("owner") or "Ответственный не определён"
        deadline = raw.get("deadline") or "Срок не определён"
        if owner.casefold() in {"ответственный не определён", "не определён", "не указан", "unknown"}:
            owner = "Ответственный не определён"
            questions.append(f"Кто отвечает за поручение «{raw['title']}»?")
        if deadline.casefold() in {"срок не определён", "не определён", "не указан", "unknown"}:
            deadline = "Срок не определён"
            questions.append(f"Какой срок выполнения поручения «{raw['title']}»?")
        # Ground the player seek time in the recognized segment containing the quote;
        # do not trust a model-generated timestamp.
        citation_segment = next((s for s in segments if quote.casefold() in s.text.casefold()), None)
        if citation_segment is None:
            offset = transcript_flat.find(quote.casefold())
            cumulative = 0
            for segment in segments:
                next_offset = cumulative + len(segment.text)
                if cumulative <= offset < next_offset:
                    citation_segment = segment
                    break
                cumulative = next_offset + 1
        grounded_time = citation_segment.start if citation_segment else 0.0
        due_date = None
        if raw.get("due_date"):
            try:
                from datetime import date
                due_date = date.fromisoformat(str(raw["due_date"]))
            except ValueError:
                questions.append(f"Не удалось проверить дату срока поручения «{raw.get('title', 'без названия')}».")
        tasks.append(Task(title=raw["title"], owner=owner, deadline=deadline, evidence=quote,
                          timestamp=float(grounded_time), due_date=due_date))
    if diarization_warning:
        questions.append(diarization_warning)
    result = MeetingResult(title=title, summary=data.get("summary", ""), decisions=data.get("decisions", []),
                           tasks=tasks, questions=questions, transcript=segments, language=detected_language)
    CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return result

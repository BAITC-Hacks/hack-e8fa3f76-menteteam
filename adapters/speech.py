"""Whisper and pyannote inference through local Python APIs."""
from functools import lru_cache
from pathlib import Path

from core.languages import LANGUAGE_MODES, SPEECH_LANGUAGES
from core.models import Segment
from settings import MODEL_CACHE, OFFLINE
from adapters.runtime import INFERENCE_LOCK, lifecycle, runtime
from adapters.whisper_languages import RestrictedLanguageModel


@lru_cache(maxsize=1)
def whisper_model(name: str, compute_type: str):
    from faster_whisper import WhisperModel
    device, _ = runtime()
    model = WhisperModel(name, device=device, compute_type=compute_type,
                         download_root=str(MODEL_CACHE), local_files_only=OFFLINE)
    if not model.model.is_multilingual:
        raise ValueError("Выберите многоязычный Whisper, например large-v3, для kk / ru / en.")
    model.model = RestrictedLanguageModel(model.model)
    return model


@lru_cache(maxsize=1)
def diarization_model(model_name: str, token: str | None):
    import torch
    from pyannote.audio import Pipeline
    if OFFLINE and not Path(model_name).exists():
        raise ValueError("Для офлайн-диаризации задайте DIARIZATION_MODEL — путь к локальным весам.")
    pipeline = Pipeline.from_pretrained(model_name, token=token, cache_dir=str(MODEL_CACHE))
    device, _ = runtime()
    if device == "cuda":
        pipeline.to(torch.device("cuda"))
    return pipeline


def align_speakers(chunks, turns) -> list[Segment]:
    def speaker_at(start, end):
        overlaps = [(max(0, min(end, stop) - max(start, begin)), speaker)
                    for begin, stop, speaker in turns]
        return max(overlaps)[1] if overlaps and max(overlaps)[0] > 0 else "Спикер не определён"

    result = []
    for chunk in chunks:
        words = getattr(chunk, "words", None)
        units = words if words and turns else [chunk]
        for unit in units:
            speaker = speaker_at(unit.start, unit.end)
            text = unit.word if words and turns else unit.text
            if not text or not text.strip():
                continue
            if (result and result[-1].speaker == speaker and unit.start - result[-1].end < 1.5
                    and unit.end - result[-1].start <= 30 and len(result[-1].text) < 600):
                result[-1].text += " " + text.strip()
                result[-1].end = float(unit.end)
            else:
                result.append(Segment(id=f"seg-{len(result)+1}", speaker=speaker,
                                      start=float(unit.start), end=float(unit.end), text=text.strip()))
    return result


class LocalSpeech:
    def __init__(self, model: str = "large-v3", compute_type: str = "int8_float16", language: str = "auto",
                 hf_token: str | None = None, diarization: str = "pyannote/speaker-diarization-community-1"):
        if language not in LANGUAGE_MODES:
            raise ValueError("Язык записи: auto, kk, ru или en.")
        self.model, self.compute_type, self.language = model, compute_type, language
        self.hf_token, self.diarization = hf_token, diarization

    def transcribe(self, path: str) -> tuple[list[Segment], str, str | None]:
        with INFERENCE_LOCK:
            lifecycle.activate("speech")
            try:
                model = whisper_model(self.model, self.compute_type)
                model.model.detected_languages.clear()
                automatic = self.language == "auto"
                chunks, info = model.transcribe(
                    path, language=None if automatic else self.language,
                    multilingual=automatic,
                    # Previous-language text can bias the next window into translation.
                    condition_on_previous_text=not automatic,
                    task="transcribe", vad_filter=True, word_timestamps=True, beam_size=5)
                recognized = list(chunks)
                language = (
                    " / ".join(code for code in SPEECH_LANGUAGES if code in model.model.detected_languages)
                    if automatic else self.language
                ) or info.language
            except Exception as exc:
                raise RuntimeError(f"Whisper: не удалось распознать запись: {exc}") from exc
            turns, warning = [], None
            try:
                import torch
                from faster_whisper.audio import decode_audio
                pipeline = diarization_model(self.diarization, self.hf_token)
                output = pipeline({"waveform": torch.from_numpy(decode_audio(path, sampling_rate=16000)).unsqueeze(0),
                                   "sample_rate": 16000})
                annotation = getattr(output, "exclusive_speaker_diarization", None)
                if annotation is None:
                    annotation = getattr(output, "speaker_diarization", output)
                turns = [(float(turn.start), float(turn.end), str(speaker))
                         for turn, _, speaker in annotation.itertracks(yield_label=True)]
                if not turns:
                    warning = "Диаризация не нашла спикеров. Проверьте запись."
            except Exception as exc:
                warning = ("Диаризация не выполнена. Установите extra diarization, подготовьте веса Community-1 "
                           f"и HF_TOKEN или локальный DIARIZATION_MODEL. Причина: {type(exc).__name__}.")
            return align_speakers(recognized, turns), language, warning


def release_models():
    whisper_model.cache_clear()
    diarization_model.cache_clear()


lifecycle.register("speech", release_models)

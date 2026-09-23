"""Restrict both initial and per-window CTranslate2 language detection."""
from core.languages import SPEECH_LANGUAGES


class RestrictedLanguageModel:
    """Delegate inference while filtering language candidates before selection.

    Faster-Whisper calls its backend directly for multilingual windows, so
    overriding only WhisperModel.detect_language would leave those unrestricted.
    Keep original probabilities: filtering must not inflate confidence.
    """

    def __init__(self, backend):
        self._backend = backend
        self._allowed_tokens = {f"<|{language}|>" for language in SPEECH_LANGUAGES}
        self.detected_languages: set[str] = set()

    def __getattr__(self, name):
        return getattr(self._backend, name)

    def detect_language(self, *args, **kwargs):
        restricted = []
        for candidates in self._backend.detect_language(*args, **kwargs):
            allowed = sorted(
                ((token, probability) for token, probability in candidates
                 if token in self._allowed_tokens),
                key=lambda candidate: candidate[1], reverse=True,
            )
            if not allowed:
                raise RuntimeError("Whisper не вернул оценки языков kk, ru или en.")
            self.detected_languages.add(allowed[0][0][2:-2])
            restricted.append(allowed)
        return restricted

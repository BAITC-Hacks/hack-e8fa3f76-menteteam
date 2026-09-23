# Backend security integration

The existing `security/` implementation is unchanged. All detection, risk
assessment, sanitization and JSONL auditing are delegated to that package.

## Processing path

1. `ui/intake.py::render_intake` or `process_recording.py::main` supplies audio
   to `services/pipeline.py::analyze`.
2. `adapters/speech.py::LocalSpeech.transcribe` invokes local Faster-Whisper,
   then local pyannote. `align_speakers` returns `Segment` objects.
3. `application/process.py::ProcessMeeting.run` joins segment text with spaces
   and invokes `application/security_gate.py::check_transcript` before extraction.
4. The adapter calls the existing public API:

   ```python
   from security.security_pipeline import analyze_transcript

   result = analyze_transcript(text)
   ```

5. `requires_review=True` returns a `MeetingResult` with a structured `security`
   decision, no generated summary/tasks, and a fixed warning. No LLM call occurs.
6. Otherwise `result["sanitized_text"]` is passed to the extractor along with
   sanitized segment copies. `LocalGemma.extract` renders those segments as
   untrusted user content and runs the local Transformers model.
7. `core/grounding.py::build_result` verifies evidence against the same sanitized
   segments, retaining speaker attribution and timestamps for tasks and reports.

## Segment preservation

Only segment `text` changes. `id`, `speaker`, `start`, and `end` are preserved;
the original transcriber objects are not mutated. The adapter projects pipeline
finding offsets onto each segment and calls the existing
`security.sanitizer.redact_findings`, without implementing another detector or
redaction policy. Scanning speech before adding labels detects instruction
phrases split across turns and avoids masking timestamps as phone numbers.
Spaces allow the existing detector to recognize supported secrets crossing
segment boundaries; each affected segment is redacted independently, so a
placeholder may repeat across those boundaries.

## Decisions and errors

`MeetingResult.security` is optional for backward compatibility with saved
meetings. New processed meetings include:

```json
{
  "status": "requires_review",
  "requires_review": true,
  "risk_level": "HIGH",
  "llm_input_policy": "UNTRUSTED",
  "pii_detected": false,
  "prompt_injection_detected": true,
  "error_code": null
}
```

Allowed status values are `passed`, `requires_review`, and `security_error`.
Security exceptions, invalid responses and audit failures return
`security_error`, `requires_review=true`, and
`error_code="SECURITY_PROCESSING_FAILED"`. Text is withheld on failure, while
segment attribution and timing remain available. Neither exception details nor
raw input are returned or logged. Only the existing audit logger is used; if
audit writing also fails, the blocked decision still stands.

`services/reports.py::rebuild_reports` applies the same gate and does not
automatically approve an already-blocked meeting after its secrets have been
redacted. `services/llm.py::extract_minutes` also applies the gate and returns
an empty summary/tasks with a structured `security` entry when blocked.
The UI shows the security hold and does not report successful generation.
There is deliberately no automatic approval/retry bypass.

## Local LLM and caches

Gemma's trusted system message contains separate static security and application
instruction blocks. The transcript, including its segment labels, is exclusively
user-message data. There is no concatenation of transcript into system content,
no external inference API, and no new network operation. Model loading remains
unchanged; use the existing `ALEM_OFFLINE=1` and prepared local model paths to
disable model downloads. Prompt separation and heuristic detection do not
guarantee that a model will resist every injection.

Cache version `local-8-security-gate` invalidates earlier generated results.
Only successful checked results are cached; records without a passed security
decision are not reused. Original recordings and earlier stored meetings are
not rewritten. Direct low-level use of `LocalGemma.extract` requires a prior
security check; backend callers should use the guarded application/services.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_security.py
.\.venv\Scripts\python.exe -m pytest -q tests/test_security_integration.py
.\.venv\Scripts\python.exe -m pytest -q
```

Tests use the real security implementation and mocked local inference. They
cover allowed/PII/injection/error paths, multi-segment redaction, metadata,
grounding, safe auditing, additional LLM entry points, caches and chat-message
separation. Security integration tests prohibit network connections. Existing
capture tests use loopback HTTP. PDF tests require DejaVu Sans, as documented
by the backend; on Windows it can be supplied at `assets/DejaVuSans.ttf`.
Real model inference still requires the project's AI extras and local weights.

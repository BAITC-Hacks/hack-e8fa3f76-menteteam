# Local transcript security

Python 3.11+. Runtime uses only the standard library. No network requests,
model downloads, LLM calls, prompt templates, transcription or frontend code.

From the repository root:

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m security.demo
```

Installing pytest may require package-index access; security processing and
the tests/demo themselves work offline. The demo uses only synthetic values
and creates `security_audit.jsonl` locally, excluded from Git.

## Requirement mapping

| Document requirement | Implementation |
| --- | --- |
| Six PII categories, structured spans | `pii_detector.detect_pii`, immutable `Finding` |
| Typed placeholders, optional findings | `sanitizer.sanitize_text`, `sanitize_with_findings` |
| English/Russian injection patterns and risk | `prompt_guard.analyze_prompt_injection` |
| Safe local JSONL events | `audit_logger.AuditLogger.log_event` |
| Validation, risk, untrusted boundary | `security_pipeline.analyze_transcript` |
| Public API | `security.__init__` |
| Synthetic runnable demo | `demo.main` |
| Fifteen validation categories | `tests/test_security.py` |

## Backend integration

There is no backend implementation in this checkout yet. Insert this call
after local Faster-Whisper and diarization have produced the transcript, before
the local/self-hosted LLM receives any transcript content:

```python
from security.security_pipeline import analyze_transcript

result = analyze_transcript(transcript)
safe_transcript = result["sanitized_text"]
requires_review = result["requires_review"]
input_policy = result["llm_input_policy"]  # Always UNTRUSTED
```

The backend should hold items requiring review rather than automatically submit
them. When it permits processing, it must pass only `safe_transcript` as untrusted
data, keeping trusted system instructions and application instructions separate.
Never interpolate the original transcript into a system/instruction message.
This package deliberately neither constructs a prompt nor modifies a system
prompt. `UNTRUSTED` is a contract the future backend must enforce, not a mechanism
that forces a model to obey. Local deployment alone does not stop injection.

Optional audit configuration:

```python
from security.audit_logger import AuditLogger

result = analyze_transcript(
    transcript,
    audit_logger=AuditLogger("security_audit.jsonl"),
)
```

The audit directory must already exist and be writable. Configure its OS access
permissions for the backend account. Logs contain only fixed event identifiers,
counts, flags and UTC timestamps. Arbitrary metadata and exception messages are
rejected. No root logging handlers are invoked. An audit write failure raises
`AuditLogError`; processing must not continue silently. Invalid input raises
`ValueError`; unexpected processing failures raise a generic `RuntimeError`.
Avoid logging the backend's incoming request body or exception locals.

## Result and detection limits

`findings` in the pipeline result contain type, original character offsets and
risk, without raw values. `detect_pii` and `sanitize_with_findings` return
`Finding` instances including raw values for in-memory use; do not log, persist
or return those instances to clients. Their repr omits the value. Offsets refer
to the original input, not the sanitized text. Overlapping findings are merged
for redaction, so counts describe detections rather than replacement count.

Risk is the maximum finding risk: LOW for no detected issue, MEDIUM for email
or phone, HIGH for IIN/card-like numbers or injection, CRITICAL for passwords
or tokens. `requires_review` is true for injection or CRITICAL risk. Input is
limited to 1,000,000 characters; empty strings are valid.

Number detection is conservative and shape-based, without checksum validation.
Unformatted 12-digit numbers are treated as IIN; 13–19 digit numeric sequences
as card-like; other supported phone shapes have 7–15 digits. Ambiguous numeric
types can be misclassified but are still redacted. Credentials are detected
after English/Russian labels with `:`, `=`, `is` or `это`, or via recognizable
token prefixes/Bearer notation. Quote multiword passwords in text where possible.
Arbitrary unlabeled secrets and all natural-language PII cannot be guaranteed.

Injection detection covers the document's English/Russian examples, case and
whitespace variations, Unicode compatibility forms and invisible format
characters. It can flag quoted benign discussion and miss paraphrases or
obfuscated attacks. Suspicious instructions remain in sanitized text and are
flagged for review; PII sanitization does not make instructions trustworthy.
Clean results must also remain untrusted. No network test can prove the absence
of all future networking; this implementation has no networking dependencies
and the test suite blocks socket connection, DNS and datagram send attempts.

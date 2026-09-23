# Alem Minutes: local meeting assistant

The user authorized implementation of the requirements in `docs/requirements_ru_kz_en.txt`, direct Python inference with Whisper and Gemma, a small clean architecture refactor, and commits of existing and new work. The follow-up instruction to continue authorizes execution without additional design approval rounds.

## Outcome

A secretary records or imports a Russian, Kazakh or mixed meeting, reviews speaker names and evidence-backed assignments, publishes minutes and tracks completion. Managers receive deadline reminders from a local worker. Inference never sends audio or transcripts to hosted AI services.

## Design

Keep Streamlit as the local presentation layer. `core` owns typed entities and evidence/deadline policy; `application` owns the processing scenario and interfaces; `adapters` owns Whisper, pyannote, Transformers and SQLite. `services.pipeline` composes those dependencies. Models load lazily into the Python process. Target hardware is NVIDIA T4 (user clarification): CUDA 12.6, Gemma FP16, Whisper int8_float16, sequential model release between speech and language phases. CPU is an explicit fallback. Offline mode uses preloaded local model paths.

Persist meetings by stable ID, with task IDs independent of titles, participant mapping, source path and review status. A task retains the cited speaker separately from its responsible person. Human confirmation of a speaker name never assigns every instruction spoken by that person to them. Cache keys are hashes of content and settings; cache reuse never overwrites user edits.

Gemma produces validated JSON in bounded transcript batches. Quotes and timestamps are checked against actual segments. Missing owners and ambiguous dates become review questions. Explicit dates and unambiguous relative days use the supplied meeting date. Failed diarization is visibly reported; the UI never presents it as successful speaker identification.

## Inputs and platform workflow

Support file upload, microphone recording, and a local browser capture page using `getDisplayMedia` plus optional microphone mixing. The page opens validated Teams, Zoom or Meet web links; the operator joins as the named assistant, obtains participant notice/permission, and selects the meeting tab with audio. Authentication, waiting rooms and admission remain explicit operator steps. This is assisted participant capture, not a claim of an autonomous official platform bot. Capture endpoints bind only to loopback, validate host/origin and a random session token, limit payload size, and save audio under generated filenames.

## Review, control and exports

Provide history, searchable transcript, speaker playback, editable participant names and task owner/date/status/urgency/area, and explicit approval before notifications. Dashboard derives overdue status from dates. Export Unicode DOCX/PDF, JSON for EDMS import, and calendar ICS. Provide anonymized export with participant substitutions and contact redaction; manual inspection remains necessary for free-form personal data.

## Notifications and deployment

A standalone worker generates local `.eml` messages for approved assignments and due/overdue reminders with persistent deduplication; explicitly configured internal SMTP can deliver them. No mail is sent during implementation. On-premise instructions cover model preparation, offline environment flags, loopback binding, data deletion and optional container deployment. Full vendor-specific EDMS integration and biometric voice enrollment remain outside the mandatory prototype.

## Acceptance

Behavioral tests cover grounding, owner attribution, date resolution, safe model-path cache keys, meeting isolation, review persistence, notification deduplication, Unicode exports and capture security. Streamlit smoke checks use the real app with local temporary storage. Tests do not pretend to measure model accuracy: real multilingual audio inference requires downloaded model weights and is reported separately.

# Local Minutes Implementation Plan

> Execute inline using the executing-plans workflow; user has authorized continuing implementation and commits.

**Goal:** Deliver the local meeting workflow and provide truthful evidence against the supplied rubric.

**Architecture:** Typed core and grounding rules, injected application scenario, local model and persistence adapters, Streamlit presentation, separate loopback capture server and notification worker.

**Spec:** `docs/superpowers/specs/2026-09-23-local-minutes-design.md`

**Constraints:** Direct Python Whisper/Gemma. No external inference. Preserve existing edits. No real notification sends during development. Python 3.12–3.13 deployment.

## Tasks

- [x] Preserve initial changes in commit 4167a57 (author supplied by user).
- [x] Core/process: tests for invalid evidence, cross-segment timestamps, named vs speaking owner, relative dates and local model paths; implement `core.grounding`, `application.process`, protocols and model adapters.
- [x] Persistence: real SQLite tests for same-title meetings, durable review edits and notification deduplication; implement `adapters.repository` and local mail worker.
- [x] Presentation: replace monolithic app wiring with history, recording, participant confirmation, task review, timeline and exports; exercise with Streamlit AppTest.
- [x] Capture: implement loopback HTTP capture and a browser recorder with validated platform URLs, explicit consent, token validation and audio limits; test HTTP behavior and URL validation.
- [x] Exports: test DOCX fields and Unicode PDF, anonymization and ICS escaping; implement corrected exports and EDMS JSON package.
- [x] Reproducibility: update dependencies and lock, scripts, deployment instructions, sample transcript demo and requirement matrix; run behavioral suite, smoke checks and review; commit all final changes.

## Review focus

Same title must not merge different meetings. Model IDs containing slashes must not become cache paths. Speaker identity must not be confused with responsibility. UI reruns must preserve edits. Notifications must require approval and avoid repeat sends.

## Execution notes

Initial direct-inference/tracker work was preserved in 4167a57. The obsolete llama.cpp tests were replaced by behavioral coverage. User clarified the target is NVIDIA T4: primary dependencies are CUDA 12.6; Gemma chooses FP16 on compute capability 7.5, Whisper defaults to int8_float16. A launcher exposes wheel-provided CUDA libraries before CTranslate2 loads. Heavy models are released across speech/language phases.

Review fixes: Unicode phrase boundaries prevent substring owners/dates; cross-speaker quotes cannot attribute a personal commitment to the first speaker; HF authentication is forwarded to Gemma; notifications revalidate the meeting snapshot under the delivery transaction, preventing stale-recipient sends after saved corrections.

Validation: Python 3.12.14, 30 behavioral/integration tests passed; actual Tesla T4 FP16 matrix operation passed; initial real recording run without Community-1 credentials produced 11 segments and 10 tasks in 204.6 seconds. Authenticated full-pipeline run and final commit are recorded in docs/verification.md.

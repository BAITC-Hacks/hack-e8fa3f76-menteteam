#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export UV_PROJECT_ENVIRONMENT="${XDG_CACHE_HOME:-$HOME/.cache}/uv-envs/alem-minutes"
export UV_LINK_MODE=copy
uv sync --extra diarization
uv run pytest -q

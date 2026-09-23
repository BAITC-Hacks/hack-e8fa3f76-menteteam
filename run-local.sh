#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export UV_PROJECT_ENVIRONMENT="${XDG_CACHE_HOME:-$HOME/.cache}/uv-envs/alem-minutes"
export UV_LINK_MODE=copy
if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required: sudo pacman -S uv" >&2
  exit 1
fi
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg is required: sudo pacman -S ffmpeg" >&2
  exit 1
fi
if [ ! -f .env ]; then cp .env.example .env; fi
uv sync --extra diarization
uv run streamlit run app.py --server.address 0.0.0.0

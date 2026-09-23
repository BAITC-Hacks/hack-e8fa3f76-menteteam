#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
umask 077
if ! command -v uv >/dev/null 2>&1; then
  echo "Install uv: https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi
uv sync --locked --extra ai --extra diarization
exec uv run --no-sync python launch.py

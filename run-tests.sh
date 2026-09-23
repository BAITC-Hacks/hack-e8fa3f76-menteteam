#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
uv sync --locked --group dev --inexact
exec uv run --no-sync pytest -q

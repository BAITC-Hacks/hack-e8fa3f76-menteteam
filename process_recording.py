"""Command-line path for reproducible local inference on a real recording."""
import argparse
import os
import sys
import time
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from services.pipeline import analyze


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path)
    parser.add_argument("--title", default="Совещание")
    parser.add_argument("--date", type=date.fromisoformat, default=None)
    parser.add_argument("--language", choices=["auto", "ru", "kk"], default="auto")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()
    start = time.monotonic()
    result = analyze(str(args.audio), args.title, os.getenv("WHISPER_MODEL", "small"),
                     os.getenv("GEMMA_MODEL", "google/gemma-4-E2B-it"), language=args.language,
                     compute_type=os.getenv("WHISPER_COMPUTE", "int8_float16"),
                     hf_token=os.getenv("HF_TOKEN"), meeting_date=args.date,
                     progress=lambda message: print(message, file=sys.stderr), use_cache=not args.no_cache)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    args.output.chmod(0o600)
    print(f"Saved {len(result.transcript)} segments, {len(result.tasks)} tasks in {time.monotonic()-start:.1f}s",
          file=sys.stderr)


if __name__ == "__main__":
    main()

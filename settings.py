"""Shared local configuration."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = Path(os.getenv("ALEM_DATA_DIR", str(ROOT / "data"))).resolve()
MODEL_CACHE = DATA / "models"
OFFLINE = os.getenv("ALEM_OFFLINE", "0").lower() in {"1", "true", "yes"}
if OFFLINE:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("PYANNOTE_METRICS_ENABLED", "0")

"""Prepare local model directories before moving the app into a closed network."""
import argparse
import os

from dotenv import load_dotenv

load_dotenv()

from settings import MODEL_CACHE, OFFLINE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--whisper", default="small")
    parser.add_argument("--gemma", default="google/gemma-4-E2B-it")
    parser.add_argument("--skip-diarization", action="store_true")
    args = parser.parse_args()
    if OFFLINE:
        parser.error("Temporarily set ALEM_OFFLINE=0 to download weights on the preparation machine.")
    from faster_whisper.utils import download_model
    from huggingface_hub import snapshot_download
    whisper_path = MODEL_CACHE / f"whisper-{args.whisper}"
    download_model(args.whisper, output_dir=str(whisper_path))
    gemma_path = MODEL_CACHE / "gemma"
    snapshot_download(args.gemma, local_dir=gemma_path, token=os.getenv("HF_TOKEN") or None)
    print(f"WHISPER_MODEL={whisper_path}\nGEMMA_MODEL={gemma_path}")
    if not args.skip_diarization:
        diarization_path = MODEL_CACHE / "diarization"
        snapshot_download("pyannote/speaker-diarization-community-1", local_dir=diarization_path,
                          token=os.getenv("HF_TOKEN") or None)
        print(f"DIARIZATION_MODEL={diarization_path}")
    print("ALEM_OFFLINE=1")


if __name__ == "__main__":
    main()

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core libsndfile1 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.12.18
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --extra ai --extra diarization
COPY . .
RUN useradd --create-home --uid 1000 alem && mkdir -p /app/data && chown -R alem:alem /app/data
USER alem
ENV PYTHONDONTWRITEBYTECODE=1 HF_HUB_DISABLE_TELEMETRY=1 PYANNOTE_METRICS_ENABLED=0
CMD ["uv", "run", "--no-sync", "python", "launch.py"]

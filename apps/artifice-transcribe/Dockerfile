FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv

# ffmpeg for audio processing; build-essential for torch/wheels.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
RUN uv sync --frozen --package artifice-transcribe
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "artifice_transcribe.main:app", \
     "--host", "0.0.0.0", "--port", "8000"]

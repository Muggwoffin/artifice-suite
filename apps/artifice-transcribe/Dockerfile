FROM python:3.10-slim
WORKDIR /app/apps/artifice-transcribe

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY apps/artifice-transcribe .
RUN pip install --no-cache-dir -e .

EXPOSE 8000
CMD ["uvicorn", "artifice_transcribe.main:app", "--host", "0.0.0.0", "--port", "8000"]

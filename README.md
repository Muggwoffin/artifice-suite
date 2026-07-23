# PersonaeTranscribe

Speech-to-Text & Diarization API — upload audio, get timestamped speaker-labeled transcripts.

## Quick Start

```bash
# 1. Clone & create virtualenv
python -m venv .venv && .venv\Scripts\activate   # Windows
# source .venv/bin/activate                        # macOS/Linux

# 2. Install dependencies
pip install -e ".[dev]"

# 3. Configure
copy .env.example .env
# Edit .env — set HF_TOKEN for diarization

# 4. Run
python -m app.main
# Server starts on http://127.0.0.1:8000
# Swagger UI at http://127.0.0.1:8000/docs
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/transcribe` | Upload audio, returns `202` with `job_id` |
| `GET` | `/api/v1/jobs/{job_id}` | Job status & progress |
| `GET` | `/api/v1/jobs/{job_id}/transcript` | Structured transcript |
| `PATCH` | `/api/v1/jobs/{job_id}/speakers` | Rename speaker labels |
| `GET` | `/api/v1/jobs/{job_id}/export?format=` | Export as `json`/`srt`/`vtt`/`txt` |
| `DELETE` | `/api/v1/jobs/{job_id}` | Delete job & audio |
| `GET` | `/health` | Health check |

## Architecture

```
app/
├── main.py                 # FastAPI app + lifespan
├── config.py               # Settings from env
├── db/
│   ├── models.py           # SQLAlchemy ORM (Job, Segment, SpeakerMapping)
│   └── session.py          # Async engine + session factory
├── schemas/
│   └── transcription.py    # Pydantic request/response schemas
├── services/
│   ├── transcription.py    # WhisperX engine wrapper
│   └── exports.py          # SRT/VTT/TXT/JSON generators
└── api/v1/
    └── routes.py           # All API endpoints + background worker
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HF_TOKEN` | *(required for diarization)* | Hugging Face access token |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/transcribe.db` | Database connection string |
| `WHISPER_MODEL` | `base` | Whisper model size (`tiny`/`base`/`small`/`medium`/`large-v2`/`large-v3`) |
| `DEVICE` | `auto` | Compute device (`cpu`/`cuda`/`auto`) |
| `UPLOAD_DIR` | `./uploads` | Audio file storage directory |

## Testing

```bash
# Start server in one terminal
python -m app.main

# Run verification script
python tests/test_api.py path/to/audio.wav
```

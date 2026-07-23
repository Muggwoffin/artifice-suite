# AGENTS.md

## Status

FastAPI backend for speech-to-text + speaker diarization. Uses WhisperX (Whisper + PyAnnote).

## Dev Commands

```bash
pip install -e ".[dev]"        # install with dev extras
python -m app.main              # run server on :8000
python tests/test_api.py        # e2e verification (needs audio arg for full test)
ruff check .                    # lint
ruff format .                   # format
```

## Architecture

- **Entry point:** `app/main.py` → FastAPI app with lifespan
- **Routes:** `app/api/v1/routes.py` — all endpoints + background worker
- **Engine:** `app/services/transcription.py` — WhisperX wrapper (lazy-loads models, frees VRAM after each job)
- **Exports:** `app/services/exports.py` — SRT/VTT/TXT/JSON formatters
- **ORM:** `app/db/models.py` — `TranscriptionJob`, `TranscriptSegment`, `SpeakerMapping`
- **Config:** `app/config.py` — pydantic-settings, reads `.env`
- **DB:** SQLite by default (`./data/transcribe.db`), async via `aiosqlite`

## Gotchas

- **HF_TOKEN required** for diarization — set in `.env`, no fallback
- **VRAM management:** engine calls `torch.cuda.empty_cache()` + `gc.collect()` after every job. Model is a module-level singleton; do not import `whisperx` at module level (lazy-loaded in `_ensure_models`)
- **Background tasks:** uses FastAPI `BackgroundTasks` (in-process). For production scale, swap to Celery/RQ — the `_run_transcription` function in `routes.py` is the unit of work
- **Audio uploads:** stored at `uploads/{job_id}_{filename}`, cleaned up on `DELETE`
- **DB tables:** auto-created on startup via `Base.metadata.create_all`
- **Speaker mapping:** auto-populated during diarization, PATCH-able via API

## Project Layout

```
app/
├── main.py                 # app factory + lifespan
├── config.py               # Settings
├── db/
│   ├── models.py           # ORM models
│   └── session.py          # async engine
├── schemas/
│   └── transcription.py    # Pydantic schemas
├── services/
│   ├── transcription.py    # WhisperX engine
│   └── exports.py          # format generators
└── api/v1/
    └── routes.py           # endpoints + worker
```

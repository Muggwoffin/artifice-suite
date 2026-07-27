# ArtificeTranscribe

> High-Precision Speech-to-Text & Speaker Diarization Platform with Oral History & Archival Standards

ArtificeTranscribe is an open-source, production-grade transcription and speaker diarization engine designed for researchers, archivists, oral historians, journalists, and power users. Built on top of **WhisperX** (OpenAI Whisper + PyAnnote audio diarization), it bridges state-of-the-art AI speech recognition with professional archival workflows, rigorous metadata management, and publication-ready export standards.

---

## 🏛️ Philosophy

1. **Uncompromising Precision:** Audio transcriptions are only as good as their timestamps. ArtificeTranscribe uses forced word-level alignment to lock every word to exact audio offsets, eliminating drift and guesswork.
2. **Archival Integrity & Interoperability:** Modern AI tools often discard context. ArtificeTranscribe embraces established digital humanities and oral history standards—supporting **OHMS (Oral History Metadata Synchronizer)** and **TEI (Text Encoding Initiative)** XML exports alongside standard subtitles and documents.
3. **Resource Efficiency & Privacy:** Designed to run locally with strict VRAM hygiene (automatic garbage collection and CUDA cache clearing after every job), protecting sensitive recordings while maintaining hardware health.
4. **Frictionless Workflow:** Featuring a zero-build-step responsive web SPA paired with an asynchronous FastAPI backend, providing both an intuitive user interface and a robust REST API.

---

## 🌟 Key Features

### 🎙️ Advanced Transcription & Diarization Engine
- **WhisperX Integration:** Combines robust multilingual Whisper transcription models with PyAnnote speaker diarization.
- **Forced Word-Level Alignment:** Dynamic language detection per segment with cached alignment models for high-accuracy timing.
- **Custom Vocabulary / Initial Prompting:** Guide Whisper toward domain-specific terminology, acronyms, and proper nouns.
- **VRAM Lifecycle Management:** Automatic singleton model caching with aggressive cleanup (`torch.cuda.empty_cache()` + `gc.collect()`) post-job.

### 📚 Oral History & Metadata Management
- Record rich interview metadata directly linked to jobs:
  - Interviewee & Interviewer names
  - Interview Date & Location
  - Project Name & Collection ID
  - Access Restrictions & archival notes

### 📤 Comprehensive Export Ecosystem
Export your transcripts in 8 distinct formats tailored for any downstream workflow:
- **JSON:** Structured machine-readable segment data with word timestamps and speaker mappings.
- **SRT & VTT:** Standard subtitle formats for video production and closed captioning.
- **TXT:** Clean plain-text speaker-grouped transcripts.
- **Markdown (`.md`):** Formatted transcripts ready for wikis, static sites, or note-taking apps.
- **PDF:** Formatted printable document export (via `fpdf2`).
- **OHMS XML:** Oral History Metadata Synchronizer standard for digital archives.
- **TEI XML:** Text Encoding Initiative standard for digital scholarly editions.

### 🖥️ Modern Web UI & Editing Suite
- **Responsive SPA:** Vanilla JavaScript/CSS interface (zero build step) served directly by FastAPI.
- **Light & Dark Themes:** LudwigLang-inspired editorial design system with paper-and-ink tactile aesthetics.
- **Audio Synchronisation:** Interactive audio player with real-time transcript segment highlighting.
- **Speaker Mapping:** Easily rename auto-detected speaker labels (`SPEAKER_00`, `SPEAKER_01`) to human names across the entire job.
- **Interactive Editing:** Contenteditable transcript segments with change persistence, tag support, and revision/diff views.

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- PyTorch (compatible with your CPU/CUDA setup)
- **Hugging Face Token (`HF_TOKEN`):** Required for PyAnnote speaker diarization models. Accept user conditions on Hugging Face for `pyannote/speaker-diarization-3.1` and `pyannote/segmentation-3.0`.

### Installation

```bash
# 1. Clone repository & create virtual environment
python -m venv .venv
.venv\Scripts\activate   # Windows (.venv/bin/activate on macOS/Linux)

# 2. Install package in editable mode with dev extras
pip install -e ".[dev]"

# 3. Configure environment variables
copy .env.example .env   # cp .env.example .env on Linux/macOS
# Edit .env and insert your HF_TOKEN
```

### Running the Application

```bash
# Start server (opens web UI at http://127.0.0.1:8000)
python -m app.main

# Or use the Windows shortcut script
start.bat
```

- **Web UI:** `http://127.0.0.1:8000`
- **Interactive API Docs (Swagger UI):** `http://127.0.0.1:8000/docs`

---

## ⚙️ Environment Variables

Configure via your `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `HF_TOKEN` | *(required)* | Hugging Face access token for speaker diarization |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/transcribe.db` | Async SQLite database connection string |
| `WHISPER_MODEL` | `base` | Whisper model size (`tiny`, `base`, `small`, `medium`, `large-v2`, `large-v3`) |
| `DEVICE` | `auto` | Compute device (`cpu`, `cuda`, `auto`) |
| `UPLOAD_DIR` | `./uploads` | Temporary storage directory for uploaded audio files |

---

## 🔌 API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/transcribe` | Upload audio file with optional metadata & options (returns `202 Accepted` with `job_id`) |
| `GET` | `/api/v1/jobs/{job_id}` | Check job status, progress percentage, and oral history metadata |
| `GET` | `/api/v1/jobs/{job_id}/transcript` | Retrieve structured timestamped transcript segments & tags |
| `PATCH` | `/api/v1/jobs/{job_id}/transcript` | Edit transcript segment text with change tracking |
| `GET` | `/api/v1/jobs/{job_id}/speakers` | Get speaker label-to-name mappings |
| `PATCH` | `/api/v1/jobs/{job_id}/speakers` | Rename speaker labels (e.g., `SPEAKER_00` → `Dr. Jane Doe`) |
| `GET` | `/api/v1/jobs/{job_id}/export` | Export transcript (`format=json\|srt\|vtt\|txt\|md\|pdf\|ohms\|tei`) |
| `DELETE` | `/api/v1/jobs/{job_id}` | Delete transcription job, metadata, database records, and uploaded audio file |
| `GET` | `/health` | Application health check |

---

## 🏗️ Project Architecture

```
app/
├── main.py                 # FastAPI application factory, lifespan, and static routing
├── config.py               # Pydantic settings parser (`.env` integration)
├── static/                 # Frontend SPA (Vanilla HTML, CSS design system, JS client)
│   ├── index.html          # Main application shell
│   ├── css/app.css         # LudwigLang-inspired editorial themes
│   └── js/app.js           # Audio player sync, API client, interactive editor
├── db/
│   ├── models.py           # SQLAlchemy ORM models (Jobs, Segments, Speakers, Edits)
│   └── session.py          # Async SQLAlchemy engine & session factory
├── schemas/
│   └── transcription.py    # Pydantic request/response validation schemas
├── services/
│   ├── transcription.py    # WhisperX engine wrapper & VRAM manager
│   └── exports.py          # Multi-format formatters (SRT, VTT, OHMS, TEI, PDF, etc.)
└── api/v1/
    └── routes.py           # REST endpoints & background worker coordination
```

---

## 🧪 Testing & Verification

```bash
# Run backend linters & formatters
ruff check .
ruff format .

# Run end-to-end API verification (requires an audio file argument)
python tests/test_api.py path/to/sample.wav
```

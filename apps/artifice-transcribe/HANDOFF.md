# Handoff Report: Load Models / Health Check Failure

## Date: 2026-07-23

## Summary

The "Load Models" button in the health panel fails with a "Not Found" error. Investigation
reveals multiple compounding issues, the most critical being a broken API import and a missing
`.env` file. Below is a full accounting of findings and recommended fixes.

---

## Issue 1 (CRITICAL): `whisperx.DiarizationPipeline` does not exist

**File:** `app/services/transcription.py:64`

The engine calls `whisperx.DiarizationPipeline(...)`, but this attribute does not exist in
whisperx 3.8.6 (the installed version). The class lives at `whisperx.diarize.DiarizationPipeline`.

This causes `_ensure_models()` to raise an `AttributeError` every time models are loaded,
which means:
- **Preload fails** with error: `module 'whisperx' has no attribute 'DiarizationPipeline'`
- **Transcription fails** for the same reason
- The health check returns `state: "failed"` and `last_error` with this message

**Fix:** Change line 64 from:
```python
self._diarize_model = whisperx.DiarizationPipeline(
    use_auth_token=self._hf_token, device=self._device
)
```
to:
```python
from whisperx.diarize import DiarizationPipeline
self._diarize_model = DiarizationPipeline(
    use_auth_token=self._hf_token, device=self._device
)
```

---

## Issue 2 (CRITICAL): No `.env` file exists

The `.env` file does not exist. Only `.env.example` is present. This means:
- `HF_TOKEN` defaults to `""` (empty string)
- `WHISPER_MODEL` defaults to `"base"` (not the intended `"large-v3"`)
- `DEVICE` defaults to `"auto"`

Without a valid HuggingFace token, the diarization model cannot authenticate to download
the pyannote models, even if the import is fixed.

**Fix:** Create `.env` from `.env.example`:
```bash
cp .env.example .env
# Then edit .env and set a valid HF_TOKEN=hf_...
```

**Note:** `.env.example` contains what appears to be a real HuggingFace token
(`your_hf_token_here`). This is a **security concern** — the example
file should use a placeholder like `hf_YOUR_TOKEN_HERE`.

---

## Issue 3: "Not Found" on the Load Models button

The `POST /api/v1/health/preload` endpoint **does exist** and **works correctly** when tested
via `TestClient`:

```python
POST /api/v1/health/preload → 200 {"ok": false, "error": "module 'whisperx' has no attribute 'DiarizationPipeline'"}
```

Routes are properly registered (confirmed via `app.routes`). The JS code correctly calls
`api('/health/preload', { method: 'POST' })` which resolves to `/api/v1/health/preload`.

**Possible causes for "Not Found":**

1. **Browser cache:** The old JS (before the preload endpoint was added) may be cached.
   Hard refresh (`Ctrl+Shift+R`) may not have cleared the disk cache.

2. **Uvicorn reload race:** The `reload_excludes` pattern in `main.py:74` includes broad
   globs (`"*.db"` etc.) — though these shouldn't affect route registration, there may be
   a timing issue where uvicorn restarts but the new app instance hasn't fully mounted routes
   before the browser makes its request.

3. **Server not actually restarted:** The user may have opened a new browser tab while the
   old server process was still serving stale routes. The `start.bat` opens a browser after
   a 3-second delay which may not be enough time for uvicorn to fully start.

**Debugging steps:**
- Open `http://127.0.0.1:8000/docs` in the browser and check if `POST /api/v1/health/preload`
  appears in the FastAPI Swagger UI.
- Check the uvicorn terminal output for startup errors.
- Try `curl -X POST http://127.0.0.1:8000/api/v1/health/preload` directly.

---

## Issue 4: ffmpeg / torchcodec warnings

ffmpeg IS installed at:
```
C:\Users\mjcas\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_...\ffmpeg.EXE
```

However, `torchcodec` cannot find its DLLs. This is a **PATH vs DLL search path issue** —
ffmpeg is on the system PATH but its DLLs are not in the Windows DLL search path that
torchcodec uses. This produces verbose warnings on every model load but does **not** block
transcription (whisperx falls back to its own audio loading).

**Fix (optional):** Add ffmpeg's `bin/` directory to the system PATH, or reinstall ffmpeg
via a method that registers DLLs properly. Alternatively, suppress the warning by setting
an environment variable or filtering the warning in `transcription.py`.

---

## Issue 5: `.env.example` leaks a real HuggingFace token

**File:** `.env.example:2`

The file contains `your_hf_token_here` — this looks like a real token,
not a placeholder. If this is a valid token, it should be rotated immediately and replaced
with a placeholder.

---

## Files to Modify

| File | Change |
|------|--------|
| `app/services/transcription.py` | Fix `DiarizationPipeline` import (line 64) |
| `.env` | **Create** with valid `HF_TOKEN` and `WHISPER_MODEL=large-v3` |
| `.env.example` | Replace real token with placeholder |
| `app/static/js/app.js` | Consider adding cache-busting query param to `api()` calls |
| `start.bat` | Increase browser launch delay from 3s to 5s |

---

## Environment Info

- **Python:** 3.12
- **whisperx:** 3.8.6
- **torch:** 2.8.0+cpu (no CUDA)
- **ffmpeg:** 8.1.2 (installed via winget, on PATH)
- **FastAPI:** latest (from pyproject.toml)
- **OS:** Windows (win32)

---

## Recommended Fix Order

1. Create `.env` from `.env.example` with a valid `HF_TOKEN`
2. Fix `whisperx.DiarizationPipeline` import in `transcription.py`
3. Verify the endpoint works: `python -c "from app.main import app; from fastapi.testclient import TestClient; print(TestClient(app).post('/api/v1/health/preload').json())"`
4. Restart server, confirm `POST /api/v1/health/preload` appears in Swagger at `/docs`
5. Test the Load Models button in the browser
6. Rotate the leaked HF token in `.env.example`

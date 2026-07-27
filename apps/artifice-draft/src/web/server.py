"""FastAPI backend for the ArtificeDraft web frontend.

Additive, not a replacement: `src/gui.py` and the CLI entry point in
`scripts/run_edit.py` are untouched, and every pipeline module this imports
(`doc_parser`, `llm_client`, `doc_writer`, `review`, `changelog`) is exactly
what the tkinter build already uses. The only new code is the adapter in
`runtime.py` and this HTTP/SSE layer over it.

Progress reaches the browser as Server-Sent Events, same choice and same
reasoning as the OCR Pipeline tool's web build: one-directional is all a
progress feed needs, and `EventSource` reconnects on its own.
"""

from __future__ import annotations

import asyncio
import json
import queue
import socket
import webbrowser
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .runtime import (
    config_from_settings,
    save_settings,
    serialize_progress,
    serialize_review_items,
    serialize_settings,
    serialize_status,
    state,
)

from src.style_guides import delete_custom_guide, list_guides, save_custom_guide
from src.style_guides.base import StyleGuide

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="ArtificeDraft")


# --------------------------------------------------------------------------- #
# request models
# --------------------------------------------------------------------------- #

class SettingsPatch(BaseModel):
    llm_provider: str | None = None
    editing_style: str | None = None
    custom_system_prompt: str | None = None
    style_guide: str | None = None
    export_format: str | None = None
    batch_size: int | None = None
    temperature: float | None = None
    enable_review: bool | None = None
    author_name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    model_name: str | None = None
    vision_enabled: bool | None = None


class ReviewDecisionIn(BaseModel):
    paragraph_index: int
    approved: bool
    replacement_text: str | None = None


class ReviewSubmitRequest(BaseModel):
    decisions: list[ReviewDecisionIn]


class GuideImportRequest(BaseModel):
    url: str


class GuideImportTextRequest(BaseModel):
    text: str


class GuideSaveRequest(BaseModel):
    name: str
    guide: dict


# --------------------------------------------------------------------------- #
# settings
# --------------------------------------------------------------------------- #

@app.get("/api/settings")
def get_settings() -> dict:
    return serialize_settings(config_from_settings())


@app.post("/api/settings")
def update_settings(patch: SettingsPatch) -> dict:
    data = {k: v for k, v in patch.model_dump().items() if v is not None}
    save_settings(data)
    return serialize_settings(config_from_settings())


@app.get("/api/style-guides")
def get_style_guides() -> dict:
    return {"guides": list_guides()}


@app.post("/api/style-guides/preview")
def preview_guide(req: GuideImportRequest) -> dict:
    """Scrape a URL and parse it into a StyleGuide without saving."""
    from src.style_guides.scraper import preview_guide_from_url
    from src.web.runtime import config_from_settings

    cfg = config_from_settings()
    try:
        guide = preview_guide_from_url(req.url, cfg)
    except (ValueError, ImportError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"guide": guide.to_dict()}


@app.post("/api/style-guides/preview-text")
def preview_guide_text(req: GuideImportTextRequest) -> dict:
    """Parse pasted text into a StyleGuide without saving."""
    from src.style_guides.scraper import preview_guide_from_text
    from src.web.runtime import config_from_settings

    cfg = config_from_settings()
    try:
        guide = preview_guide_from_text(req.text, cfg)
    except (ValueError, ImportError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"guide": guide.to_dict()}


@app.post("/api/style-guides/preview-file")
async def preview_guide_file(file: UploadFile = File(...)) -> dict:
    """Upload a .docx or .pdf file and parse it into a StyleGuide."""
    from src.style_guides.scraper import preview_guide_from_file
    from src.web.runtime import config_from_settings

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    lower = file.filename.lower()
    if not (lower.endswith(".docx") or lower.endswith(".pdf")):
        raise HTTPException(status_code=400, detail="Only .docx and .pdf files are supported")

    import tempfile
    data = await file.read()
    suffix = ".docx" if lower.endswith(".docx") else ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    cfg = config_from_settings()
    try:
        guide = preview_guide_from_file(tmp_path, cfg)
    except (ValueError, ImportError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        import os
        os.unlink(tmp_path)

    return {"guide": guide.to_dict()}


@app.post("/api/style-guides/save")
def save_guide(req: GuideSaveRequest) -> dict:
    """Save a scraped/edited StyleGuide as a custom guide."""
    from src.web.runtime import config_from_settings

    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Guide name is required")
    guide = StyleGuide.from_dict(req.guide)
    guide.name = name
    save_custom_guide(name, guide)
    return {"guides": list_guides(), "saved": name}


@app.delete("/api/style-guides/{name}")
def delete_guide(name: str) -> dict:
    """Delete a custom style guide by name."""
    deleted = delete_custom_guide(name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Guide '{name}' not found")
    return {"guides": list_guides(), "deleted": name}


# --------------------------------------------------------------------------- #
# document upload + run
# --------------------------------------------------------------------------- #

@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    if not (file.filename or "").lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only .docx files are supported")

    data = await file.read()
    try:
        doc = state.add_document(file.filename, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not doc.paragraphs:
        raise HTTPException(status_code=400, detail="No content found in the document")

    return serialize_status(doc)


@app.get("/api/run/{doc_id}/status")
def get_status(doc_id: str) -> dict:
    doc = state.get(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Unknown document")
    return serialize_status(doc)


@app.post("/api/run/{doc_id}/start")
def start_run(doc_id: str) -> dict:
    try:
        doc = state.start_run(doc_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown document")
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return serialize_status(doc)


async def _event_stream(doc_id: str):
    """Drain one document's progress queue and forward each event as an SSE
    frame, stopping once the run reaches a state the client must act on
    (awaiting_review) or a terminal state (done/error).

    `queue.Queue.get` is blocking, so it runs via `asyncio.to_thread` rather
    than stalling the event loop. A 30s timeout turns into a heartbeat
    comment line (`EventSource` ignores lines starting with `:` natively) so
    the connection doesn't look dead during a slow LLM batch.
    """
    doc = state.get(doc_id)
    if doc is None:
        return

    terminal = {"awaiting_review", "done", "error"}
    while True:
        try:
            progress = await asyncio.to_thread(doc.events.get, True, 30)
        except queue.Empty:
            yield ": heartbeat\n\n"
            if doc.stage in terminal:
                break
            continue

        yield f"data: {json.dumps(serialize_progress(progress))}\n\n"
        if progress.stage in terminal:
            break


@app.get("/api/run/{doc_id}/events")
async def run_events(doc_id: str):
    if state.get(doc_id) is None:
        raise HTTPException(status_code=404, detail="Unknown document")
    return StreamingResponse(
        _event_stream(doc_id), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/run/{doc_id}/review")
def get_review(doc_id: str) -> dict:
    doc = state.get(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Unknown document")
    if doc.stage != "awaiting_review":
        raise HTTPException(
            status_code=409,
            detail=f"Document is not awaiting review (stage={doc.stage})",
        )
    return {"items": serialize_review_items(doc)}


@app.post("/api/run/{doc_id}/review")
def submit_review(doc_id: str, req: ReviewSubmitRequest) -> dict:
    try:
        doc = state.submit_review(doc_id, [d.model_dump() for d in req.decisions])
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown document")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return serialize_status(doc)


@app.get("/api/run/{doc_id}/download")
def download(doc_id: str):
    doc = state.get(doc_id)
    if doc is None or doc.output_path is None:
        raise HTTPException(status_code=404, detail="No output file yet")
    return FileResponse(doc.output_path, filename=doc.output_path.name)


# --------------------------------------------------------------------------- #
# static frontend
# --------------------------------------------------------------------------- #

@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# --------------------------------------------------------------------------- #
# bootstrap
# --------------------------------------------------------------------------- #

def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(port: int, *, timeout: float = 10.0) -> bool:
    """Block until something is actually listening on `port`.

    `uvicorn.run()` starts in a background thread and takes a moment to bind
    its socket — opening a window at the target URL immediately races that.
    Same fix, same reasoning, as the OCR Pipeline tool's web build; see that
    project's `web/server.py` for the live bug this caught there.
    """
    import time as _time

    deadline = _time.monotonic() + timeout
    while _time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.2)
            try:
                probe.connect(("127.0.0.1", port))
                return True
            except OSError:
                _time.sleep(0.1)
    return False


def main() -> None:
    """Start the server and open a window onto it.

    Prefers a native pywebview window; falls back to the system browser if
    pywebview is not installed or `--browser` is passed.
    """
    import argparse
    import sys as _sys
    import threading

    # pythonw.exe has sys.stdout and sys.stderr set to None.  uvicorn's
    # logging formatter calls sys.stdout.isatty(), which blows up with an
    # AttributeError when stdout is None.  Seed them with /dev/null so the
    # server can start; the browser / pywebview window is the real UI.
    if _sys.stdout is None:
        _sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if _sys.stderr is None:
        _sys.stderr = open(os.devnull, "w", encoding="utf-8")

    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", action="store_true",
                       help="Open in the default browser instead of a native window")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    port = args.port or _free_port()
    url = f"http://127.0.0.1:{port}"

    server_thread = threading.Thread(
        target=lambda: uvicorn.run(app, host="127.0.0.1", port=port,
                                   log_level="warning"),
        daemon=True,
    )
    server_thread.start()
    if not _wait_for_server(port):
        print(f"WARNING: server did not respond on port {port} within 10s; "
              f"opening the window anyway, but it may show a connection error.")

    use_browser = args.browser
    if not use_browser:
        try:
            import webview  # noqa: F401
        except ImportError:
            use_browser = True

    if use_browser:
        webbrowser.open(url)
        print(f"ArtificeDraft running at {url}  (Ctrl+C to stop)")
        try:
            server_thread.join()
        except KeyboardInterrupt:
            pass
        return

    import webview

    window = webview.create_window("ArtificeDraft", url, width=1100, height=800)
    webview.start()


if __name__ == "__main__":
    main()

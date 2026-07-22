"""FastAPI backend for the web frontend.

This is additive, not a replacement: `gui/app.py` and everything under
`gui/views/` are untouched, and every core module this imports
(`jobs`, `pipeline`, `history`, `tropy`, `config`) is exactly what the tkinter
build already uses. The only new code is the adapter in `runtime.py` and this
HTTP/SSE layer over it.

Progress reaches the browser as Server-Sent Events rather than WebSockets:
it's one-directional (server -> client), which is all a progress feed needs,
and a browser's built-in `EventSource` reconnects on its own if the connection
drops — no client-side reconnect logic to write.
"""

import asyncio
import json
import os
import queue
import socket
import sys
import webbrowser
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import config
from .._prompts import DOCUMENT_TYPES
from ..jobs import STAGES
from ..tropy import TropyProject, pages_to_job_items, recent_projects, write_manifest
from .runtime import (
    pdf_export_state,
    render_page_image,
    save_raw_text,
    serialize_event,
    serialize_history_item,
    serialize_history_item_detail,
    serialize_history_run,
    serialize_item_preview,
    start_pdf_export,
    state,
)

_IMAGE_PASSTHROUGH_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="OCR Pipeline")


# --------------------------------------------------------------------------- #
# request/response models
# --------------------------------------------------------------------------- #

class AddPathsRequest(BaseModel):
    paths: list[str]


class RemoveRequest(BaseModel):
    ids: list[str]


class StartRunRequest(BaseModel):
    stages: list[str]
    output_dir: str = "output"
    force: bool = False


class SkipRequest(BaseModel):
    id: str


class RawTextRequest(BaseModel):
    text: str


class TropyBrowseRequest(BaseModel):
    project: str
    list_id: int | None = None
    tag: str | None = None
    item_ids: list[int] | None = None


class TropySendRequest(BaseModel):
    project: str
    item_ids: list[str] | None = None  # queue-item ids; None = all eligible
    targets: list[str]
    stage: str = "cleaned"


class TropySendWriteRequest(TropySendRequest):
    make_backup: bool = True


class PdfExportRequest(BaseModel):
    folder: str
    stage: str = "cleaned"
    structure: bool = True
    output: str | None = None
    manifest: str | None = None


# --------------------------------------------------------------------------- #
# queue
# --------------------------------------------------------------------------- #

@app.get("/api/queue")
def get_queue() -> dict:
    return {"items": state.queue_snapshot(), "status": state.status()}


@app.post("/api/queue/add-paths")
def add_paths(req: AddPathsRequest) -> dict:
    added = state.add_paths(req.paths)
    return {"added": len(added), "items": state.queue_snapshot()}


@app.post("/api/queue/remove")
def remove_items(req: RemoveRequest) -> dict:
    removed = state.remove(req.ids)
    return {"removed": removed, "items": state.queue_snapshot()}


@app.post("/api/queue/clear")
def clear_queue() -> dict:
    state.clear()
    return {"items": []}


@app.get("/api/queue/{item_id}/preview")
def queue_item_preview(item_id: str) -> dict:
    """Raw/Cleaned/Translated text + diff ranges for one in-memory queue item.

    This reads whatever `item.results` the runner already holds — nothing
    here touches disk, which is why it only works for items still in this
    server's queue. A finished run that has since been cleared is in
    `/api/history/*` instead.
    """
    item = state.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found in the queue")
    return serialize_item_preview(item)


@app.get("/api/queue/{item_id}/image")
def queue_item_image(item_id: str):
    """The source scan for one queue item, for Preview's zoom/pan image pane.

    jpg/png are already browser-renderable and pass through unchanged
    (`FileResponse`, no decode/re-encode). tiff/pdf go through
    `render_page_image`, which converts to PNG — for a PDF this renders only
    the single page `item.page` already points at, never the whole document.
    """
    item = state.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found in the queue")

    suffix = Path(item.path).suffix.lower()
    media_type = _IMAGE_PASSTHROUGH_TYPES.get(suffix)
    if media_type:
        return FileResponse(item.path, media_type=media_type)

    try:
        png_bytes = render_page_image(item)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return Response(content=png_bytes, media_type="image/png")


@app.post("/api/queue/{item_id}/raw-text")
def save_raw_text_route(item_id: str, req: RawTextRequest) -> dict:
    """Manual correction to one item's raw OCR text — see `save_raw_text`'s
    docstring in runtime.py for what this does and does not touch on disk."""
    item = state.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found in the queue")
    return save_raw_text(item, req.text)


# --------------------------------------------------------------------------- #
# run control
# --------------------------------------------------------------------------- #

@app.post("/api/run/start")
def start_run(req: StartRunRequest) -> dict:
    stages = {s for s in req.stages if s in STAGES}
    try:
        state.start_run(stages=stages, output_dir=req.output_dir, force=req.force)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True}


@app.post("/api/run/pause")
def pause_run() -> dict:
    state.pause()
    return {"ok": True}


@app.post("/api/run/resume")
def resume_run() -> dict:
    state.resume()
    return {"ok": True}


@app.post("/api/run/cancel")
def cancel_run() -> dict:
    state.cancel()
    return {"ok": True}


@app.post("/api/run/skip")
def skip_item(req: SkipRequest) -> dict:
    ok = state.skip(req.id)
    return {"ok": ok}


@app.get("/api/run/status")
def run_status() -> dict:
    return state.status()


# --------------------------------------------------------------------------- #
# events (SSE)
# --------------------------------------------------------------------------- #

async def _event_stream():
    """Drain the runner's queue.Queue and forward each event as an SSE frame.

    `queue.Queue.get` is blocking, so it runs in a worker thread via
    `asyncio.to_thread` rather than stalling the event loop. A short timeout
    turns into a heartbeat comment (a line starting with `:`, which
    `EventSource` ignores natively — no client-side handling needed), which is
    also how the loop keeps checking for a runner that doesn't exist yet, or a
    new one started after the previous run finished.

    One caveat worth being explicit about: this drains one shared
    `queue.Queue` per runner. Two browser tabs open at once would each get
    only *some* of the events, because `Queue.get()` removes what it reads.
    Fine for one person in one tab, which is the spike's scope; a multi-tab
    build would need to fan events out to a list of per-connection queues
    instead of reading the runner's queue directly.
    """
    while True:
        runner = state.runner
        if runner is None:
            await asyncio.sleep(0.3)
            yield ": waiting for a run to start\n\n"
            continue

        try:
            event = await asyncio.to_thread(runner.events.get, True, 1.0)
        except queue.Empty:
            yield ": heartbeat\n\n"
            continue

        if event.kind == "item_finished":
            state.record_finished_items()
        if event.kind == "run_finished":
            state.finish_run(event.payload)

        yield f"data: {json.dumps(serialize_event(event))}\n\n"


@app.get("/api/events")
async def events():
    return StreamingResponse(_event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                     "X-Accel-Buffering": "no"})


# --------------------------------------------------------------------------- #
# settings
# --------------------------------------------------------------------------- #

_CONFIG_KEYS = (
    "lm_studio_url", "output_dir", "cleanup_model", "translate_model",
    "ocr_model", "document_type", "max_ocr_workers", "chunk_max_tokens",
    "resume", "confidence_enabled", "ollama_think",
)


@app.get("/api/config")
def get_config() -> dict:
    return {k: config.get(k) for k in _CONFIG_KEYS}


@app.post("/api/config")
def set_config(overrides: dict[str, Any]) -> dict:
    allowed = {k: v for k, v in overrides.items() if k in config.PERSISTED_KEYS}
    config.apply_overrides(allowed)
    config.save_user_settings(allowed)
    return {"ok": True}


@app.post("/api/config/reset")
def reset_config() -> dict:
    """Discards overrides (in-memory and saved) back to built-in defaults.

    Mirrors Settings' "Reset to Defaults" on the desktop build. Does not
    touch `configs/default.yaml` or environment overrides — those still take
    effect, same as `config.load_config()` always applies them.
    """
    config.reset()
    config.load_config()
    return {k: config.get(k) for k in _CONFIG_KEYS}


@app.get("/api/document-types")
def document_types() -> dict:
    return {"types": DOCUMENT_TYPES}


@app.get("/api/health")
def health_check() -> dict:
    """Same checks Settings' pre-flight button runs on the desktop build."""
    from ..utils import check_lm_studio, check_ollama

    lm_err = check_lm_studio()
    models = [config.get("cleanup_model"), config.get("translate_model")]
    ollama_errors = check_ollama(models)
    ollama_reachable = not any("Cannot reach" in e for e in ollama_errors)

    return {
        "lm_studio": {"ok": lm_err is None, "detail": lm_err,
                     "url": config.get("lm_studio_url")},
        "ollama": {"ok": ollama_reachable,
                  "detail": None if ollama_reachable else ollama_errors[0]},
        "models": [
            {"name": m, "ok": ollama_reachable and not any(m in e for e in ollama_errors)}
            for m in models
        ],
    }


# --------------------------------------------------------------------------- #
# history
# --------------------------------------------------------------------------- #

@app.get("/api/history/runs")
def history_runs() -> dict:
    return {"runs": [serialize_history_run(r) for r in state.history.list_runs()]}


@app.get("/api/history/runs/{run_id}/items")
def history_run_items(run_id: int) -> dict:
    return {"items": [serialize_history_item(r) for r in state.history.list_items(run_id)]}


@app.get("/api/history/items/{item_id}")
def history_item_detail(item_id: int) -> dict:
    row = state.history.get_item(item_id)
    if row is None:
        raise HTTPException(status_code=404, detail="History item not found")
    return serialize_history_item_detail(row)


@app.get("/api/history/search")
def history_search(q: str = "") -> dict:
    if not q.strip():
        return {"items": []}
    return {"items": [serialize_history_item(r) for r in state.history.search_items(q)]}


@app.delete("/api/history/runs/{run_id}")
def history_delete_run(run_id: int) -> dict:
    """Removes only the history record — output files on disk are untouched."""
    state.history.delete_run(run_id)
    return {"ok": True}


# --------------------------------------------------------------------------- #
# analytics
# --------------------------------------------------------------------------- #

@app.get("/api/analytics/stats")
def analytics_stats() -> dict:
    return state.history.stats()


# --------------------------------------------------------------------------- #
# tropy
# --------------------------------------------------------------------------- #

@app.get("/api/tropy/recent")
def tropy_recent() -> dict:
    return {"projects": [str(p) for p in recent_projects()]}


@app.post("/api/tropy/browse")
def tropy_browse(req: TropyBrowseRequest) -> dict:
    try:
        with TropyProject(req.project) as proj:
            if req.list_id is not None:
                ids = proj.item_ids_in_list(req.list_id)
            elif req.tag:
                ids = proj.item_ids_with_tag(req.tag)
            else:
                ids = req.item_ids

            return {
                "project": proj.name,
                "lists": [
                    {"list_id": l.list_id, "name": l.name,
                     "parent_id": l.parent_id, "depth": l.depth,
                     "item_count": l.item_count}
                    for l in proj.lists()
                ],
                "tags": [{"name": n, "count": c} for n, c in proj.tags() if c],
                "items": [
                    {"item_id": i.item_id, "title": i.title,
                     "photo_count": i.photo_count}
                    for i in proj.items(ids)
                ],
            }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class TropyAddRequest(BaseModel):
    project: str
    item_ids: list[int] | None = None
    output_dir: str = "output"


@app.post("/api/tropy/add")
def tropy_add(req: TropyAddRequest) -> dict:
    try:
        with TropyProject(req.project) as proj:
            pages = proj.pages(req.item_ids)
            missing = [p.label for p in proj.missing_assets(pages)]
            items = pages_to_job_items(pages)
            try:
                write_manifest(req.output_dir, proj, pages)
            except Exception:
                pass
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    added = state.add_items(items)
    return {
        "added": len(added),
        "missing": missing,
        "items": state.queue_snapshot(),
    }


def _build_tropy_preview(req: TropySendRequest):
    from ..tropy_write import TropyWriter, entries_from_items

    items = state.tropy_eligible_items(req.item_ids)
    entries = entries_from_items(items, stage=req.stage)
    with TropyWriter(req.project) as writer:
        return writer.preview(entries, req.targets)


@app.post("/api/tropy/send/preview")
def tropy_send_preview(req: TropySendRequest) -> dict:
    """What sending would do, without touching the Tropy project.

    Recomputed fresh on every call rather than cached between preview and
    write — the desktop dialog does the same (a second `TropyWriter` connection
    for the write step), so a duplicate that appeared between the two calls is
    still caught.
    """
    try:
        preview = _build_tropy_preview(req)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "blockers": preview.blockers,
        "summary": preview.summary(),
        "insertable": len(preview.insertable),
        "plans": [
            {"label": p.entry.label or f"photo {p.entry.photo_id}",
             "target": p.target, "action": p.action, "reason": p.reason}
            for p in preview.plans
        ],
    }


@app.post("/api/tropy/send/write")
def tropy_send_write(req: TropySendWriteRequest) -> dict:
    """Writes for real. Refuses if the fresh preview has any blocker."""
    from ..tropy_write import TropyWriter

    try:
        preview = _build_tropy_preview(req)
        if preview.blockers:
            raise HTTPException(status_code=409, detail="; ".join(preview.blockers))
        with TropyWriter(req.project) as writer:
            report = writer.write(preview, make_backup=req.make_backup)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if report.errors:
        raise HTTPException(status_code=500, detail="; ".join(report.errors))

    return {
        "written": report.written,
        "skipped": report.skipped,
        "backup": str(report.backup) if report.backup else None,
    }


# --------------------------------------------------------------------------- #
# pdf export (one-off — not wired into the queue/runner)
# --------------------------------------------------------------------------- #

@app.post("/api/pdf-export/start")
def pdf_export_start(req: PdfExportRequest) -> dict:
    started = start_pdf_export(
        req.folder, stage=req.stage,
        structure=req.structure, output=req.output,
        manifest_path=req.manifest,
    )
    if not started:
        raise HTTPException(
            status_code=409, detail="A PDF export is already running")
    return {"ok": True}


@app.get("/api/pdf-export/status")
def pdf_export_status_route() -> dict:
    return {
        "status": pdf_export_state.status,
        "error": pdf_export_state.error,
        "output_path": pdf_export_state.output_path,
    }


@app.get("/api/pdf-export/events")
async def pdf_export_events():
    async def gen():
        while True:
            try:
                event = await asyncio.to_thread(
                    pdf_export_state.events.get, True, 1.0)
            except queue.Empty:
                yield ": heartbeat\n\n"
                continue
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("type") in ("done", "error"):
                break
    return StreamingResponse(
        gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache",
                 "X-Accel-Buffering": "no"},
    )


@app.get("/api/pdf-export/download")
def pdf_export_download():
    if not pdf_export_state.output_path:
        raise HTTPException(status_code=404, detail="No PDF has been compiled yet")
    path = Path(pdf_export_state.output_path)
    return FileResponse(path, media_type="application/pdf", filename=path.name)


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
    its socket — opening a window at the target URL immediately races that,
    and loses often enough to matter (caught it happening on ordinary
    hardware, not a contrived slow-machine case). A bare TCP connect is enough
    evidence the server is up; the real HTTP request the window makes next
    then succeeds normally. This affects the browser fallback exactly as much
    as the native window, so both wait here rather than each growing their
    own copy of this check.
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


def _start_server_thread(port: int):
    """Run uvicorn in a background thread, capturing any exception it raises.

    A `.pyw` process has no console, so an exception here would otherwise
    just kill the daemon thread silently — `main()` would then open a window
    onto a server that never came up, with nothing telling the user why.
    Returns (thread, errors) where `errors` is a list `_report_startup_failure`
    can inspect after `_wait_for_server` gives up.
    """
    import threading

    import uvicorn

    errors: list[BaseException] = []

    def _serve():
        try:
            uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
        except Exception as exc:  # surfaced to the main thread, not swallowed
            errors.append(exc)

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    return thread, errors


def _report_startup_failure(port: int, thread, errors: list[BaseException]) -> None:
    """Tell the user the server didn't start, instead of silently opening a
    window onto a connection-refused page — the exact failure mode this
    replaces (caught live: a `.pyw` window would show Edge's WebView2 error
    page with zero indication anything went wrong, since print() goes
    nowhere without a console).
    """
    if errors:
        detail = f"{type(errors[0]).__name__}: {errors[0]}"
    elif thread.is_alive():
        detail = "No response within 10s, though the server thread is still running."
    else:
        detail = "The server thread exited without ever starting to listen."
    message = (f"OCR Pipeline's local server could not start on port {port}.\n\n"
              f"{detail}\n\n"
              f"Close any other OCR Pipeline window and try again.")
    print(f"ERROR: {message}")
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("OCR Pipeline — server did not start", message)
        root.destroy()
    except Exception:
        pass  # already printed above; nothing more to do without a console


def _ensure_std_streams() -> None:
    """A `.pyw` launched with a real double-click (no terminal, no redirected
    output) has `sys.stdout`/`sys.stderr` as None — not just quiet, literally
    absent. That crashes two different things here: this module's own
    print() calls (`_report_startup_failure` among them — the very thing
    meant to explain a startup failure would itself raise), and uvicorn's
    internal logging setup, which fails immediately with "Unable to
    configure formatter 'default'" trying to attach a StreamHandler to a
    stream that doesn't exist. Confirmed live: this is the actual cause of
    the "OCR Pipeline" window showing a bare connection-refused page after a
    fresh reboot, with no other process holding the port.
    """
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")


def main() -> None:
    """Start the server and open a window onto it.

    Prefers a native pywebview window (native file/folder dialogs, no browser
    chrome); falls back to opening the system browser if pywebview is not
    installed or `--browser` is passed, since the server works standalone too.
    """
    _ensure_std_streams()

    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", action="store_true",
                       help="Open in the default browser instead of a native window")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    port = args.port or _free_port()
    url = f"http://127.0.0.1:{port}"

    server_thread, server_errors = _start_server_thread(port)
    if not _wait_for_server(port):
        _report_startup_failure(port, server_thread, server_errors)
        return

    use_browser = args.browser
    if not use_browser:
        try:
            import webview  # noqa: F401
        except ImportError:
            use_browser = True

    if use_browser:
        webbrowser.open(url)
        print(f"OCR Pipeline running at {url}  (Ctrl+C to stop)")
        try:
            server_thread.join()
        except KeyboardInterrupt:
            pass
        return

    _run_native_window(url)


def _run_native_window(url: str) -> None:
    import webview

    from .bridge import Bridge

    window = webview.create_window(
        "OCR Pipeline", url, width=1180, height=860, min_size=(980, 700),
        js_api=Bridge(),
    )
    webview.start(private_mode=False)


if __name__ == "__main__":
    main()

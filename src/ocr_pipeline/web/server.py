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
import queue
import socket
import sys
import webbrowser
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import config
from .._prompts import DOCUMENT_TYPES
from ..jobs import STAGES
from ..tropy import TropyProject, pages_to_job_items, recent_projects
from .runtime import (
    serialize_event,
    serialize_history_item,
    serialize_history_item_detail,
    serialize_history_run,
    serialize_item_preview,
    state,
)

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


@app.post("/api/tropy/add")
def tropy_add(req: TropyAddRequest) -> dict:
    try:
        with TropyProject(req.project) as proj:
            pages = proj.pages(req.item_ids)
            items = pages_to_job_items(pages)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    added = state.add_items(items)
    return {"added": len(added), "items": state.queue_snapshot()}


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


def main() -> None:
    """Start the server and open a window onto it.

    Prefers a native pywebview window (native file/folder dialogs, no browser
    chrome); falls back to opening the system browser if pywebview is not
    installed or `--browser` is passed, since the server works standalone too.
    """
    import argparse
    import threading

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

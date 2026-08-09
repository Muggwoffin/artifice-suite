# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""FastAPI backend for the Artifice Hub — native launcher and installer GUI.

Owns the FastAPI ``app`` and the bootstrap code (port discovery, server
thread, native window / browser launch).

The Hub makes zero model calls — the harness mandate does not apply here.
"""

from __future__ import annotations

import contextlib
import importlib.resources
import json
import re
import sys
import threading
import webbrowser
from datetime import UTC, datetime
from typing import Any

import shared_ui
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from model_harness.registry import HardwareTier
from shared_ui.server_bootstrap import (
    ensure_std_streams,
    free_port,
    port_available,
    report_startup_failure,
    start_server_thread,
    wait_for_server,
)
from starlette.middleware.base import BaseHTTPMiddleware

from .. import __version__
from ..engine import get_engine_status, pull_model_command
from ..hardware import GpuKind
from ..hardware import probe as probe_hardware
from ..registry import APPS
from ..state import HubState
from ..uv_backend import (
    JobState,
    _jobs,
    find_uv,
    install_app,
    launch_app,
    list_tools,
    outdated_tools,
    upgrade_app,
)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="ArtificeHub")

class AllowedHostsMiddleware(BaseHTTPMiddleware):
    """Reject requests with a Host header that isn't localhost.

    Prevents DNS-rebinding attacks against the Hub's local API.
    """
    _ALLOWED = ("127.0.0.1", "localhost", "[::1]")

    async def dispatch(self, request, call_next):
        host = request.headers.get("host", "").split(":")[0]
        if host and host not in self._ALLOWED:
            return JSONResponse({"error": "Forbidden"}, status_code=403)
        return await call_next(request)

app.add_middleware(AllowedHostsMiddleware)


@app.middleware("http")
async def no_cache_static(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/") or request.url.path.startswith("/shared/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# ── Static assets (importlib.resources — freeze-safe) ──────────────────

_SHARED_UI = importlib.resources.files(shared_ui) / "assets"

# Resolve from the artifice_hub.web package
_STATIC_DIR = importlib.resources.files("artifice_hub.web") / "static"

# Mount static BEFORE shared so the hub's own files take precedence
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
app.mount("/shared", StaticFiles(directory=str(_SHARED_UI)), name="shared")


# ── Serve index.html at root ───────────────────────────────────────────

@app.get("/")
async def index():
    """Serve the hub dashboard."""
    content = (_STATIC_DIR / "index.html").read_text(encoding="utf-8")
    from fastapi.responses import HTMLResponse

    return HTMLResponse(content)


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

# Tier mapping from GpuKind to HardwareTier
def _gpu_kind_to_tier(gpu_kind: GpuKind) -> HardwareTier:
    if gpu_kind == GpuKind.CUDA:
        return HardwareTier.DESKTOP
    if gpu_kind == GpuKind.APPLE_SILICON:
        return HardwareTier.MAC_UNIFIED
    return HardwareTier.LAPTOP

# Helper function to parse progress from ollama output
def _parse_progress(line: str) -> dict[str, Any]:
    match = re.search(r'(\d{1,3})%', line)
    progress = int(match.group(1)) if match else None
    return {"line": line, "progress": progress} if progress is not None else {"line": line}


@app.get("/api/health")
async def api_health():
    """Report whether ``uv`` is found and return its path."""
    uv_path = find_uv()
    return {
        "status": "ok",
        "version": __version__,
        "uv": uv_path,
    }


@app.get("/api/hardware")
async def api_hardware():
    """Return a GPU / OS hardware profile."""
    profile = probe_hardware()
    return {"gpu": profile.gpu.value, "detail": profile.detail}


@app.get("/api/apps")
async def api_apps():
    """Return the status of all registered apps.

    Includes whether each app is installed, its current version, and whether
    an update is available.
    """
    uv = find_uv()
    if uv is None:
        return {
            "uv_found": False,
            "apps": [
                {
                    "slug": spec.slug,
                    "display_name": spec.display_name,
                    "description": spec.description,
                    "self_opens_browser": spec.self_opens_browser,
                    "default_port": spec.default_port,
                    "has_asr_variants": spec.has_asr_variants,
                    "status": "uv_missing",
                    "version": None,
                    "update_available": False,
                }
                for spec in APPS.values()
            ],
        }

    tools = list_tools(uv)
    outdated = outdated_tools(uv)

    apps_data = []
    for spec in APPS.values():
        if spec.slug in tools:
            version = tools[spec.slug]
            update = spec.slug in outdated
            status = "update_available" if update else "installed"
        else:
            version = None
            update = False
            status = "not_installed"

        apps_data.append(
            {
                "slug": spec.slug,
                "display_name": spec.display_name,
                "description": spec.description,
                "self_opens_browser": spec.self_opens_browser,
                "default_port": spec.default_port,
                "has_asr_variants": spec.has_asr_variants,
                "status": status,
                "version": version,
                "update_available": update,
            }
        )

    return {"uv_found": True, "apps": apps_data}


@app.post("/api/apps/{slug}/install")
async def api_install(slug: str, request: Request):
    """Start an install job for *slug*.  Accepts ``variant`` in request body
    for transcribe ASR variant selection.

    Returns ``202`` with a ``job_id`` the client can stream via SSE.
    """
    if slug not in APPS:
        return JSONResponse({"error": f"Unknown app: {slug}"}, status_code=404)

    uv = find_uv()
    if uv is None:
        return JSONResponse({"error": "uv not installed"}, status_code=400)

    # Parse body for variant
    variant: str | None = None
    try:
        body = await request.json()
        variant = body.get("variant")
    except Exception:
        pass

    import uuid

    job_id = str(uuid.uuid4())
    job = JobState(job_id=job_id, slug=slug, action="install")
    _jobs[job_id] = job

    def _run():
        result = install_app(uv, slug, variant, job)
        job.finish(result)
        # Update state on success
        if result.returncode == 0:
            state = HubState.load()
            tools = list_tools(uv)
            if slug in tools:
                state.record_install(slug, tools[slug])

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return JSONResponse({"job_id": job_id}, status_code=202)


@app.post("/api/apps/{slug}/upgrade")
async def api_upgrade(slug: str):
    """Start an upgrade job for *slug*.

    Returns ``202`` with a ``job_id`` the client can stream via SSE.
    """
    if slug not in APPS:
        return JSONResponse({"error": f"Unknown app: {slug}"}, status_code=404)

    uv = find_uv()
    if uv is None:
        return JSONResponse({"error": "uv not installed"}, status_code=400)

    import uuid

    job_id = str(uuid.uuid4())
    job = JobState(job_id=job_id, slug=slug, action="upgrade")
    _jobs[job_id] = job

    def _run():
        result = upgrade_app(uv, slug, job)
        job.finish(result)
        if result.returncode == 0:
            state = HubState.load()
            tools = list_tools(uv)
            if slug in tools:
                state.record_install(slug, tools[slug])

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return JSONResponse({"job_id": job_id}, status_code=202)


@app.post("/api/apps/{slug}/launch")
async def api_launch(slug: str):
    """Launch the installed app. Returns ``200`` on success or an error."""
    if slug not in APPS:
        return JSONResponse({"error": f"Unknown app: {slug}"}, status_code=404)

    uv = find_uv()
    if uv is None:
        return JSONResponse({"error": "uv not installed"}, status_code=400)

    hardware_profile = probe_hardware()
    tier = _gpu_kind_to_tier(hardware_profile.gpu)

    try:
        engine_status = await get_engine_status(slug, tier)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=404)

    if not engine_status["all_satisfied"]:
        return {
            "ok": True,
            "engine_required": True,
            "message": "Engine requirements not satisfied",
        }

    spec = APPS[slug]
    ok, msg = launch_app(uv, slug)
    if ok:
        state = HubState.load()
        state.record_launch(slug)

        if spec.self_opens_browser:
            return {"ok": True, "message": msg, "self_opens_browser": True}
        if spec.default_port:
            return {"ok": True, "message": msg, "url": f"http://127.0.0.1:{spec.default_port}"}
        return {"ok": True, "message": msg}

    return JSONResponse({"ok": False, "message": msg}, status_code=500)


@app.get("/api/jobs/{job_id}/events")
async def api_job_events(job_id: str):
    """SSE stream of install/upgrade progress events for *job_id*."""
    job = _jobs.get(job_id)
    if job is None:
        return JSONResponse({"error": "Job not found"}, status_code=404)

    async def _stream():
        yield "event: start\ndata: {}\n\n"
        while True:
            try:
                line = job.events.get(timeout=0.5)
            except Exception:
                # Send a heartbeat so the connection stays alive
                ts = datetime.now(UTC).isoformat()
                yield f"event: heartbeat\ndata: {json.dumps({'ts': ts})}\n\n"
                continue

            if line is None:
                # Sentinel — job complete
                if job.result:
                    payload = {
                        "returncode": job.result.returncode,
                        "error_kind": job.result.error_kind.value,
                        "error_detail": job.result.error_detail,
                    }
                    yield f"event: done\ndata: {json.dumps(payload)}\n\n"
                else:
                    yield "event: done\ndata: {}\n\n"
                break
            if job.action == "pull":
                progress_data = _parse_progress(line)
                yield f"event: log\ndata: {json.dumps(progress_data)}\n\n"
            else:
                yield f"event: log\ndata: {json.dumps({'line': line})}\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/jobs")
async def api_jobs():
    """Return active and recent jobs."""
    jobs = {}
    for job_id, job in _jobs.items():
        jobs[job_id] = {
            "slug": job.slug,
            "action": job.action,
            "complete": job.complete,
            "error_kind": job.result.error_kind.value if job.result else None,
            "started_at": datetime.fromtimestamp(job.started_at, tz=UTC).isoformat(),
        }
    return {"jobs": jobs}


@app.get("/api/engine/{slug}")
async def api_engine_status(slug: str):
    """Get the engine status for the given app slug."""
    if slug not in APPS:
        return JSONResponse({"error": f"Unknown app: {slug}"}, status_code=404)

    hardware_profile = probe_hardware()
    tier = _gpu_kind_to_tier(hardware_profile.gpu)

    try:
        status = await get_engine_status(slug, tier)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=404)

    return status

@app.post("/api/engine/{slug}/pull")
async def api_pull_model(slug: str, request: Request):
    """Pull a model for the given app slug."""
    if slug not in APPS:
        return JSONResponse({"error": f"Unknown app: {slug}"}, status_code=404)

    try:
        body = await request.json()
        model_name = body.get("model")
    except Exception:
        return JSONResponse({"error": "Invalid request body"}, status_code=400)

    if not model_name:
        return JSONResponse({"error": "Model name is required"}, status_code=400)

    hardware_profile = probe_hardware()
    tier = _gpu_kind_to_tier(hardware_profile.gpu)

    try:
        cmd = pull_model_command(slug, tier, model_name)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    import uuid

    job_id = str(uuid.uuid4())
    job = JobState(job_id=job_id, slug=slug, action="pull")
    _jobs[job_id] = job

    def _run():
        from ..uv_backend import _run_subprocess
        result = _run_subprocess(cmd, job)
        job.finish(result)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return JSONResponse({"job_id": job_id}, status_code=202)


# ---------------------------------------------------------------------------
# Bootstrap — main() entry point
# ---------------------------------------------------------------------------


def main() -> None:
    ensure_std_streams()

    import argparse

    parser = argparse.ArgumentParser(description="Artifice Hub — native Artifice Suite launcher")
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port for the local server (default: 8865, or a free port if busy)",
    )
    parser.add_argument(
        "--no-window",
        action="store_true",
        default=False,
        help="Server-only mode: print the URL and wait, do not open a window or browser",
    )
    args = parser.parse_args()

    is_explicit_port = args.port is not None

    # Try the requested port; fall back to a free port when not explicit.
    port = 8865
    for attempt in range(2):
        if attempt == 0:
            port = args.port if is_explicit_port else 8865
        else:
            port = free_port()
            print(f"Port 8865 is busy — using port {port} instead.", flush=True)

        if not port_available(port):
            if is_explicit_port or attempt == 1:
                report_startup_failure(
                    "ArtificeHub", port, None, [OSError(f"Port {port} is already in use")]
                )
                return
            continue

        server_thread, server_errors = start_server_thread(app, port)
        if wait_for_server(port):
            break

        if is_explicit_port or attempt == 1:
            report_startup_failure("ArtificeHub", port, server_thread, server_errors)
            return

    # Guard against the race where another process grabbed the port
    if server_errors or not server_thread.is_alive():
        report_startup_failure("ArtificeHub", port, server_thread, server_errors)
        return

    url = f"http://127.0.0.1:{port}"

    # ── Server-only mode (--no-window) ────────────────────────────────
    if args.no_window:
        print(f"ArtificeHub running at {url}  (Ctrl+C to stop)", flush=True)
        with contextlib.suppress(KeyboardInterrupt):
            server_thread.join()
        return

    # ── Frozen executable: try a native window ────────────────────────
    _frozen = bool(getattr(sys, "frozen", False))
    if _frozen:
        from .window import open_native_window  # noqa: PLC0415

        result = open_native_window(url, title="ArtificeHub")
        if result.opened:
            return

        print(result.reason, flush=True)
        print(f"Falling back — ArtificeHub running at {url}", flush=True)
        webbrowser.open(url)
        with contextlib.suppress(KeyboardInterrupt):
            server_thread.join()
        return

    # ── Non-frozen (dev / `uv run artifice-hub`) ─────────────────────
    print(f"ArtificeHub running at {url}  (Ctrl+C to stop)", flush=True)
    webbrowser.open(url)
    with contextlib.suppress(KeyboardInterrupt):
        server_thread.join()

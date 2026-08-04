# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""FastAPI backend for the web frontend.

This module owns the FastAPI ``app`` and the bootstrap code (CLI, port
discovery, browser launch). Individual route groups live under ``routers/``
and are included here.
"""

import json
import os
import socket
import sys
import webbrowser
from html import escape
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .routers import analytics as analytics_router
from .routers import byom as byom_router
from .routers import events as events_router
from .routers import history as history_router
from .routers import pdf_export as pdf_export_router
from .routers import queue as queue_router
from .routers import run as run_router
from .routers import settings as settings_router
from .routers import tropy as tropy_router
from .routers import ludwiglang as ludwiglang_router

app = FastAPI(title="OCR Pipeline")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8765",
        "http://127.0.0.1:8765",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def no_cache_static(request: Request, call_next):
    response: Response = await call_next(request)
    if request.url.path.startswith("/static/") or request.url.path.startswith("/shared/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

app.include_router(byom_router.router)
app.include_router(queue_router.router)
app.include_router(run_router.router)
app.include_router(events_router.router)
app.include_router(settings_router.router)
app.include_router(history_router.router)
app.include_router(analytics_router.router)
app.include_router(tropy_router.router)
app.include_router(pdf_export_router.router)
app.include_router(ludwiglang_router.router)

STATIC_DIR = Path(__file__).resolve().parent / "static"

# ── Shared design system (resolved from installed shared-ui package) ───────
import importlib.resources
import shared_ui
_SHARED_UI = importlib.resources.files(shared_ui) / "assets"
app.mount("/shared", StaticFiles(directory=str(_SHARED_UI)), name="shared")


def _asset_version() -> str:
    """Cache-busting version for the /static and /shared links in index.html.

    Derived from the newest mtime across both asset trees and recomputed on
    every request to "/", so an asset edited while the server is running is
    picked up immediately and the version changes only when an asset
    actually did. The cost is a directory walk (stat only, no file reads)
    once per page load — negligible for a static tree this size, but it
    would not scale to a very large one.
    """
    roots = (STATIC_DIR, Path(str(_SHARED_UI)))
    mtimes = [p.stat().st_mtime for root in roots for p in root.rglob("*") if p.is_file()]
    return str(int(max(mtimes))) if mtimes else "0"


@app.get("/")
def index() -> HTMLResponse:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html.replace("__ASSET_V__", _asset_version()))


# ── BYOM dev-only preview (phase6) ──────────────────────────────────────────
#
# Renders packages/shared-ui's byom.css/byom.js against fixture data, with
# no dependency on the real /api/byom/* routes — those are Step 4 and do not
# exist yet. Gated behind ARTIFICE_DEV_PREVIEW=1 so it 404s (rather than
# merely being unlinked) unless a developer opts in, and can never ship
# enabled by accident.


def _byom_recommendations() -> dict:
    """Serialise model_harness.registry recommendations for artifice-ocr.

    Reads the real ModelRecommendation fields (model_name, provider, vision,
    min_vram_gb) — NOT the {name, why, size_bytes} shape the phase6 brief's
    illustrative GET /api/byom/state JSON shows, which does not match the
    dataclass. See the KNOWN CONTRACT MISMATCH note atop
    packages/shared-ui/shared_ui/assets/byom.js.
    """
    from model_harness.registry import HardwareTier, recommendations_for_app

    tier_keys = {
        "laptop": HardwareTier.LAPTOP,
        "desktop": HardwareTier.DESKTOP,
        "mac_unified": HardwareTier.MAC_UNIFIED,
    }
    return {
        key: [
            {
                "model_name": r.model_name,
                "provider": r.provider,
                "vision": r.vision,
                "min_vram_gb": r.min_vram_gb,
            }
            for r in recommendations_for_app("artifice-ocr", tier)
        ]
        for key, tier in tier_keys.items()
    }


def _byom_preview_fixture(state: str) -> dict:
    """Return the fixture bundle {state, detect, test, initialTab, autoTest}
    for one preview state. Falls back to "not-found" for an absent or
    unrecognised ``state`` — the real first-run case.

    Hint strings mirror (but do not import — they are private module
    constants) the wording model_harness.discovery actually produces, so
    the preview reads like the real thing without reaching into
    discovery.py's underscore-prefixed internals.
    """
    base_state = {
        "app": "artifice-ocr",
        "configured": False,
        "endpoint": None,
        "model": None,
        "recommendations": _byom_recommendations(),
    }

    runner_down_hint = (
        "Ensure your local model runner (Ollama, LM Studio, vLLM) is running. "
        "Run 'ollama serve' to start the Ollama server"
    )
    lm_studio_down_hint = "Ensure the LM Studio server is running and accessible"

    not_found_detect = {
        "endpoints": [
            {"url": "http://localhost:11434", "name": "Ollama", "provider": "ollama",
             "reachable": False, "models": [], "hint": runner_down_hint},
            {"url": "http://localhost:1234/v1", "name": "LM Studio", "provider": "lm-studio",
             "reachable": False, "models": [], "hint": lm_studio_down_hint},
        ]
    }
    found_detect = {
        "endpoints": [
            {"url": "http://localhost:11434", "name": "Ollama", "provider": "ollama",
             "reachable": True, "models": ["llava:7b"], "hint": None},
            {"url": "http://localhost:1234/v1", "name": "LM Studio", "provider": "lm-studio",
             "reachable": False, "models": [], "hint": lm_studio_down_hint},
        ]
    }
    ok_test = {"reachable": True, "provider": "ollama", "models": ["llava:7b", "minicpm-v:8b"], "hint": None}
    fail_test = {"reachable": False, "provider": "ollama", "models": [], "hint": runner_down_hint}

    scenarios = {
        "detecting": {
            "state": base_state, "detect": None, "test": None,
            "initialTab": None, "autoTest": None,
        },
        "not-found": {
            "state": base_state, "detect": not_found_detect, "test": fail_test,
            "initialTab": None, "autoTest": None,
        },
        "found": {
            "state": base_state, "detect": found_detect, "test": ok_test,
            "initialTab": None, "autoTest": None,
        },
        "test-ok": {
            "state": base_state, "detect": not_found_detect, "test": ok_test,
            "initialTab": None, "autoTest": {"url": "http://localhost:11434", "apiKey": ""},
        },
        "test-fail": {
            "state": base_state, "detect": not_found_detect, "test": fail_test,
            "initialTab": None, "autoTest": {"url": "http://localhost:9999", "apiKey": ""},
        },
        "advanced": {
            "state": base_state, "detect": not_found_detect, "test": fail_test,
            "initialTab": "advanced", "autoTest": None,
        },
    }
    return scenarios.get(state, scenarios["not-found"])


@app.get("/byom-preview")
def byom_preview(state: str = "not-found") -> HTMLResponse:
    """Dev-only preview of the shared BYOM onboarding screen. 404s unless
    ARTIFICE_DEV_PREVIEW=1 is set in the environment.
    """
    if os.environ.get("ARTIFICE_DEV_PREVIEW") != "1":
        raise HTTPException(status_code=404)

    html = (STATIC_DIR / "byom-preview.html").read_text(encoding="utf-8")
    fixture = _byom_preview_fixture(state)
    # "</" -> "<\/" defensively: none of the fixture strings above contain
    # it today, but this is embedded into a <script> block by string
    # substitution rather than a templating engine that would escape it,
    # and the fixture text is free-form enough (hints, URLs) that a future
    # edit could introduce "</script>" by accident.
    fixture_json = json.dumps(fixture).replace("</", "<\\/")
    # `state` is attacker-influenceable (a query parameter) even though this
    # route is dev-flag-gated, so it gets two separately-escaped
    # substitutions rather than one shared placeholder: HTML-escaped for the
    # text node, JSON-encoded (implies quoting) for the JS string literal.
    html = html.replace("__ASSET_V__", _asset_version())
    html = html.replace("__STATE_HTML__", escape(state))
    html = html.replace("__STATE_JS__", json.dumps(state))
    html = html.replace("__FIXTURE_JSON__", fixture_json)
    return HTMLResponse(html)


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# --------------------------------------------------------------------------- #
# bootstrap
# --------------------------------------------------------------------------- #

def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(port: int, *, timeout: float = 10.0) -> bool:
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
    import threading

    import uvicorn

    errors: list[BaseException] = []

    def _serve():
        try:
            uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    return thread, errors


def _report_startup_failure(port: int, thread, errors: list[BaseException]) -> None:
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
        pass


def _ensure_std_streams() -> None:
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")


def main() -> None:
    _ensure_std_streams()

    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765,
                        help="Port for the local server (default: 8765)")
    args = parser.parse_args()

    port = args.port
    url = f"http://127.0.0.1:{port}"

    server_thread, server_errors = _start_server_thread(port)
    if not _wait_for_server(port):
        _report_startup_failure(port, server_thread, server_errors)
        return

    webbrowser.open(url)
    print(f"OCR Pipeline running at {url}  (Ctrl+C to stop)")
    try:
        server_thread.join()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

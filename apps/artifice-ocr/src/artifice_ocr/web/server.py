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


_BYOM_PREVIEW_APPS = (
    "artifice-ocr",
    "artifice-draft",
    "artifice-graph",
    "artifice-transcribe",
)
# Apps the dev-only preview can render. Matches the four ``app`` slugs
# ``GET /api/byom/state`` will actually return — see
# ``model_harness.registry._RECOMMENDATIONS``, which already carries all four
# (artifice-transcribe's entries cover its optional post-transcription
# endpoint only, per the docstring on ``recommendations_for_app``).

_BYOM_PREVIEW_APP_NAMES = {
    "artifice-ocr": "OCR Pipeline",
    "artifice-draft": "Draft",
    "artifice-graph": "Knowledge Graph",
    "artifice-transcribe": "Transcribe",
}


def _byom_recommendations(app: str) -> dict:
    """Serialise model_harness.registry recommendations for *app*.

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
            for r in recommendations_for_app(app, tier)
        ]
        for key, tier in tier_keys.items()
    }


def _byom_base_state(app: str) -> dict:
    """Build the {app, configured, endpoint, model, recommendations[, embedding]}
    shape for *app*. Only artifice-graph carries the `embedding` key — the
    other three omit it entirely, matching the frozen contract byom.js
    branches on (see APP_GRAPH handling in packages/shared-ui/shared_ui
    /assets/byom.js). The embedding block itself has no registry data of
    its own to source from (model_harness.registry has no embedding-model
    table), so its endpoint/model here are the frozen contract's own
    literal example, not a real lookup.
    """
    state = {
        "app": app,
        "configured": False,
        "endpoint": None,
        "model": None,
        "recommendations": _byom_recommendations(app),
    }
    if app == "artifice-graph":
        state["embedding"] = {
            "configured": False,
            "endpoint": "http://localhost:11434",
            "model": "bge-m3",
        }
    return state


def _byom_preview_fixture(app: str, state: str) -> dict:
    """Return the fixture bundle {state, detect, test, testEmbedding,
    initialTab, autoTest} for one (app, state) pair. Falls back to
    "artifice-ocr" for an unrecognised ``app`` and to "not-found" for an
    absent or unrecognised ``state`` — the real first-run case.

    Hint strings mirror (but do not import — they are private module
    constants) the wording model_harness.discovery actually produces, so
    the preview reads like the real thing without reaching into
    discovery.py's underscore-prefixed internals.
    """
    if app not in _BYOM_PREVIEW_APPS:
        app = "artifice-ocr"
    base_state = _byom_base_state(app)

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
    # POST /api/byom/test-embedding fixtures — graph only exercises these,
    # but they are harmless to include for every app since byom.js never
    # calls that endpoint unless state.embedding is present.
    embedding_ok_test = {"reachable": True, "provider": "ollama", "models": ["bge-m3"], "hint": None}
    embedding_fail_test = {"reachable": False, "provider": "ollama", "models": [], "hint": runner_down_hint}

    scenarios = {
        "detecting": {
            "state": base_state, "detect": None, "test": None, "testEmbedding": None,
            "initialTab": None, "autoTest": None,
        },
        "not-found": {
            "state": base_state, "detect": not_found_detect, "test": fail_test,
            "testEmbedding": embedding_fail_test,
            "initialTab": None, "autoTest": None,
        },
        "found": {
            "state": base_state, "detect": found_detect, "test": ok_test,
            "testEmbedding": embedding_ok_test,
            "initialTab": None, "autoTest": None,
        },
        "test-ok": {
            "state": base_state, "detect": not_found_detect, "test": ok_test,
            "testEmbedding": embedding_ok_test,
            "initialTab": None, "autoTest": {"url": "http://localhost:11434", "apiKey": ""},
        },
        "test-fail": {
            "state": base_state, "detect": not_found_detect, "test": fail_test,
            "testEmbedding": embedding_fail_test,
            "initialTab": None, "autoTest": {"url": "http://localhost:9999", "apiKey": ""},
        },
        "advanced": {
            "state": base_state, "detect": not_found_detect, "test": fail_test,
            "testEmbedding": embedding_fail_test,
            "initialTab": "advanced", "autoTest": None,
        },
    }
    return scenarios.get(state, scenarios["not-found"])


@app.get("/byom-preview")
def byom_preview(app: str = "artifice-ocr", state: str = "not-found") -> HTMLResponse:
    """Dev-only preview of the shared BYOM onboarding screen. 404s unless
    ARTIFICE_DEV_PREVIEW=1 is set in the environment.

    `app` and `state` are orthogonal: `app` selects which of the four apps'
    GET /api/byom/state payload is served, `state` keeps selecting the
    detect/test scenario, exactly as before this parameter was added.
    """
    if os.environ.get("ARTIFICE_DEV_PREVIEW") != "1":
        raise HTTPException(status_code=404)

    html = (STATIC_DIR / "byom-preview.html").read_text(encoding="utf-8")
    fixture = _byom_preview_fixture(app, state)
    resolved_app = fixture["state"]["app"]  # normalised: falls back to artifice-ocr for a bad `app`
    app_name = _BYOM_PREVIEW_APP_NAMES.get(resolved_app, resolved_app)
    # "</" -> "<\/" defensively: none of the fixture strings above contain
    # it today, but this is embedded into a <script> block by string
    # substitution rather than a templating engine that would escape it,
    # and the fixture text is free-form enough (hints, URLs) that a future
    # edit could introduce "</script>" by accident.
    fixture_json = json.dumps(fixture).replace("</", "<\\/")
    # `state` and `app` are both attacker-influenceable (query parameters)
    # even though this route is dev-flag-gated, so each gets two
    # separately-escaped substitutions rather than one shared placeholder:
    # HTML-escaped for the text node, JSON-encoded (implies quoting) for the
    # JS string literal.
    #
    # json.dumps() does NOT escape "/" — a `state` of
    # "</script><script>alert(1)</script>" survives dumps() intact and,
    # embedded verbatim into the <script> block below, terminates it early:
    # the HTML tokenizer matches the literal bytes "</script" regardless of
    # JS string-literal context, so the browser closes the tag mid-string
    # and the remainder becomes live markup. Confirmed by curling this
    # route with that value during review. `resolved_app`/`app_name` are
    # already constrained to the four-item allowlist below and cannot
    # carry attacker input, but get the same treatment for defense in depth
    # against a future edit adding a name with "</" in it.
    html = html.replace("__ASSET_V__", _asset_version())
    html = html.replace("__STATE_HTML__", escape(state))
    html = html.replace("__STATE_JS__", json.dumps(state).replace("</", "<\\/"))
    html = html.replace("__APP_HTML__", escape(resolved_app))
    html = html.replace("__APP_JS__", json.dumps(resolved_app).replace("</", "<\\/"))
    html = html.replace("__APP_NAME_JS__", json.dumps(app_name).replace("</", "<\\/"))
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

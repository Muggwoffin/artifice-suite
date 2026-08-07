# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""FastAPI backend for the web frontend.

This module owns the FastAPI ``app`` and the bootstrap code (CLI, port
discovery, browser launch). Individual route groups live under ``routers/``
and are included here.
"""

import contextlib
import json
import os
import sys
import time
import webbrowser
from html import escape
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import ChoiceLoader, Environment, PackageLoader, select_autoescape

from .routers import analytics as analytics_router
from .routers import byom as byom_router
from .routers import events as events_router
from .routers import history as history_router
from .routers import ludwiglang as ludwiglang_router
from .routers import pdf_export as pdf_export_router
from .routers import queue as queue_router
from .routers import run as run_router
from .routers import settings as settings_router
from .routers import tropy as tropy_router

app = FastAPI(title="ArtificeOCR")

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

# ── Static assets (resolved through importlib.resources — freeze-safe) ─────
import importlib.resources

import shared_ui

# Resolved through importlib.resources, NOT a __file__-relative path.  This
# app is distributed as a frozen .exe/.dmg, where __file__ points inside a
# temporary extraction directory.  Using importlib keeps the path correct in
# every environment — source checkout, installed wheel, and frozen bundle.
STATIC_DIR = importlib.resources.files("artifice_ocr.web") / "static"

# Shared design system (resolved from installed shared-ui package)
_SHARED_UI = importlib.resources.files(shared_ui) / "assets"
app.mount("/shared", StaticFiles(directory=str(_SHARED_UI)), name="shared")

# ── Jinja2 — PackageLoader resolves through importlib (freeze-safe), and
# ChoiceLoader lets templates include shared-ui’s masthead partial.
_JINJA = Environment(
    loader=ChoiceLoader(
        [
            PackageLoader("artifice_ocr.web", "templates"),
            PackageLoader("shared_ui", "templates"),
        ]
    ),
    autoescape=select_autoescape(["html", "xml"]),
)

# ── Masthead context for shared _masthead.html partial ──────────────────
_OCR_NAV_ITEMS = [
    {"href": "/", "label": "Pipeline", "key": "pipeline"},
    {"href": "/about", "label": "About", "key": "about"},
]

_MASTHEAD_CTX = {
    "brand_accent": "OCR",
    "brand_tagline": "local-first \u00b7 LM Studio + Ollama",
    "nav_items": _OCR_NAV_ITEMS,
    "show_theme_toggle": True,
}


def _asset_version() -> str:
    """Cache-busting version for the /static and /shared links.

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


def _render(template_name: str, **extra) -> str:
    """Build template context and render a Jinja template."""
    ctx: dict[str, Any] = {
        "asset_v": int(time.time()),
    }
    ctx.update(_MASTHEAD_CTX)
    ctx.update(extra)
    return _JINJA.get_template(template_name).render(**ctx)


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(_render("index.html", active_tab="pipeline"))


@app.get("/about", response_class=HTMLResponse)
def about() -> HTMLResponse:
    return HTMLResponse(_render("about.html", active_tab="about"))


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
    "artifice-ocr": "ArtificeOCR",
    "artifice-draft": "Draft",
    "artifice-graph": "Knowledge Graph",
    "artifice-transcribe": "Transcribe",
}


def _byom_recommendations(app: str) -> dict:
    """Serialise model_harness.registry recommendations for *app*.

    Reads the real ModelRecommendation fields (model_name, provider, vision,
    min_vram_gb, ethos_badges, role, notes) — NOT the {name, why, size_bytes}
    shape the phase6 brief's illustrative GET /api/byom/state JSON shows,
    which does not match the dataclass. See the KNOWN CONTRACT MISMATCH note
    atop packages/shared-ui/shared_ui/assets/byom.js.

    This is a dev-only duplicate of routers/byom.py's own
    _byom_recommendations(), kept in sync by hand rather than imported,
    because the preview route's fixture data lives in this file. PR #56
    added ethos_badges/role/notes to the real router but missed this copy —
    the exact "half-applied change" failure mode this codebase's HANDOVER
    keeps recording. Whenever ModelRecommendation's serialised shape
    changes, update both.
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
                "ethos_badges": list(r.ethos_badges),
                "role": r.role,
                "notes": r.notes,
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
            {
                "url": "http://localhost:11434",
                "name": "Ollama",
                "provider": "ollama",
                "reachable": False,
                "models": [],
                "hint": runner_down_hint,
            },
            {
                "url": "http://localhost:1234/v1",
                "name": "LM Studio",
                "provider": "lm-studio",
                "reachable": False,
                "models": [],
                "hint": lm_studio_down_hint,
            },
        ]
    }
    found_detect = {
        "endpoints": [
            {
                "url": "http://localhost:11434",
                "name": "Ollama",
                "provider": "ollama",
                "reachable": True,
                "models": ["llava:7b"],
                "hint": None,
            },
            {
                "url": "http://localhost:1234/v1",
                "name": "LM Studio",
                "provider": "lm-studio",
                "reachable": False,
                "models": [],
                "hint": lm_studio_down_hint,
            },
        ]
    }
    ok_test = {
        "reachable": True,
        "provider": "ollama",
        "models": ["llava:7b", "minicpm-v:8b"],
        "hint": None,
    }
    fail_test = {"reachable": False, "provider": "ollama", "models": [], "hint": runner_down_hint}
    # POST /api/byom/test-embedding fixtures — graph only exercises these,
    # but they are harmless to include for every app since byom.js never
    # calls that endpoint unless state.embedding is present.
    embedding_ok_test = {
        "reachable": True,
        "provider": "ollama",
        "models": ["bge-m3"],
        "hint": None,
    }
    embedding_fail_test = {
        "reachable": False,
        "provider": "ollama",
        "models": [],
        "hint": runner_down_hint,
    }

    scenarios = {
        "detecting": {
            "state": base_state,
            "detect": None,
            "test": None,
            "testEmbedding": None,
            "initialTab": None,
            "autoTest": None,
        },
        "not-found": {
            "state": base_state,
            "detect": not_found_detect,
            "test": fail_test,
            "testEmbedding": embedding_fail_test,
            "initialTab": None,
            "autoTest": None,
        },
        "found": {
            "state": base_state,
            "detect": found_detect,
            "test": ok_test,
            "testEmbedding": embedding_ok_test,
            "initialTab": None,
            "autoTest": None,
        },
        "test-ok": {
            "state": base_state,
            "detect": not_found_detect,
            "test": ok_test,
            "testEmbedding": embedding_ok_test,
            "initialTab": None,
            "autoTest": {"url": "http://localhost:11434", "apiKey": ""},
        },
        "test-fail": {
            "state": base_state,
            "detect": not_found_detect,
            "test": fail_test,
            "testEmbedding": embedding_fail_test,
            "initialTab": None,
            "autoTest": {"url": "http://localhost:9999", "apiKey": ""},
        },
        "advanced": {
            "state": base_state,
            "detect": not_found_detect,
            "test": fail_test,
            "testEmbedding": embedding_fail_test,
            "initialTab": "advanced",
            "autoTest": None,
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

from shared_ui.server_bootstrap import (  # noqa: E402
    ensure_std_streams,
    free_port,
    port_available,
    report_startup_failure,
    start_server_thread,
    wait_for_server,
)

# Re-export under the private names that `main()` and the test suite expect.
_free_port = free_port
_port_available = port_available
_wait_for_server = wait_for_server
_ensure_std_streams = ensure_std_streams


def _start_server_thread(port: int):
    return start_server_thread(app, port)


def _report_startup_failure(port: int, thread, errors: list[BaseException]) -> None:
    report_startup_failure("ArtificeOCR", port, thread, errors)


def main() -> None:
    _ensure_std_streams()

    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port for the local server (default: 8765, or a free port if busy)",
    )
    parser.add_argument(
        "--no-window",
        action="store_true",
        default=False,
        help="Server-only mode: print the URL and wait, do not open a window or browser",
    )
    args = parser.parse_args()

    # Distinguish "user said --port 8765" from "the default happened to be 8765".
    # An explicit port that is busy is a deliberate choice — fail, don't fall back.
    is_explicit_port = args.port is not None

    # Try the requested port; fall back to a free port only when the user
    # did NOT specify one and the default (8765) is busy.
    for attempt in range(2):
        if attempt == 0:
            port = args.port if is_explicit_port else 8765
        else:
            port = _free_port()
            print(f"Port 8765 is busy — using port {port} instead.", flush=True)

        if not _port_available(port):
            if is_explicit_port or attempt == 1:
                _report_startup_failure(port, None, [OSError(f"Port {port} is already in use")])
                return
            continue

        server_thread, server_errors = _start_server_thread(port)
        if _wait_for_server(port):
            break

        if is_explicit_port or attempt == 1:
            _report_startup_failure(port, server_thread, server_errors)
            return

    # Guard against the race where another process grabbed the port between
    # our availability check and the server thread binding.
    if server_errors or not server_thread.is_alive():
        _report_startup_failure(port, server_thread, server_errors)
        return

    url = f"http://127.0.0.1:{port}"

    # ── Server-only mode (--no-window) ────────────────────────────────────
    if args.no_window:
        print(f"ArtificeOCR running at {url}  (Ctrl+C to stop)", flush=True)
        with contextlib.suppress(KeyboardInterrupt):
            server_thread.join()
        return

    # ── Frozen executable: try a native window ───────────────────────────
    _frozen = bool(getattr(sys, "frozen", False))
    if _frozen:
        # Lazy import — pywebview must not be required at module scope
        # for non-frozen installs (e.g. `uv tool install` users who don't
        # have a webview backend).
        from .window import open_native_window  # noqa: PLC0415

        result = open_native_window(url, title="ArtificeOCR")
        if result.opened:
            # Window closed by user — exit cleanly.
            # The daemon server thread dies with the process.
            return

        # Window failed — fall back to browser (same as non-frozen mode,
        # but with an extra line explaining why).
        print(result.reason, flush=True)
        print(f"Falling back — ArtificeOCR running at {url}", flush=True)
        webbrowser.open(url)
        with contextlib.suppress(KeyboardInterrupt):
            server_thread.join()
        return

    # ── Non-frozen (dev / `uv run artifice-ocr-web`) ─────────────────────
    print(f"ArtificeOCR running at {url}  (Ctrl+C to stop)", flush=True)
    webbrowser.open(url)
    with contextlib.suppress(KeyboardInterrupt):
        server_thread.join()


if __name__ == "__main__":
    main()

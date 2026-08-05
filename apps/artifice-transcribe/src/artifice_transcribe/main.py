# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import ChoiceLoader, Environment, PackageLoader, select_autoescape

from artifice_transcribe.api.v1.routes import router as v1_router
from artifice_transcribe.config import settings
from artifice_transcribe.db.models import Base
from artifice_transcribe.db.session import engine
from artifice_transcribe.web.routers.byom import router as byom_router

STATIC_DIR = Path(__file__).parent / "web" / "static"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure data directory exists, then create tables
    _ = settings.data_path
    async with engine.connect() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.commit()
        logger.info("Tables created")
    logger.info("Database tables ensured")
    yield
    # Cleanup on shutdown
    await engine.dispose()


app = FastAPI(
    title="ArtificeTranscribe",
    version="0.1.0",
    description="Speech-to-Text & Diarization API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(v1_router)
app.include_router(byom_router)


@app.middleware("http")
async def no_cache_static(request: Request, call_next):
    response: Response = await call_next(request)
    if request.url.path.startswith("/static/") or request.url.path.startswith("/shared/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Shared design system (resolved from installed shared-ui package) ───────
import importlib.resources
import shared_ui
_SHARED_UI = importlib.resources.files(shared_ui) / "assets"
app.mount("/shared", StaticFiles(directory=str(_SHARED_UI)), name="shared")

# ── Jinja2 — PackageLoader resolves through importlib (freeze-safe), and
# ChoiceLoader lets templates include shared-ui’s masthead partial.
_JINJA = Environment(
    loader=ChoiceLoader([
        PackageLoader("artifice_transcribe.web", "templates"),
        PackageLoader("shared_ui", "templates"),
    ]),
    autoescape=select_autoescape(["html", "xml"]),
)

# ── Masthead context for shared _masthead.html partial ──────────────────
_TRANSCRIBE_NAV_ITEMS = [
    {"href": "/", "label": "Transcribe", "key": "transcribe"},
    {"href": "/about", "label": "About", "key": "about"},
]

_MASTHEAD_CTX = {
    "brand_accent": "Transcribe",
    "brand_tagline": "speech-to-text \u00b7 diarization \u00b7 oral history",
    "nav_items": _TRANSCRIBE_NAV_ITEMS,
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
async def index() -> HTMLResponse:
    return HTMLResponse(_render("index.html", active_tab="transcribe"))


@app.get("/about", response_class=HTMLResponse)
async def about() -> HTMLResponse:
    return HTMLResponse(_render("about.html", active_tab="about"))


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def cli():
    import os
    import sys
    import uvicorn

    if len(sys.argv) > 1 and sys.argv[1] == "--data-dir":
        from artifice_transcribe.config import settings
        print(str(settings.data_path))
        return

    # Reload is opt-in via ARTIFICE_TRANSCRIBE_RELOAD=1 for development use.
    # The packaged entry point (artifice-transcribe) defaults to off because the
    # file-watching reloader spawns a subprocess, which breaks under PyInstaller
    # and is wasteful in any production run.
    enable_reload = os.environ.get("ARTIFICE_TRANSCRIBE_RELOAD", "").strip() in ("1", "true", "yes")

    uvicorn.run(
        "artifice_transcribe.main:app",
        host=os.environ.get("CALLOSIP_HOST", "127.0.0.1"),
        port=int(os.environ.get("CALLOSIP_PORT", "8000")),
        reload=enable_reload,
        reload_excludes=[
            "data/*",
            "data\\*",
            "uploads/*",
            "uploads\\*",
            "__pycache__/*",
            "__pycache__\\*",
            "*.db",
        ],
    )


if __name__ == "__main__":
    cli()

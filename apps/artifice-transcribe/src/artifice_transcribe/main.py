# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from artifice_transcribe.api.v1.routes import router as v1_router
from artifice_transcribe.config import settings
from artifice_transcribe.db.models import Base
from artifice_transcribe.db.session import engine

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
async def index() -> HTMLResponse:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html.replace("__ASSET_V__", _asset_version()))


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def cli():
    import os
    import uvicorn

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

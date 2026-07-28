from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def cli():
    import os
    import uvicorn

    uvicorn.run(
        "artifice_transcribe.main:app",
        host=os.environ.get("CALLOSIP_HOST", "127.0.0.1"),
        port=int(os.environ.get("CALLOSIP_PORT", "8000")),
        reload=True,
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

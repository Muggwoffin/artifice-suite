# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

"""PDF export routes: start, status, SSE events, download."""

import asyncio
import json
import queue
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from ..models import PdfExportRequest
from ..runtime import pdf_export_state, start_pdf_export
from ..validation import validate_directory

router = APIRouter(tags=["pdf-export"])


@router.post("/api/pdf-export/start")
def pdf_export_start(req: PdfExportRequest) -> dict:
    validate_directory(req.folder, "folder")
    if req.output is not None:
        validate_directory(req.output, "output")
    if req.manifest is not None:
        validate_directory(req.manifest, "manifest")
    started = start_pdf_export(
        req.folder, stage=req.stage,
        structure=req.structure, output=req.output,
        manifest_path=req.manifest,
        format=req.format, style=req.style,
        bilingual=req.bilingual,
    )
    if not started:
        raise HTTPException(
            status_code=409, detail="A PDF export is already running")
    return {"ok": True}


@router.get("/api/pdf-export/status")
def pdf_export_status_route() -> dict:
    return {
        "status": pdf_export_state.status,
        "error": pdf_export_state.error,
        "output_path": pdf_export_state.output_path,
    }


@router.get("/api/pdf-export/events")
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


@router.get("/api/pdf-export/download")
def pdf_export_download():
    if not pdf_export_state.output_path:
        raise HTTPException(status_code=404, detail="No PDF has been compiled yet")
    path = Path(pdf_export_state.output_path)
    ext = path.suffix.lower()
    media_type = "text/markdown" if ext == ".md" else "application/pdf"
    return FileResponse(path, media_type=media_type, filename=path.name)

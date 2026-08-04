# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Queue management routes."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from ..models import (AddPathsRequest, BatchReplaceRequest, RawTextRequest,
                      RemoveRequest, ReorderRequest, ReprocessRequest)
from ..runtime import (_IMAGE_PASSTHROUGH_TYPES, batch_replace, render_page_image,
                       reprocess_item, save_cleaned_text, save_raw_text,
                       save_translated_text, state)
from ..serializers import serialize_item_preview
from ..validation import validate_directory

router = APIRouter(tags=["queue"])


@router.get("/api/queue")
def get_queue() -> dict:
    return {"items": state.queue_snapshot(), "status": state.status()}


@router.post("/api/queue/add-paths")
def add_paths(req: AddPathsRequest) -> dict:
    safe = [validate_directory(p, "path") for p in req.paths]
    added = state.add_paths(safe)
    return {"added": len(added), "items": state.queue_snapshot()}


@router.post("/api/queue/remove")
def remove_items(req: RemoveRequest) -> dict:
    removed = state.remove(req.ids)
    return {"removed": removed, "items": state.queue_snapshot()}


@router.post("/api/queue/clear")
def clear_queue() -> dict:
    state.clear()
    return {"items": []}


@router.get("/api/queue/{item_id}/preview")
def queue_item_preview(item_id: str) -> dict:
    item = state.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found in the queue")
    return serialize_item_preview(item)


@router.get("/api/queue/{item_id}/image")
def queue_item_image(item_id: str):
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


@router.post("/api/queue/{item_id}/raw-text")
def save_raw_text_route(item_id: str, req: RawTextRequest) -> dict:
    item = state.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found in the queue")
    return save_raw_text(item, req.text)


@router.post("/api/queue/{item_id}/cleaned-text")
def save_cleaned_text_route(item_id: str, req: RawTextRequest) -> dict:
    item = state.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found in the queue")
    return save_cleaned_text(item, req.text)


@router.post("/api/queue/{item_id}/translated-text")
def save_translated_text_route(item_id: str, req: RawTextRequest) -> dict:
    item = state.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found in the queue")
    return save_translated_text(item, req.text)


@router.post("/api/queue/{item_id}/reprocess")
def reprocess_item_route(item_id: str, req: ReprocessRequest) -> dict:
    item = state.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found in the queue")
    if req.from_stage not in ("raw", "cleaned", "translate"):
        raise HTTPException(status_code=400, detail="from_stage must be 'raw', 'cleaned', or 'translate'")
    if not req.stages:
        raise HTTPException(status_code=400, detail="No stages to re-run")
    try:
        return reprocess_item(item, req.from_stage, req.stages)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/queue/batch-replace")
def batch_replace_route(req: BatchReplaceRequest) -> dict:
    if not req.find:
        raise HTTPException(status_code=400, detail="find string is required")
    if not req.stages:
        raise HTTPException(status_code=400, detail="At least one stage is required")
    return batch_replace(req.find, req.replace, req.stages, req.item_ids)


@router.post("/api/queue/reorder")
def reorder_queue(req: ReorderRequest) -> dict:
    state.reorder(req.drag_id, req.drop_id, req.before)
    return {"items": state.queue_snapshot()}

# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Queue management routes."""

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

from ..models import (
    AddPathsRequest,
    BatchReplaceRequest,
    RawTextRequest,
    RemoveRequest,
    ReorderRequest,
    ReprocessRequest,
)
from ..runtime import (
    _IMAGE_PASSTHROUGH_TYPES,
    SUPPORTED_EXTENSIONS,
    batch_replace,
    render_page_image,
    reprocess_item,
    save_cleaned_text,
    save_raw_text,
    save_translated_text,
    state,
)
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

    # A Tropy-imported photo may have passed pathcheck but not exist on disk
    # (the import sets a 'missing' flag). FileResponse on a non-existent path
    # produces a raw Starlette 404 with no useful detail; check first so the
    # client gets an actionable message and the preview pane can show it.
    if not Path(item.path).exists():
        raise HTTPException(
            status_code=404,
            detail=f"Source file not found on disk: {Path(item.path).name}",
        )

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


# ── File upload ────────────────────────────────────────────────────────────
# Mirrors artifice-graph's api_upload_files and the _read_capped /
# _sanitise_path_component helpers carried by graph, draft and transcribe.
# Deliberately a fourth copy rather than a new shared abstraction —
# consolidation is a separate brief.

_MAX_UPLOAD_BYTES: int = 50 * 1024 * 1024  # 50 MB


async def _read_capped(upload: UploadFile, limit: int) -> bytes:
    """Read *upload* in bounded 64 KB chunks, raising HTTP 413 if *limit* is
    exceeded **during** the read so an oversized body is never fully resident.
    """
    chunks: list[bytes] = []
    total = 0
    while chunk := await upload.read(64 * 1024):
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds {limit // (1024 * 1024)} MB upload limit",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _sanitise_path_component(raw: str) -> str:
    """Return a safe single-component filename from *raw*.

    Treats backslashes as separators (Windows path support) and rejects
    components that are empty, ``"."`` or ``".."`` after cleaning.
    """
    cleaned = Path(raw.replace("\\", "/")).name
    if cleaned in ("", ".", ".."):
        raise HTTPException(status_code=400, detail=f"Invalid filename: {raw!r}")
    return cleaned


def _staging_dir() -> Path:
    """Directory uploaded files are staged into, created on demand.

    Lives beside settings.json (``~/.artifice_ocr/``) rather than under a
    platformdirs path — this app deliberately does not use platformdirs.
    """
    return Path.home() / ".artifice_ocr" / "uploads"


def _unique_dest(staging: Path, safe_name: str) -> Path:
    """Return a non-colliding destination for *safe_name* inside *staging*.

    Two uploads named ``page1.jpg`` must both survive: the second becomes
    ``page1_1.jpg`` (then ``page1_2.jpg``, …) rather than overwriting the
    first or anything already staged.
    """
    dest = staging / safe_name
    if not dest.exists():
        return dest
    stem = Path(safe_name).stem
    suffix = Path(safe_name).suffix
    counter = 1
    while True:
        candidate = staging / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


@router.post("/api/queue/upload")
async def upload_files(files: list[UploadFile] = File(...)) -> dict:
    """Upload one or more files into the pipeline's staging directory.

    Filenames are sanitised with the same ``_sanitise_path_component`` guard
    the other three apps use to prevent path traversal. Anything whose
    extension is not in ``SUPPORTED_EXTENSIONS`` is rejected per-file, and
    files larger than 50 MB are refused during the read.

    **This is a batch endpoint and always returns HTTP 200** when the request
    itself is well-formed. Per-file outcomes are reported in the response
    body alongside the usual ``add-paths`` keys:

        {"uploaded": [{"filename": ..., "status": "ok"},
                      {"filename": ..., "status": "rejected", "reason": ...}],
         "added": ..., "items": [...]}

    One unacceptable file must not fail an otherwise good batch — a user
    dropping twelve files should get the eleven valid ones staged and a
    specific reason for the twelfth, not a single opaque error.

    A malformed filename (empty, ``"."`` or ``".."`` after cleaning) is the
    one case that does raise — HTTP 400 — because it indicates a crafted
    request rather than a user picking the wrong file.
    """
    staging = _staging_dir()
    staging.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    staged_paths: list[str] = []
    for upload in files:
        raw_name = upload.filename or ""
        safe_name = _sanitise_path_component(raw_name)
        ext = Path(safe_name).suffix.lower()

        if ext not in SUPPORTED_EXTENSIONS:
            results.append(
                {
                    "filename": raw_name,
                    "status": "rejected",
                    "reason": f"Extension {ext!r} not accepted. "
                    f"Allowed: {sorted(SUPPORTED_EXTENSIONS)}",
                }
            )
            continue

        try:
            contents = await _read_capped(upload, _MAX_UPLOAD_BYTES)
        except HTTPException:
            results.append(
                {
                    "filename": raw_name,
                    "status": "rejected",
                    "reason": "File exceeds 50 MB limit",
                }
            )
            continue

        dest = _unique_dest(staging, safe_name)
        dest.write_bytes(contents)
        staged_paths.append(str(dest))
        results.append({"filename": safe_name, "status": "ok"})

    added = state.add_paths(staged_paths)
    return {
        "uploaded": results,
        "added": len(added),
        "items": state.queue_snapshot(),
    }

# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Live read-only .tpy browse routes — feature-flagged.

Only mounted when ARTIFICE_OCR_TROPY_LIVE_READ=1. Provides browsing of
Tropy projects, lists, tags, items, and photos directly from a .tpy file,
plus enqueueing items for OCR without a manual JSON-LD export.
"""

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from ..._logging import get_logger
from ...tropy_db import (
    TropyDBError,
    get_item,
    items_to_job_items,
    list_items,
    list_lists,
    list_projects,
    list_tags,
)
from ...validation import validate_path
from ..models import TropyBrowseRequest, TropyEnqueueRequest
from ..runtime import state

log = get_logger("tropy_browse")

router = APIRouter(tags=["tropy-browse"])

_LIVE_READ_ENABLED = os.environ.get("ARTIFICE_OCR_TROPY_LIVE_READ", "0") == "1"


def _check_enabled() -> None:
    if not _LIVE_READ_ENABLED:
        raise HTTPException(
            status_code=404, detail="Live Tropy browse is not enabled"
        )


def _resolve_db_path(raw: str) -> Path:
    """Validate and return the .tpy database path."""
    validated = validate_path(raw, "path")
    return Path(validated)


def _resolve_output_dir(raw: str) -> str:
    """Validate and return the output directory path."""
    return validate_path(raw, "output_dir")


# --------------------------------------------------------------------------- #
# browse routes
# --------------------------------------------------------------------------- #


@router.post("/api/tropy/browse/projects")
def browse_projects(req: TropyBrowseRequest) -> dict:
    """List all projects in a Tropy .tpy database."""
    _check_enabled()
    try:
        db_path = _resolve_db_path(req.path)
        projects = list_projects(db_path)
    except TropyDBError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"projects": projects}


@router.post("/api/tropy/browse/lists")
def browse_lists(req: TropyBrowseRequest) -> dict:
    """List all lists in a Tropy .tpy database."""
    _check_enabled()
    try:
        db_path = _resolve_db_path(req.path)
        lists = list_lists(db_path)
    except TropyDBError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"lists": lists}


@router.post("/api/tropy/browse/tags")
def browse_tags(req: TropyBrowseRequest) -> dict:
    """List all tags in a Tropy .tpy database."""
    _check_enabled()
    try:
        db_path = _resolve_db_path(req.path)
        tags = list_tags(db_path)
    except TropyDBError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"tags": tags}


@router.post("/api/tropy/browse/items")
def browse_items(
    req: TropyBrowseRequest,
    list_id: int | None = Query(None),
    tag: str | None = Query(None),
) -> dict:
    """List items in a Tropy .tpy database, optionally filtered.

    Query parameters:
    - ``list_id``: filter items to a specific list
    - ``tag``: filter items to a specific tag name
    """
    _check_enabled()
    try:
        db_path = _resolve_db_path(req.path)
        items = list_items(db_path, list_id=list_id, tag=tag)
    except TropyDBError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "items": [
            {
                "item_id": it.item_id,
                "title": it.title,
                "photo_count": len(it.photos),
                "missing_count": sum(1 for p in it.photos if p.missing),
                "photos": [
                    {
                        "photo_id": p.photo_id,
                        "path": p.path,
                        "page": p.page,
                        "mimetype": p.mimetype,
                        "checksum": p.checksum,
                        "orientation": p.orientation,
                        "missing": p.missing,
                    }
                    for p in it.photos
                ],
            }
            for it in items
        ]
    }


@router.post("/api/tropy/browse/items/{item_id}")
def browse_single_item(req: TropyBrowseRequest, item_id: int) -> dict:
    """Get a single item with its photos from a Tropy .tpy database."""
    _check_enabled()
    try:
        db_path = _resolve_db_path(req.path)
        item = get_item(db_path, item_id)
        if item is None:
            raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
        return {
            "item": {
                "item_id": item.item_id,
                "title": item.title,
                "photo_count": len(item.photos),
                "missing_count": sum(1 for p in item.photos if p.missing),
                "photos": [
                    {
                        "photo_id": p.photo_id,
                        "path": p.path,
                        "page": p.page,
                        "mimetype": p.mimetype,
                        "checksum": p.checksum,
                        "orientation": p.orientation,
                        "missing": p.missing,
                    }
                    for p in item.photos
                ],
            }
        }
    except TropyDBError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# --------------------------------------------------------------------------- #
# enqueue route
# --------------------------------------------------------------------------- #


@router.post("/api/tropy/browse/enqueue")
def enqueue_from_tropy(req: TropyEnqueueRequest) -> dict:
    """Enqueue items from a live .tpy browse for OCR processing."""
    _check_enabled()
    try:
        db_path = _resolve_db_path(req.path)
        output_dir = _resolve_output_dir(req.output_dir)
        items = []
        for item_id in req.item_ids:
            item = get_item(db_path, item_id)
            if item is not None:
                items.append(item)
        job_items = items_to_job_items(items, output_dir=output_dir)
        added = state.add_items(job_items)
        return {"added": len(added), "items": state.queue_snapshot()}
    except TropyDBError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tropy JSON-LD bridge routes: import preview, import add, export, export history."""

import contextlib
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response

from ..._logging import get_logger
from ...tropy_jsonld import (
    ExportPhoto,
    TropyImportError,
    export_json,
    load_export,
    load_export_content,
    photos_to_job_items,
    write_manifest,
)
from ..models import (
    TropyExportHistoryRequest,
    TropyExportRequest,
    TropyImportAddRequest,
    TropyImportRequest,
)
from ..runtime import state

log = get_logger("tropy_bridge")

router = APIRouter(tags=["tropy"])


# --------------------------------------------------------------------------- #
# import: preview
# --------------------------------------------------------------------------- #


@router.post("/api/tropy/import/preview")
def tropy_import_preview(req: TropyImportRequest) -> dict:
    """Parse a Tropy JSON-LD export and return a summary of what's in it."""
    try:
        preview = (
            load_export(req.path)
            if req.path is not None
            else load_export_content(req.content, filename=req.filename)
        )
    except TropyImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        log.exception("Unexpected error parsing Tropy export")
        raise HTTPException(
            status_code=400, detail="Could not parse the export file"
        ) from None

    return {
        "export_name": preview.export_name,
        "items": [
            {
                "group": item.group,
                "title": item.title,
                "photo_count": len(item.photos),
                "missing_count": sum(1 for p in item.photos if p.missing),
            }
            for item in preview.items
        ],
        "warnings": preview.warnings,
    }


# --------------------------------------------------------------------------- #
# import: add to queue
# --------------------------------------------------------------------------- #


@router.post("/api/tropy/import/add")
def tropy_import_add(req: TropyImportAddRequest) -> dict:
    """Add photos from a Tropy JSON-LD export to the processing queue."""
    try:
        preview = (
            load_export(req.path)
            if req.path is not None
            else load_export_content(req.content, filename=req.filename)
        )
    except TropyImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        log.exception("Unexpected error parsing Tropy export")
        raise HTTPException(
            status_code=400, detail="Could not parse the export file"
        ) from None

    items = photos_to_job_items(preview, groups=req.groups)

    # Collect missing labels for reporting
    missing_labels: list[str] = []
    for item in preview.items:
        if req.groups is not None and item.group not in set(req.groups):
            continue
        for photo in item.photos:
            if photo.missing:
                is_pdf = (
                    photo.mimetype == "application/pdf"
                    or photo.resolved.suffix.lower() == ".pdf"
                )
                name = Path(photo.path_rel).name
                if is_pdf and photo.page is not None:
                    missing_labels.append(f"{name}  p.{photo.page + 1}")
                else:
                    missing_labels.append(name)

    # Write manifest (swallow failure)
    with contextlib.suppress(Exception):
        write_manifest(req.output_dir, preview)

    added = state.add_items(items)
    return {
        "added": len(added),
        "missing": missing_labels,
        "items": state.queue_snapshot(),
    }


# --------------------------------------------------------------------------- #
# export: queue items
# --------------------------------------------------------------------------- #


_STAGE_COLUMNS = {
    "raw_ocr": ("raw", "extracted_text"),
    "cleaned": ("cleaned", "cleaned_text"),
    "translated": ("translated", "translated_text"),
}


def _eligible_photos_for_export(
    item_ids: list[str] | None, stage: str
) -> list[ExportPhoto]:
    """Walk eligible queue items and build :class:`ExportPhoto` objects."""
    items = state.tropy_eligible_items(item_ids)
    stage_key, text_key = _STAGE_COLUMNS.get(stage, ("cleaned", "cleaned_text"))

    photos: list[ExportPhoto] = []
    for item in items:
        src = item.source or {}
        text = (item.results.get(stage_key) or {}).get(text_key, "") or ""
        item_node = src.get("item_node")

        photos.append(
            ExportPhoto(
                abs_path=Path(item.path),
                text=text,
                label=item.name,
                language=item.language or "de",
                item_node=item_node,
                group=src.get("tropy_group"),
                photo_index=src.get("photo_index"),
                path_rel=src.get("photo_path_rel"),
                checksum=src.get("checksum", ""),
                mimetype=src.get("mimetype", ""),
            )
        )
    return photos


@router.post("/api/tropy/export")
def tropy_export(req: TropyExportRequest):
    """Generate a Tropy JSON-LD file from eligible queue items.

    If ``req.path`` is provided the JSON-LD is written to that path on
    disk and a JSON summary is returned.  Otherwise the content is
    returned as a download response (browser dev-mode fallback).
    """
    photos = _eligible_photos_for_export(req.item_ids, req.stage)
    photos_with_text = [p for p in photos if p.text.strip()]

    if not photos_with_text and not any(p.text.strip() for p in photos):
        raise HTTPException(
            status_code=409,
            detail="No eligible photos with text — run the pipeline first",
        )

    content = export_json(photos)

    if req.path:
        out = Path(req.path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")
        return {"path": str(out), "filename": out.name}

    return Response(
        content=content,
        media_type="application/ld+json",
        headers={
            "Content-Disposition": 'attachment; filename="artifice-ocr-tropy.jsonld"',
        },
    )


# --------------------------------------------------------------------------- #
# export: history items
# --------------------------------------------------------------------------- #


def _eligible_photos_from_history(
    item_ids: list[int], stage: str
) -> list[ExportPhoto]:
    """Build :class:`ExportPhoto` objects from history DB rows."""
    text_col = {
        "raw_ocr": "raw_text",
        "cleaned": "cleaned_text",
        "translated": "translated_text",
    }.get(stage, "cleaned_text")

    photos: list[ExportPhoto] = []
    for item_id in item_ids:
        row = state.history.get_item(item_id)
        if row is None:
            continue

        # Must be exportable (has a stored item_node)
        if not row["tropy_item_node"]:
            continue

        text = row[text_col] or ""
        try:
            item_node = json.loads(row["tropy_item_node"])
        except (json.JSONDecodeError, TypeError):
            item_node = None

        source_path = Path(row["source_file"])
        photos.append(
            ExportPhoto(
                abs_path=source_path,
                text=text,
                label=row["name"] or f"item {row['item_id']}",
                language=row["language"] or "de",
                item_node=item_node,
                group=row["tropy_group"] or None,
                photo_index=None,
                path_rel=row["tropy_photo_path"] or None,
                checksum="",
                mimetype="",
            )
        )
    return photos


@router.post("/api/tropy/export/history")
def tropy_export_history(req: TropyExportHistoryRequest):
    """Generate a Tropy JSON-LD file from history DB rows.

    If ``req.path`` is provided the JSON-LD is written to that path on
    disk and a JSON summary is returned.  Otherwise the content is
    returned as a download response (browser dev-mode fallback).
    """
    photos = _eligible_photos_from_history(req.item_ids, req.stage)
    photos_with_text = [p for p in photos if p.text.strip()]

    if not photos_with_text:
        raise HTTPException(
            status_code=409,
            detail="No exportable items — text may be empty or items not from Tropy JSON-LD bridge",
        )

    content = export_json(photos)

    if req.path:
        out = Path(req.path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")
        return {"path": str(out), "filename": out.name}

    return Response(
        content=content,
        media_type="application/ld+json",
        headers={
            "Content-Disposition": 'attachment; filename="artifice-ocr-tropy.jsonld"',
        },
    )

"""Tropy integration routes: browse, add, send preview, send write."""

from fastapi import APIRouter, HTTPException

from ..models import (
    TropyAddRequest,
    TropyBrowseRequest,
    TropySendHistoryRequest,
    TropySendHistoryWriteRequest,
    TropySendRequest,
    TropySendWriteRequest,
)
from ..runtime import state
from ...tropy import TropyProject, pages_to_job_items, recent_projects, write_manifest

router = APIRouter(tags=["tropy"])


@router.get("/api/tropy/recent")
def tropy_recent() -> dict:
    return {"projects": [str(p) for p in recent_projects()]}


@router.post("/api/tropy/browse")
def tropy_browse(req: TropyBrowseRequest) -> dict:
    try:
        with TropyProject(req.project) as proj:
            if req.list_id is not None:
                ids = proj.item_ids_in_list(req.list_id)
            elif req.tag:
                ids = proj.item_ids_with_tag(req.tag)
            else:
                ids = req.item_ids

            return {
                "project": proj.name,
                "lists": [
                    {"list_id": l.list_id, "name": l.name,
                     "parent_id": l.parent_id, "depth": l.depth,
                     "item_count": l.item_count}
                    for l in proj.lists()
                ],
                "tags": [{"name": n, "count": c} for n, c in proj.tags() if c],
                "items": [
                    {"item_id": i.item_id, "title": i.title,
                     "photo_count": i.photo_count}
                    for i in proj.items(ids)
                ],
            }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/tropy/add")
def tropy_add(req: TropyAddRequest) -> dict:
    try:
        with TropyProject(req.project) as proj:
            pages = proj.pages(req.item_ids)
            missing = [p.label for p in proj.missing_assets(pages)]
            items = pages_to_job_items(pages, project_path=proj.db_path)
            try:
                write_manifest(req.output_dir, proj, pages)
            except Exception:
                pass
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    added = state.add_items(items)
    return {
        "added": len(added),
        "missing": missing,
        "items": state.queue_snapshot(),
    }


def _build_tropy_preview(req: TropySendRequest):
    from ...tropy_write import TropyWriter, entries_from_items

    items = state.tropy_eligible_items(req.item_ids)
    entries = entries_from_items(items, stage=req.stage)
    with TropyWriter(req.project) as writer:
        return writer.preview(entries, req.targets)


@router.post("/api/tropy/send/preview")
def tropy_send_preview(req: TropySendRequest) -> dict:
    try:
        preview = _build_tropy_preview(req)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "blockers": preview.blockers,
        "summary": preview.summary(),
        "insertable": len(preview.insertable),
        "plans": [
            {"label": p.entry.label or f"photo {p.entry.photo_id}",
             "target": p.target, "action": p.action, "reason": p.reason}
            for p in preview.plans
        ],
    }


@router.post("/api/tropy/send/write")
def tropy_send_write(req: TropySendWriteRequest) -> dict:
    from ...tropy_write import TropyWriter

    try:
        preview = _build_tropy_preview(req)
        if preview.blockers:
            raise HTTPException(status_code=409, detail="; ".join(preview.blockers))
        with TropyWriter(req.project) as writer:
            report = writer.write(preview, make_backup=req.make_backup)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if report.errors:
        raise HTTPException(status_code=500, detail="; ".join(report.errors))

    return {
        "written": report.written,
        "skipped": report.skipped,
        "backup": str(report.backup) if report.backup else None,
    }


# --------------------------------------------------------------------------- #
# History‑based send (items already processed, stored in history DB)
# --------------------------------------------------------------------------- #

_TEXT_COLUMNS = {
    "raw_ocr": "raw_text",
    "cleaned": "cleaned_text",
    "translated": "translated_text",
}


def _entries_from_history_items(item_ids: list[int], stage: str):
    """Build WriteEntry list from history DB rows."""
    from ...tropy_write import WriteEntry

    text_col = _TEXT_COLUMNS.get(stage, "cleaned_text")
    entries = []
    for item_id in item_ids:
        row = state.history.get_item(item_id)
        if row is None:
            continue
        photo_id = row["photo_id"]
        if photo_id is None:
            continue
        entries.append(WriteEntry(
            photo_id=photo_id,
            text=row[text_col] or "",
            label=row["name"] or f"item {row['item_id']}",
            language=row["language"] or "",
            stage=stage,
        ))
    return entries


def _build_tropy_history_preview(req: TropySendHistoryRequest):
    from ...tropy_write import TropyWriter

    entries = _entries_from_history_items(req.item_ids, stage=req.stage)
    with TropyWriter(req.project) as writer:
        return writer.preview(entries, req.targets)


@router.post("/api/tropy/send/history/preview")
def tropy_send_history_preview(req: TropySendHistoryRequest) -> dict:
    try:
        preview = _build_tropy_history_preview(req)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "blockers": preview.blockers,
        "summary": preview.summary(),
        "insertable": len(preview.insertable),
        "plans": [
            {"label": p.entry.label or f"photo {p.entry.photo_id}",
             "target": p.target, "action": p.action, "reason": p.reason}
            for p in preview.plans
        ],
    }


@router.post("/api/tropy/send/history/write")
def tropy_send_history_write(req: TropySendHistoryWriteRequest) -> dict:
    from ...tropy_write import TropyWriter

    try:
        preview = _build_tropy_history_preview(req)
        if preview.blockers:
            raise HTTPException(status_code=409, detail="; ".join(preview.blockers))
        with TropyWriter(req.project) as writer:
            report = writer.write(preview, make_backup=req.make_backup)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if report.errors:
        raise HTTPException(status_code=500, detail="; ".join(report.errors))

    return {
        "written": report.written,
        "skipped": report.skipped,
        "backup": str(report.backup) if report.backup else None,
    }

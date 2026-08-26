# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tropy write-back routes: preview and commit, feature-flagged.

Wires :mod:`artifice_ocr.tropy_write` to the web layer. Both routes are gated
on ``tropy_writeback_enabled`` (default off) and return 404 when disabled, so
an off feature does not advertise itself. The commit route recomputes the
preview server-side and never trusts a client-supplied count — a freshly
appearing blocker or a count that no longer matches is a 409 and writes
nothing.

Only notes (:data:`TropyWriter` target ``notes``) are written; transcriptions
remain unexposed until the flow is proven.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ... import config
from ..._logging import get_logger
from ...tropy_db import resolve_project_db_path
from ...tropy_write import (
    TARGET_NOTES,
    TropyWriter,
    _display_path,
    entries_from_items,
)
from ..runtime import state
from ..validation import validate_directory

log = get_logger("tropy_writeback")

router = APIRouter(tags=["tropy-writeback"])

_VALID_STAGES = ("raw_ocr", "cleaned", "translated")


class TropyWritebackPreviewRequest(BaseModel):
    project_path: str | None = None
    stage: str = "cleaned"
    item_ids: list[str] | None = None


class TropyWritebackCommitRequest(TropyWritebackPreviewRequest):
    expected_write_count: int


def _writeback_enabled() -> bool:
    return bool(config.get("tropy_writeback_enabled", False))


def _check_enabled() -> None:
    if not _writeback_enabled():
        raise HTTPException(status_code=404, detail="Tropy write-back is not enabled")


def _resolve_db_path(raw: str | None) -> Path:
    """Validate ``raw`` (falling back to the last-used project) and resolve it
    to the ``.tpy`` file — the same ``validate_directory`` +
    ``resolve_project_db_path`` pair :func:`tropy_browse._resolve_db_path` uses.
    """
    if raw is None:
        raw = config.get("tropy_last_path")
    if not raw:
        raise HTTPException(status_code=400, detail="No Tropy project selected")
    validated = validate_directory(raw, "path")
    return resolve_project_db_path(validated)


def _split_by_project(items, db_path: Path):
    """Split writable items into those from the target project and the rest.

    ``entries_from_items`` requires only a ``photo_id``; it does not know which
    project that id belongs to. Tropy ids are per-project, so an item browsed
    from project A must never be written into project B — a match lands a note
    on a different photo entirely. An item with no ``tropy_project`` recorded
    cannot be proven to belong here, so it is refused too (fail closed).
    """
    target = db_path.resolve()
    eligible = []
    foreign = []
    for i in items:
        project = (i.source or {}).get("tropy_project")
        if project is not None and Path(project).resolve() == target:
            eligible.append(i)
        else:
            foreign.append(i)
    return eligible, foreign


def _prepare(req):
    """Validate the stage, resolve the project path, and build write entries
    from the selected items.

    Shared by preview and commit so both compute identical results.
    Returns ``(db_path, entries, eligible, foreign, ineligible)``.
    """
    if req.stage not in _VALID_STAGES:
        raise HTTPException(status_code=400, detail=f"Unknown stage: {req.stage}")
    db_path = _resolve_db_path(req.project_path)
    items = state.tropy_writable_items(req.item_ids)
    eligible_items, foreign_items = _split_by_project(items, db_path)
    entries = entries_from_items(eligible_items, stage=req.stage)
    if req.item_ids is not None:
        selected = sum(1 for i in req.item_ids if state.get(i) is not None)
    else:
        selected = len(state.items)
    ineligible = selected - len(items)
    return db_path, entries, len(eligible_items), len(foreign_items), ineligible


@router.post("/api/tropy/writeback/preview")
def tropy_writeback_preview(req: TropyWritebackPreviewRequest) -> dict:
    """Report what a write-back would do, without writing anything."""
    _check_enabled()
    db_path, entries, eligible, foreign, ineligible = _prepare(req)

    try:
        with TropyWriter(db_path) as writer:
            preview = writer.preview(entries, [TARGET_NOTES])
    except FileNotFoundError as exc:
        # ``TropyWriter`` raises this with a ``_display_path``-redacted message.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "blockers": preview.blockers,
        "counts": preview.counts(),
        "summary": preview.summary(),
        "eligible": eligible,
        "ineligible": ineligible,
        "foreign": foreign,
    }


@router.post("/api/tropy/writeback/commit")
def tropy_writeback_commit(req: TropyWritebackCommitRequest) -> dict:
    """Apply an approved write-back, recomputing the preview first.

    Never trusts a client-supplied preview: the insertable count is recomputed
    and blockers re-checked. A mismatch or a blocker is a 409 and writes
    nothing — the project changed between preview and commit, and the user
    should look again.
    """
    _check_enabled()
    db_path, entries, _eligible, foreign, _ineligible = _prepare(req)

    if foreign:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{foreign} selected item(s) do not belong to this Tropy "
                "project — please preview again before writing"
            ),
        )

    try:
        with TropyWriter(db_path) as writer:
            preview = writer.preview(entries, [TARGET_NOTES])
            if preview.blockers:
                raise HTTPException(
                    status_code=409,
                    detail={"blockers": preview.blockers},
                )
            if len(preview.insertable) != req.expected_write_count:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "The project changed since the preview — "
                        "please preview again before writing"
                    ),
                )
            report = writer.write(preview)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "written": report.written,
        "skipped": report.skipped,
        "errors": report.errors,
        "backup_path": _display_path(report.backup) if report.backup is not None else None,
    }

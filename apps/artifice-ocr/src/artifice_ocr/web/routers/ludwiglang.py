# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

"""LudwigLang export routes: list collections, export .md."""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ...config import get as config_get
from ..models import LudwigLangExportRequest
from ..validation import validate_contained

router = APIRouter(tags=["ludwiglang"])


def _collections(output_dir: str) -> list[str]:
    cleaned_text = Path(output_dir) / "cleaned" / "text"
    if not cleaned_text.exists():
        return []
    return sorted(
        d.name for d in cleaned_text.iterdir()
        if d.is_dir()
    )


@router.get("/api/ludwiglang/collections")
def ludwiglang_collections(output_dir: str = "output") -> dict:
    return {"collections": _collections(output_dir)}


@router.post("/api/ludwiglang/export")
def ludwiglang_export(req: LudwigLangExportRequest) -> dict:
    from ...export_ludwiglang import export_md, _read_manifest

    cleaned_root = Path(req.output_dir) / "cleaned" / "text" / req.collection
    if not cleaned_root.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Collection '{req.collection}' not found at {cleaned_root}",
        )

    manifest = _read_manifest(Path(req.output_dir))

    try:
        result_path = export_md(
            cleaned_root,
            medium=req.medium,
            author=req.author or "",
            date=req.date or "",
            page_markers=req.page_markers,
            manifest=manifest,
            skip_language_gate=req.skip_language_gate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "path": str(result_path),
        "filename": result_path.name,
        "collection": req.collection,
        "page_count": None,
        "skipped_count": None,
    }


@router.get("/api/ludwiglang/download")
def ludwiglang_download(path: str) -> FileResponse:
    output_dir = config_get("output_dir", "output")
    # must_exist=False so that containment is enforced without existence being
    # folded into the same answer: a file inside output_dir that is simply not
    # there is a 404 below, while anything outside it is a 400 from the
    # validator. Requiring existence here would make every miss a 400.
    normalised = validate_contained(path, output_dir, "path", must_exist=False)
    p = Path(normalised)
    if not p.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(p, media_type="text/markdown", filename=p.name)

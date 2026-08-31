# SPDX-FileCopyrightText: 2026 Maurice Casey
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Resolve OCR stage directories in canonical and legacy output layouts."""

from pathlib import Path

_CANONICAL = {
    "raw_ocr": "raw-ocr",
    "title": "titles",
    "structured": "structured",
    "cleaned": "cleaned",
    "translated": "translated",
}


def stage_dir(output_dir: str | Path, stage: str) -> Path:
    root = Path(output_dir)
    if (root / "project.json").is_file() and (root / "pipeline").is_dir():
        return root / "pipeline" / _CANONICAL.get(stage, stage)
    return root / stage


def record_dir(output_dir: str | Path, stage: str) -> Path:
    """Return the metadata directory, retaining ``json`` for legacy roots."""
    root = Path(output_dir)
    return stage_dir(root, stage) / ("records" if (root / "project.json").is_file() else "json")

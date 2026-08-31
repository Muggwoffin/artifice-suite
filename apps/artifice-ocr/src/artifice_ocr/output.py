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

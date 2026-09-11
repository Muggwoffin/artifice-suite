# SPDX-FileCopyrightText: 2026 Maurice Casey
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Resolve OCR stage directories in canonical and legacy output layouts."""

import json
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


def write_stage_output(
    output_dir: str | Path,
    stage: str,
    base_name: str,
    *,
    text_content: str,
    metadata: dict,
) -> None:
    """Write a stage's text output and its JSON metadata sidecar.

    Creates the stage's text/ and json-or-records/ directories as needed.
    Every stage in apps/artifice-ocr/src/artifice_ocr/stages/ writes its
    output this same way; this is the single implementation.
    """
    output_path = Path(output_dir)
    text_dir = stage_dir(output_path, stage) / "text"
    json_dir = record_dir(output_path, stage)
    text_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)

    text_path = text_dir / f"{base_name}.txt"
    json_path = json_dir / f"{base_name}.json"
    text_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    with open(text_path, "w", encoding="utf-8") as f:
        f.write(text_content)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

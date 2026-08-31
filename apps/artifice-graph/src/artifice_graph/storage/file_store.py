# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class FileStore:
    """JSON-file persistence for pipeline artefacts."""

    def __init__(self, output_dir: str | Path) -> None:
        root = Path(output_dir)
        if (root / "project.json").is_file() and (root / "pipeline").is_dir():
            root = root / "pipeline" / "graph"
        self.output_dir = root
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save(self, filename: str, data: list[dict[str, Any]]) -> Path:
        path = self.output_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        return path

    def load(self, filename: str) -> list[dict[str, Any]]:
        path = self.output_dir / filename
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_models(self, filename: str, models: list[BaseModel]) -> Path:
        return self.save(filename, [m.model_dump(mode="json") for m in models])

    def load_as_dicts(self, filename: str) -> list[dict[str, Any]]:
        return self.load(filename)

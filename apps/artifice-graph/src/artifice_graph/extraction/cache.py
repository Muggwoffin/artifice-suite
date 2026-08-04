# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from artifice_graph.config import ExtractionConfig


def _cache_key(model: str, user_prompt: str) -> str:
    key = f"{model}::{user_prompt}"
    return hashlib.sha256(key.encode()).hexdigest()


class LLMResponseCache:
    """Disk-backed cache for LLM responses keyed by (model, prompt_hash)."""

    def __init__(self, config: ExtractionConfig) -> None:
        self._cache_dir = Path(config.cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._hits = 0
        self._misses = 0

    def get(self, model: str, prompt: str) -> str | None:
        path = self._path(model, prompt)
        if path.exists():
            self._hits += 1
            return path.read_text(encoding="utf-8")
        self._misses += 1
        return None

    def set(self, model: str, prompt: str, response: str) -> None:
        path = self._path(model, prompt)
        path.write_text(response, encoding="utf-8")

    def _path(self, model: str, prompt: str) -> Path:
        return self._cache_dir / _cache_key(model, prompt)

    @property
    def stats(self) -> dict[str, int]:
        return {"hits": self._hits, "misses": self._misses}

    def clear(self) -> None:
        for f in self._cache_dir.iterdir():
            if f.is_file():
                f.unlink()
        self._hits = 0
        self._misses = 0

# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

"""Journal style guide registry and loaders.

Built-in guides (Chicago, MLA, APA) are always available. Custom guides
are loaded from JSON files in ``~/.artifice_draft/style_guides/``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .apa import apa_guide
from .base import StyleGuide
from .chicago import chicago_guide
from .mla import mla_guide

logger = logging.getLogger(__name__)

_CUSTOM_DIR = Path.home() / ".artifice_draft" / "style_guides"

_BUILTIN_GUIDES: dict[str, callable] = {
    "chicago": chicago_guide,
    "mla": mla_guide,
    "apa": apa_guide,
}


def list_guides() -> list[str]:
    """Return the names of all available style guides (built-in + custom)."""
    names = list(_BUILTIN_GUIDES.keys())
    names.extend(list_custom_guides())
    return names


def list_custom_guides() -> list[str]:
    """Return the names of user-created custom style guides."""
    if not _CUSTOM_DIR.exists():
        return []
    return [
        p.stem
        for p in _CUSTOM_DIR.glob("*.json")
        if p.is_file()
    ]


def load_guide(name: str) -> StyleGuide | None:
    """Load a style guide by name. Checks built-ins first, then custom.

    Returns ``None`` if the name is not found.
    """
    name_lower = name.lower().strip()

    if name_lower in _BUILTIN_GUIDES:
        return _BUILTIN_GUIDES[name_lower]()

    custom_path = _CUSTOM_DIR / f"{name_lower}.json"
    if custom_path.exists():
        return load_guide_by_path(str(custom_path))

    return None


def load_guide_by_path(path: str) -> StyleGuide | None:
    """Load a custom style guide from a JSON file.

    Returns ``None`` if the file cannot be read or parsed.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return StyleGuide.from_dict(data)
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        logger.warning("Failed to load style guide from %s: %s", path, exc)
        return None


def save_custom_guide(name: str, guide: StyleGuide) -> Path:
    """Save a custom style guide as a JSON file.

    Returns the path to the saved file.
    """
    _CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    path = _CUSTOM_DIR / f"{name.lower().strip()}.json"
    path.write_text(json.dumps(guide.to_dict(), indent=2), encoding="utf-8")
    logger.info("Saved custom style guide to %s", path)
    return path


def delete_custom_guide(name: str) -> bool:
    """Delete a custom style guide. Returns True if deleted."""
    path = _CUSTOM_DIR / f"{name.lower().strip()}.json"
    if path.exists() and path.is_file():
        path.unlink()
        logger.info("Deleted custom style guide %s", path)
        return True
    return False

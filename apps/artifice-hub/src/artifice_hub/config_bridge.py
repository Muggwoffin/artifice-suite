# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Cross-app config bridge — Hub writes model choices to target app configs.

When a user picks an installed model for a role in the Hub's engine modal,
this module persists that choice into the target app's settings file so the
app picks it up on next launch.

Each app uses a different config path and key scheme.  This module knows the
mapping for every registered app.  Where an app's config schema is richer than
a flat key-value file (e.g. ``artifice-graph``'s nested ``config.json``), the
write is kept minimal — we only touch the model-name field(s).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from secure_io import write_private_json

# ---------------------------------------------------------------------------
# Per-app role → (config_path_factory, config_key) mapping
# ---------------------------------------------------------------------------
# For OCR:  ~/.artifice_ocr/settings.json  (flat JSON, PERSISTED_KEYS)
# For Draft: ~/.artifice_draft/web_settings.json  (flat JSON)
# For Graph: platformdirs config.json  (nested JSON: llm.model, embedding.model)
# Transcribe has no Ollama-relevant model config — no mapping needed.
# ---------------------------------------------------------------------------

_OCR_DIR = Path.home() / ".artifice_ocr"
_OCR_SETTINGS = _OCR_DIR / "settings.json"

_DRAFT_DIR = Path.home() / ".artifice_draft"
_DRAFT_SETTINGS = _DRAFT_DIR / "web_settings.json"


def _graph_config_path() -> Path:
    """Return the graph config path, matching config_helper.CONFIG_FILE."""
    import platformdirs

    return Path(platformdirs.user_data_dir("artifice-graph", "ArtificeSuite")) / "config.json"


def _ocr_settings_path() -> Path:
    return _OCR_SETTINGS


def _draft_settings_path() -> Path:
    return _DRAFT_SETTINGS


# (app_slug, registry_role) → (path_factory, config_key)
_ROLE_KEY_MAP: dict[tuple[str, str], tuple[Callable[[], Path], str]] = {
    ("artifice-ocr", "vision"): (_ocr_settings_path, "ocr_model"),
    ("artifice-ocr", "chat"): (_ocr_settings_path, "cleanup_model"),
    ("artifice-ocr", "translation"): (_ocr_settings_path, "translate_model"),
    ("artifice-draft", "chat"): (_draft_settings_path, "model_name"),
    ("artifice-graph", "chat"): (_graph_config_path, "llm.model"),
    ("artifice-graph", "embedding"): (_graph_config_path, "embedding.model"),
}


def _read_json(path: Path) -> dict[str, Any]:
    """Read a JSON file, returning {} if it doesn't exist."""
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh) or {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    """Write JSON with restricted permissions, merging onto existing content.

    Raises:
        PermissionError: if the file cannot be verified as restricted-access
            after one retry — mirrors the guarantee each target app's own
            save path (OCR's save_user_settings, Draft's save_settings,
            Graph's save_user_config) already makes; this bridge must not be
            a weaker path to the same files.
    """
    from secure_io import is_restricted

    path.parent.mkdir(parents=True, exist_ok=True)
    merged = _read_json(path)
    merged.update(data)
    write_private_json(path, merged)
    if not is_restricted(path):
        write_private_json(path, merged)
        if not is_restricted(path):
            raise PermissionError(f"Could not restrict permissions on {path}")


def write_model_choice(slug: str, role: str, model_name: str) -> None:
    """Persist a user's model choice for *role* into *slug*'s config.

    Raises:
        ValueError: if *slug* has no config bridge mapping, or the role is
            unknown for this app.
        OSError: if the config file cannot be written.
    """
    key = (slug, role)
    if key not in _ROLE_KEY_MAP:
        raise ValueError(f"No config bridge mapping for app={slug!r} role={role!r}")

    path_factory, config_key = _ROLE_KEY_MAP[key]
    path: Path = path_factory()

    # Draft uses secure_io for write — delegate to its own save mechanism
    # if available, to preserve restricted-file semantics.
    if slug == "artifice-draft":
        try:
            from artifice_draft.web.runtime import save_settings as _draft_save
        except ImportError:
            # Draft is not importable (e.g. Hub running standalone);
            # fall back to plain JSON write.
            _write_json(path, {config_key: model_name})
            return
        _draft_save({config_key: model_name})
        return

    # Graph uses a nested config structure.
    # config_key is "llm.model" or "embedding.model".
    if slug == "artifice-graph":
        _write_graph_config(path, config_key, model_name)
        return

    # OCR and any future flat-key apps.
    _write_json(path, {config_key: model_name})


def _write_graph_config(path: Path, key_path: str, model_name: str) -> None:
    """Write a nested key (e.g. ``llm.model``) into graph's config.json.

    Graph's config is a PipelineConfig serialisation with top-level sections
    (``llm``, ``embedding``, etc.).  We only touch the field we were asked to
    change — everything else is preserved as-is.

    Raises:
        ValueError: if key_path isn't a dotted ``"section.field"`` string, or if
            an existing section in the file isn't a JSON object (e.g. a
            hand-edited or externally-corrupted config.json where ``"llm"`` is a
            string or null instead of an object) — writing into it would
            raise a confusing TypeError instead.
        PermissionError: if the file cannot be verified as restricted-access
            after one retry — see _write_json's docstring for why this
            matters.
    """
    from secure_io import is_restricted

    current = _read_json(path)
    parts = key_path.split(".", 1)
    if len(parts) != 2:
        raise ValueError(f"Graph config keys must be dotted: {key_path!r}")
    section, field = parts
    if section not in current:
        current[section] = {}
    elif not isinstance(current[section], dict):
        raise ValueError(
            f"Graph config section {section!r} is not an object "
            f"(got {type(current[section]).__name__}) — cannot write {field!r} into it"
        )
    current[section][field] = model_name
    path.parent.mkdir(parents=True, exist_ok=True)
    write_private_json(path, current)
    if not is_restricted(path):
        write_private_json(path, current)
        if not is_restricted(path):
            raise PermissionError(f"Could not restrict permissions on {path}")

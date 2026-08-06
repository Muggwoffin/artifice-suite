# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Helper utilities for web server configuration management."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from platformdirs import user_data_dir

from artifice_graph.config import (
    EmbeddingConfig,
    EntityResolutionConfig,
    ExportConfig,
    ExtractionConfig,
    IngestionConfig,
    LLMConfig,
    PipelineConfig,
    StorageConfig,
    UserPreferences,
    load_config,
)

# User data is stored under platformdirs (migrated from legacy
# ~/.callosip by artifice_graph.config on first import).
_USER_DATA_DIR = Path(user_data_dir("artifice-graph", "ArtificeSuite"))
PREFERENCES_FILE = _USER_DATA_DIR / "preferences.json"
CONFIG_FILE = _USER_DATA_DIR / "config.json"


def ensure_preferences_dir() -> None:
    """Ensure preferences directory exists."""
    _USER_DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_user_preferences() -> UserPreferences:
    """Load user preferences from file or return defaults."""
    ensure_preferences_dir()

    if PREFERENCES_FILE.exists():
        try:
            with open(PREFERENCES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return UserPreferences(**data)
        except Exception:
            pass

    return UserPreferences()


def save_user_preferences(preferences: UserPreferences) -> None:
    """Save user preferences to file."""
    ensure_preferences_dir()

    with open(PREFERENCES_FILE, "w", encoding="utf-8") as f:
        json.dump(preferences.model_dump(), f, indent=2)


def load_saved_config() -> PipelineConfig | None:
    """Load user-saved configuration from file."""
    ensure_preferences_dir()

    if CONFIG_FILE.exists():
        try:
            from secure_io import ensure_restricted

            ensure_restricted(CONFIG_FILE)
        except Exception:
            import logging

            logging.warning(
                "Could not restrict permissions on %s — continuing anyway",
                CONFIG_FILE,
            )
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            config = PipelineConfig(
                llm=LLMConfig(**data.get("llm", {})),
                embedding=EmbeddingConfig(**data.get("embedding", {})),
                ingestion=IngestionConfig(**data.get("ingestion", {})),
                extraction=ExtractionConfig(**data.get("extraction", {})),
                entity_resolution=EntityResolutionConfig(**data.get("entity_resolution", {})),
                export=ExportConfig(**data.get("export", {})),
                storage=StorageConfig(**data.get("storage", {})),
                nominatim_lookup_enabled=data.get("nominatim_lookup_enabled", False),
            )

            return config
        except Exception:
            pass

    return None


def save_user_config(config: PipelineConfig) -> None:
    """Save user configuration to file (all sections, with restricted permissions).

    If *config.llm.api_key* is the redacted placeholder the existing on-disk
    key is preserved instead — a client that GETs preferences, receives
    ``"api_key": "************"``, and POSTs the same body back must not
    overwrite the real key with the placeholder.
    """
    from secure_io import is_restricted, write_private_json

    ensure_preferences_dir()

    PLACEHOLDER = "*" * 12
    if config.llm.api_key == PLACEHOLDER:
        existing = load_saved_config()
        if existing and existing.llm.api_key and existing.llm.api_key != PLACEHOLDER:
            config.llm.api_key = existing.llm.api_key

    data = {
        "llm": config.llm.model_dump(),
        "embedding": config.embedding.model_dump(),
        "ingestion": config.ingestion.model_dump(),
        "extraction": config.extraction.model_dump(),
        "entity_resolution": config.entity_resolution.model_dump(),
        "export": config.export.model_dump(),
        "storage": config.storage.model_dump(),
        "nominatim_lookup_enabled": config.nominatim_lookup_enabled,
    }

    write_private_json(CONFIG_FILE, data)

    # Align write-time verification with the public is_restricted() contract
    # that the test suite asserts — a platform-specific false-negative
    # (e.g. Administrator accounts retaining SYSTEM ACEs on Windows CI
    # runners) must not block a successful, secure write.
    if not is_restricted(CONFIG_FILE):
        # One retry handles occasional ACL propagation delay on Windows.
        write_private_json(CONFIG_FILE, data)
        if not is_restricted(CONFIG_FILE):
            raise PermissionError(f"Failed to secure config file after retry: {CONFIG_FILE}")


def apply_preferences_to_config(
    config: PipelineConfig, preferences: UserPreferences
) -> PipelineConfig:
    """Apply user preferences to config."""
    config.theme = preferences.theme
    config.reduce_motion = preferences.reduce_motion

    return config

"""Helper utilities for web server configuration management."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from graph_pipeline.config import (
    ExtractionConfig,
    EmbeddingConfig,
    IngestionConfig,
    EntityResolutionConfig,
    ExportConfig,
    StorageConfig,
    LLMConfig,
    PipelineConfig,
    UserPreferences,
    load_config,
)

PREFERENCES_FILE = Path.home() / ".callosip" / "preferences.json"
CONFIG_FILE = Path.home() / ".callosip" / "config.json"


def ensure_preferences_dir() -> None:
    """Ensure preferences directory exists."""
    preferences_dir = Path.home() / ".callosip"
    preferences_dir.mkdir(exist_ok=True)


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
            )

            return config
        except Exception:
            pass

    return None


def save_user_config(config: PipelineConfig) -> None:
    """Save user configuration to file."""
    ensure_preferences_dir()

    data = {
        "llm": config.llm.model_dump(),
        "embedding": config.embedding.model_dump(),
        "ingestion": config.ingestion.model_dump(),
        "extraction": config.extraction.model_dump(),
        "entity_resolution": config.entity_resolution.model_dump(),
        "export": config.export.model_dump(),
        "storage": config.storage.model_dump(),
    }

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def apply_preferences_to_config(config: PipelineConfig, preferences: UserPreferences) -> PipelineConfig:
    """Apply user preferences to config."""
    config.theme = preferences.theme
    config.reduce_motion = preferences.reduce_motion

    return config

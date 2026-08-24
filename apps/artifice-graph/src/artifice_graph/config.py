# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import importlib.resources
import json
import logging
import os
from pathlib import Path

import yaml
from platformdirs import user_data_dir
from pydantic import BaseModel, Field
from secure_io.migration import migrate_legacy_directory

logger = logging.getLogger(__name__)


class LLMConfig(BaseModel):
    base_url: str = "http://localhost:11434/v1"
    api_key: str = ""
    # Empty means "the user has not chosen a model", NOT "use this one".
    # This previously named gemma2:27b and nothing checked it against what the
    # endpoint actually serves, so the first extraction failed with a raw
    # provider error. artifice_graph._resolution fills it in once per run.
    model: str = ""
    temperature: float = 0.1
    timeout: int = 120
    supports_vision: bool = False
    connection_status: str = "disconnected"


class EmbeddingConfig(BaseModel):
    base_url: str = "http://localhost:11434"
    # Empty for the same reason as LLMConfig.model above — resolved per run
    # against the models the endpoint reports.
    model: str = ""
    timeout: int = 60
    batch_size: int = 16
    supports_vision: bool = False


class UserPreferences(BaseModel):
    theme: str = "auto"
    reduce_motion: bool = False
    last_model_base_url: str = ""
    last_selected_model: str = ""


class IngestionConfig(BaseModel):
    chunk_size: int = 2000
    chunk_overlap: int = 200
    input_dir: str = "data/input_ocr"
    supported_extensions: list[str] = Field(default_factory=lambda: [".txt", ".md"])
    max_file_size_mb: int = 50


class ExtractionConfig(BaseModel):
    max_retries: int = 3
    retry_delay: float = 1.0
    batch_size: int = 5
    cache_dir: str = "data/cache/llm_responses"


class EntityResolutionConfig(BaseModel):
    similarity_threshold: float = 0.93
    fuzzy_match: bool = True
    use_semantic: bool = True
    semantic_threshold: float = 0.85
    embedding_model: str = "bge-m3"
    aliases_file: str = "data/aliases.yaml"


class ExportConfig(BaseModel):
    output_dir: str = "data/output"
    graph_formats: list[str] = Field(default_factory=lambda: ["graphml", "gexf", "json", "csv"])
    graph_format: str = "graphml"
    obsidian_vault_dir: str = "data/obsidian_vault"


class StorageConfig(BaseModel):
    entities_file: str = "data/output/entities.json"
    relationships_file: str = "data/output/relationships.json"
    documents_file: str = "data/output/documents.json"
    chunks_file: str = "data/output/chunks.json"


class PipelineConfig(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    ingestion: IngestionConfig = Field(default_factory=IngestionConfig)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    entity_resolution: EntityResolutionConfig = Field(default_factory=EntityResolutionConfig)
    export: ExportConfig = Field(default_factory=ExportConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)

    # Privacy guard: entity names extracted from a user's documents —
    # potentially unpublished research material — must never be sent to a
    # third party without explicit consent.  Even with consent this is a
    # separate opt-in from the LLM allowlist; an academic who permits a
    # local Ollama instance is not consenting to transmit entity names to
    # the OpenStreetMap Foundation.
    nominatim_lookup_enabled: bool = False


def load_config(config_path: str | Path | None = None) -> PipelineConfig:
    """Load pipeline configuration.

    Precedence (lowest to highest):
      1. Pydantic defaults
      2. config.yaml (project checked-in defaults)
      3. User config.json (preferences saved via web UI — stored under
         platformdirs, migrated from legacy ~/.callosip on first access)
      4. CLI arguments (applied by callers AFTER this function returns)

    Relative paths declared in config.yaml are resolved against the app
    root — deliberately NOT wherever config.yaml itself was found.  config.yaml
    now ships inside the installed package (importlib.resources, freeze-safe),
    but app_root governs where relative *data* paths resolve (entities.json,
    caches, output graphs). Conflating the two would silently relocate a
    user's existing pipeline data into wherever the package happens to be
    installed — site-packages for a wheel, ``_internal/`` for a frozen build —
    every time this function runs with no explicit path, which is every
    call site outside ``cli.py``. ``cli.py``'s ``_APP_ROOT`` is computed the
    same way, independently, for the same reason. Callers that further
    mutate the config should call ``resolve_config_paths()`` afterward if
    they set relative path strings.
    """
    if config_path is None:
        config_path = Path(str(importlib.resources.files("artifice_graph") / "config.yaml"))
        app_root = Path(__file__).resolve().parent.parent.parent
    else:
        config_path = Path(config_path)
        config_file = config_path if config_path.is_file() else None
        app_root = (config_file.parent if config_file else Path.cwd()).resolve()

    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        config = PipelineConfig.model_validate(raw)
    else:
        config = PipelineConfig()

    # Resolve relative paths against the app root BEFORE overlaying user config.
    # User config values that are absolute deliberately override the resolved
    # path; relative user config values are also resolved.
    resolve_config_paths(config, app_root)

    # Layer 3: merge user-saved configuration on top of config.yaml
    _merge_user_config(config)

    # User config may have introduced new relative paths - resolve again.
    resolve_config_paths(config, app_root)

    # Layer 4: environment variable overrides (highest automatic precedence).
    # CLI arguments (applied by callers after this function returns) can still
    # override these.
    _apply_env_overrides(config)

    return config


# -- path resolution ---------------------------------------------------------


def resolve_config_paths(config: PipelineConfig, app_root: Path) -> None:
    """Resolve every relative-path config field against *app_root* in-place.

    Absolute paths are left unchanged.  Missing / empty fields are skipped.
    """
    _path_sections: dict[str, list[str]] = {
        "ingestion": ["input_dir"],
        "extraction": ["cache_dir"],
        "entity_resolution": ["aliases_file"],
        "export": ["output_dir", "obsidian_vault_dir"],
        "storage": ["entities_file", "relationships_file", "documents_file", "chunks_file"],
    }
    for section_name, field_names in _path_sections.items():
        section_model = getattr(config, section_name, None)
        if section_model is None:
            continue
        for field_name in field_names:
            raw = getattr(section_model, field_name, None)
            if not raw:
                continue
            path = Path(raw)
            if not path.is_absolute():
                setattr(section_model, field_name, str((app_root / path).resolve()))


# -- user config merge -------------------------------------------------------


_LEGACY_CONFIG_DIR = Path.home() / ".callosip"


def _resolve_user_data_dir() -> Path:
    """Return the per-user data directory, migrating from legacy
    ``~/.callosip`` on first access.

    Migration moves the entire legacy directory to the platformdirs
    location, then re-applies access restrictions on the migrated config
    file so that a moved secret does not silently become world-readable.

    If migration fails the legacy directory is used as a fallback — a
    failed migration must never crash the app.
    """
    new_dir = Path(user_data_dir("artifice-graph", "ArtificeSuite"))
    return migrate_legacy_directory(
        _LEGACY_CONFIG_DIR,
        new_dir,
        user_overrode_default=False,
        move_mode="whole_dir",
        collision_is_silent=True,
        refuse_symlink=True,
        restrict_filename="config.json",
        logger=logger,
    )


_USER_DATA_DIR: Path | None = None  # Lazy — resolved via _get_user_data_dir()


def _get_user_data_dir() -> Path:
    """Return the per-user data directory, resolving on first call.

    This is deliberately NOT resolved at import time — the migration
    from ``~/.callosip`` involves ``shutil.move()``, which must never
    run as a module-import side effect.  Resolving on first actual use
    keeps the migration explicit, testable, and safe.
    """
    global _USER_DATA_DIR
    if _USER_DATA_DIR is None:
        _USER_DATA_DIR = _resolve_user_data_dir()
    return _USER_DATA_DIR


def _get_user_config_path() -> Path:
    """Return the per-user ``config.json`` path."""
    return _get_user_data_dir() / "config.json"


def _merge_user_config(config: PipelineConfig) -> None:
    """Overlay ``config.json`` (platformdirs, migrated from legacy
    ``~/.callosip``) onto *config* in-place.

    Only keys that exist on the Pydantic config model are considered;
    unknown keys in the user file are silently ignored.
    """
    user_cfg = _get_user_config_path()
    if not user_cfg.exists():
        return

    try:
        with open(user_cfg, encoding="utf-8") as f:
            user_data = json.load(f)
    except Exception:
        logger.debug("Failed to read user config at %s", user_cfg)
        return

    if not isinstance(user_data, dict):
        return

    _section_names = (
        "llm",
        "embedding",
        "ingestion",
        "extraction",
        "entity_resolution",
        "export",
        "storage",
    )
    applied = False
    for section in _section_names:
        section_data = user_data.get(section)
        if not isinstance(section_data, dict):
            continue
        section_model = getattr(config, section, None)
        if section_model is None:
            continue
        for key, value in section_data.items():
            if hasattr(section_model, key) and value is not None:
                setattr(section_model, key, value)
                applied = True

    if applied:
        logger.debug("Applied user config from %s", user_cfg)

    # Top-level fields not inside a section.
    if "nominatim_lookup_enabled" in user_data and isinstance(
        user_data["nominatim_lookup_enabled"], bool
    ):
        config.nominatim_lookup_enabled = user_data["nominatim_lookup_enabled"]


# -- environment variable overrides -------------------------------------------


def _apply_env_overrides(config: PipelineConfig) -> None:
    """Apply environment variable overrides on top of merged config.

    Precedence: env > user config > config.yaml > pydantic defaults.
    Only URL-type fields that affect model-server connectivity are
    overridden; enumerations of every config field would duplicate
    the file and user-config layers for no benefit.
    """
    _overrides: list[tuple[object, str, str]] = [
        (config.llm, "base_url", "LLM_BASE_URL"),
        (config.embedding, "base_url", "EMBEDDING_BASE_URL"),
    ]
    for section_model, attr, env_var in _overrides:
        val = os.environ.get(env_var)
        if val is not None and val.strip():
            setattr(section_model, attr, val.strip())
            logger.debug("Set %s from %s env var", attr, env_var)

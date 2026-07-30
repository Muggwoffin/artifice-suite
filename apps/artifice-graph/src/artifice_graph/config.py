# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class LLMConfig(BaseModel):
    base_url: str = "http://localhost:11434/v1"
    api_key: str = ""
    model: str = "gemma2:27b"
    temperature: float = 0.1
    timeout: int = 120
    supports_vision: bool = False
    connection_status: str = "disconnected"


class EmbeddingConfig(BaseModel):
    base_url: str = "http://localhost:11434"
    model: str = "bge-m3"
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


def load_config(config_path: str | Path | None = None) -> PipelineConfig:
    """Load pipeline configuration.

    Precedence (lowest to highest):
      1. Pydantic defaults
      2. config.yaml (project checked-in defaults)
      3. ~/.callosip/config.json (user preferences saved via web UI)
      4. CLI arguments (applied by callers AFTER this function returns)

    Relative paths declared in config.yaml are resolved against the
    directory containing that config file (the app root).  Callers that
    further mutate the config should call ``resolve_config_paths()``
    afterward if they set relative path strings.
    """
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "config.yaml"
    else:
        config_path = Path(config_path)

    config_file = config_path if config_path.is_file() else None
    app_root = (config_file.parent if config_file else Path(__file__).parent.parent.parent).resolve()

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
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


_USER_CONFIG_PATH = Path.home() / ".callosip" / "config.json"


def _merge_user_config(config: PipelineConfig) -> None:
    """Overlay ~/.callosip/config.json onto *config* in-place.

    Only keys that exist on the Pydantic config model are considered;
    unknown keys in the user file are silently ignored.
    """
    if not _USER_CONFIG_PATH.exists():
        return

    try:
        with open(_USER_CONFIG_PATH, "r", encoding="utf-8") as f:
            user_data = json.load(f)
    except Exception:
        logger.debug("Failed to read user config at %s", _USER_CONFIG_PATH)
        return

    if not isinstance(user_data, dict):
        return

    _section_names = (
        "llm", "embedding", "ingestion", "extraction",
        "entity_resolution", "export", "storage",
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
        logger.debug("Applied user config from %s", _USER_CONFIG_PATH)

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


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
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "config.yaml"
    else:
        config_path = Path(config_path)

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        return PipelineConfig.model_validate(raw)

    return PipelineConfig()

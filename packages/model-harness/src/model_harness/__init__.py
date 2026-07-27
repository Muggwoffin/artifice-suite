"""Shared BYOM connector contract for the Artifice Suite.

Provider-specific transport lives in each app today (e.g.
``ocr_pipeline._llm``, ``graph_pipeline.extraction.llm_client``); this module
defines the common configuration and schema-validated call shape they are
meant to converge on.
"""

from __future__ import annotations

from typing import Literal, TypeVar

from pydantic import BaseModel

Provider = Literal["ollama", "lm-studio", "generic-api", "whisper", "parakeet"]

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class ModelConnectorConfig(BaseModel):
    """Endpoint and credentials for a single BYOM connection."""

    provider: Provider
    endpoint: str
    model: str
    api_key: str | None = None


__all__ = ["ModelConnectorConfig", "Provider", "SchemaT"]

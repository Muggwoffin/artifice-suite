from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class Relationship(BaseModel):
    """A directed relationship between two entities."""

    id: str = ""
    source_entity: str
    target_entity: str
    relationship_type: str
    time_frame: str = ""
    evidence_quote: str = ""
    confidence_score: float = Field(default=0.8, ge=0.0, le=1.0)
    source_doc_id: str = ""

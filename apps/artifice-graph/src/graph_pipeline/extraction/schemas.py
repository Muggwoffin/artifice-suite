from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from graph_pipeline.models.entity import EntityType


class ExtractedEntity(BaseModel):
    name: str
    entity_type: EntityType
    aliases: list[str] = Field(default_factory=list)
    summary: str = ""


class ExtractedRelationship(BaseModel):
    source_entity: str
    target_entity: str
    relationship_type: str
    time_frame: str = ""
    evidence_quote: str = ""
    confidence_score: float = Field(default=0.8, ge=0.0, le=1.0)


class ExtractionResult(BaseModel):
    """Schema for a single LLM extraction response."""

    entities: list[ExtractedEntity] = Field(default_factory=list)
    relationships: list[ExtractedRelationship] = Field(default_factory=list)
    raw_response: str = ""


EXTRACTION_SYSTEM_PROMPT = """\
You are a historical-document entity extraction assistant.
Given a text chunk, extract ALL notable historical entities and the relationships between them.

Return a JSON object with exactly two keys:
  "entities": a list of objects, each with:
    - "name" (string): the canonical name of the entity as it appears in the text
    - "entity_type" (string): one of "Person", "Organization", "Location", "Event", "Concept"
    - "aliases" (list of strings): alternative names, pseudonyms, or spelling variants
    - "summary" (string): a one-sentence description of the entity based on context

  "relationships": a list of objects, each with:
    - "source_entity" (string): name of the source entity
    - "target_entity" (string): name of the target entity
    - "relationship_type" (string): short label for the relationship (e.g. "founded_by", "led", "located_in", "allied_with")
    - "time_frame" (string): dates or period if mentioned, else ""
    - "evidence_quote" (string): the exact quote from the text that supports this relationship
    - "confidence_score" (float 0-1): your confidence in the extraction

Rules:
- Extract entities ONLY if they are clearly historical figures, groups, places, events, or ideas.
- Do NOT extract common nouns or generic references.
- Use the exact spelling from the text for the entity name.
- Return ONLY valid JSON — no markdown fences, no commentary.
"""

EXTRACTION_USER_TEMPLATE = """\
Text chunk (source: {source_id}):
---
{text}
---

Extract entities and relationships as JSON:"""

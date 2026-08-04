# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from pydantic import BaseModel, Field

from artifice_graph.models.entity import Entity, EntityType
from artifice_graph.models.relationship import Relationship


class ExtractedEntity(BaseModel):
    """Lightweight extraction schema for validating raw LLM output.

    Declares exactly the fields a model is expected to produce in its JSON
    response.  Used as the item type inside :class:`_LLMExtractionShape` —
    the schema passed to :func:`model_harness.driver.run_structured`.
    """

    name: str
    entity_type: EntityType
    aliases: list[str] = Field(default_factory=list)
    summary: str = ""


class ExtractedRelationship(BaseModel):
    """Lightweight extraction schema for validating raw LLM output.

    Same role as :class:`ExtractedEntity` — declares the fields the model
    produces, independent of the domain types that carry extra pipeline
    fields (``id``, ``source_doc_id``, etc.).
    """

    source_entity: str
    target_entity: str
    relationship_type: str
    time_frame: str = ""
    evidence_quote: str = ""
    confidence_score: float = Field(default=0.8, ge=0.0, le=1.0)


class _LLMExtractionShape(BaseModel):
    """Schema for the harness structured-extraction call.

    This is the JSON Schema passed to :func:`~model_harness.driver.run_structured`
    and injected into the prompt.  It uses :class:`ExtractedEntity` and
    :class:`ExtractedRelationship` — the exact fields the model is asked to
    return — rather than the domain types, which carry extra pipeline fields
    (auto-generated ids, embedding vectors, source-doc references) that would
    confuse the model if included in the prompt.
    """

    entities: list[ExtractedEntity] = Field(default_factory=list)
    relationships: list[ExtractedRelationship] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    """Pipeline result from a single extraction call.

    Carries domain Entity / Relationship objects (not the lightweight
    extraction schemas).  ``raw_response`` is the unedited model text,
    retained for audit.
    """

    entities: list[Entity] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    raw_response: str = ""


EXTRACTION_SYSTEM_PROMPT = """\
You are a historical-document entity extraction assistant.
Given a text chunk, extract ALL notable historical entities and the relationships between them.

Rules:
- Extract entities ONLY if they are clearly historical figures, groups, places, events, or ideas.
- Do NOT extract common nouns or generic references.
- Use the exact spelling from the text for the entity name.
- You must respond with a single JSON object matching the schema provided.
"""

EXTRACTION_USER_TEMPLATE = """\
Text chunk (source: {source_id}):
---
{text}
---

Extract entities and relationships as JSON:"""

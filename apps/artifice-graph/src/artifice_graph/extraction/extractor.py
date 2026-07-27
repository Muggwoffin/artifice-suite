from __future__ import annotations

import json
import logging
import re
import time
import asyncio
from typing import AsyncGenerator

from artifice_graph.config import ExtractionConfig, load_config, LLMConfig
from artifice_graph.extraction.llm_client import LLMClient
from artifice_graph.extraction.schemas import (
    EXTRACTION_SYSTEM_PROMPT,
    EXTRACTION_USER_TEMPLATE,
    ExtractionResult,
)
from artifice_graph.extraction.cache import LLMResponseCache
from artifice_graph.models.document import TextChunk
from artifice_graph.models.entity import Entity, EntityType
from artifice_graph.models.relationship import Relationship

logger = logging.getLogger(__name__)


class EntityExtractor:
    """Extract entities and relationships from text chunks via a local LLM."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        config: ExtractionConfig | None = None,
    ) -> None:
        if config is None:
            config = load_config().extraction
        self.config = config
        self.llm = llm_client or LLMClient()
        self._cache = LLMResponseCache(config)

    def _parse_json_response(self, raw: str) -> dict:
        cleaned = raw.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}") + 1
            if start != -1 and end > start:
                return json.loads(cleaned[start:end])
            raise

    def _validate_or_retry(self, raw: str) -> dict:
        last_exc: Exception | None = None
        delay = self.config.retry_delay

        for attempt in range(1, self.config.max_retries + 1):
            try:
                data = self._parse_json_response(raw)
                ExtractionResult(
                    entities=data.get("entities", []),
                    relationships=data.get("relationships", []),
                )
                return data
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Extraction attempt %d/%d failed: %s",
                    attempt,
                    self.config.max_retries,
                    exc,
                )
                if attempt < self.config.max_retries:
                    time.sleep(delay)
                    delay *= 2

        raise ValueError(
            f"Failed to get valid JSON after {self.config.max_retries} attempts: {last_exc}"
        )

    async def extract_from_chunk(self, chunk: TextChunk) -> ExtractionResult:
        user_msg = EXTRACTION_USER_TEMPLATE.format(
            source_id=chunk.document_id, text=chunk.text
        )
        model = self.llm.config.model

        cached = self._cache.get(model, user_msg)
        if cached is not None:
            data = self._validate_or_retry(cached)
            raw = cached
        else:
            raw = await self.llm.chat(EXTRACTION_SYSTEM_PROMPT, user_msg)
            data = self._validate_or_retry(raw)
            self._cache.set(model, user_msg, raw)

        entities: list[Entity] = []
        seen_names: set[str] = set()
        for e in data.get("entities", []):
            name = e.get("name", "").strip()
            if not name or name.lower() in seen_names:
                continue
            seen_names.add(name.lower())
            entities.append(
                Entity(
                    name=name,
                    entity_type=EntityType(e.get("entity_type", "Concept")),
                    aliases=e.get("aliases", []),
                    summary=e.get("summary", ""),
                    source_doc_ids=[chunk.document_id],
                )
            )

        relationships: list[Relationship] = []
        for r in data.get("relationships", []):
            relationships.append(
                Relationship(
                    source_entity=r.get("source_entity", ""),
                    target_entity=r.get("target_entity", ""),
                    relationship_type=r.get("relationship_type", "related_to"),
                    time_frame=r.get("time_frame", ""),
                    evidence_quote=r.get("evidence_quote", ""),
                    confidence_score=float(r.get("confidence_score", 0.8)),
                    source_doc_id=chunk.document_id,
                )
            )

        return ExtractionResult(
            entities=entities,
            relationships=relationships,
            raw_response=raw,
        )

    async def extract_from_chunk_stream(
        self,
        chunk: TextChunk,
    ) -> AsyncGenerator[str, None]:
        """
        Extract from a chunk with streaming support.
        Yields:
            Complete text chunks or partial responses as they arrive
        """
        user_msg = EXTRACTION_USER_TEMPLATE.format(
            source_id=chunk.document_id, text=chunk.text
        )
        model = self.llm.config.model

        cached = self._cache.get(model, user_msg)
        if cached is not None:
            data = self._validate_or_retry(cached)
            raw = cached

            entities: list[Entity] = []
            seen_names: set[str] = set()
            for e in data.get("entities", []):
                name = e.get("name", "").strip()
                if not name or name.lower() in seen_names:
                    continue
                seen_names.add(name.lower())
                entities.append(
                    Entity(
                        name=name,
                        entity_type=EntityType(e.get("entity_type", "Concept")),
                        aliases=e.get("aliases", []),
                        summary=e.get("summary", ""),
                        source_doc_ids=[chunk.document_id],
                    )
                )

            relationships: list[Relationship] = []
            for r in data.get("relationships", []):
                relationships.append(
                    Relationship(
                        source_entity=r.get("source_entity", ""),
                        target_entity=r.get("target_entity", ""),
                        relationship_type=r.get("relationship_type", "related_to"),
                        time_frame=r.get("time_frame", ""),
                        evidence_quote=r.get("evidence_quote", ""),
                        confidence_score=float(r.get("confidence_score", 0.8)),
                        source_doc_id=chunk.document_id,
                    )
                )

            yield json.dumps(ExtractionResult(
                entities=entities,
                relationships=relationships,
                raw_response=raw,
            ).model_dump(exclude_none=True))
            return

        try:
            async for chunk_text in self.llm.chat_stream(EXTRACTION_SYSTEM_PROMPT, user_msg):
                yield chunk_text
                if "[DONE]" in chunk_text:
                    break

            raw = await self.llm.chat(EXTRACTION_SYSTEM_PROMPT, user_msg)
            data = self._validate_or_retry(raw)
            self._cache.set(model, user_msg, raw)

            entities: list[Entity] = []
            seen_names: set[str] = set()
            for e in data.get("entities", []):
                name = e.get("name", "").strip()
                if not name or name.lower() in seen_names:
                    continue
                seen_names.add(name.lower())
                entities.append(
                    Entity(
                        name=name,
                        entity_type=EntityType(e.get("entity_type", "Concept")),
                        aliases=e.get("aliases", []),
                        summary=e.get("summary", ""),
                        source_doc_ids=[chunk.document_id],
                    )
                )

            relationships: list[Relationship] = []
            for r in data.get("relationships", []):
                relationships.append(
                    Relationship(
                        source_entity=r.get("source_entity", ""),
                        target_entity=r.get("target_entity", ""),
                        relationship_type=r.get("relationship_type", "related_to"),
                        time_frame=r.get("time_frame", ""),
                        evidence_quote=r.get("evidence_quote", ""),
                        confidence_score=float(r.get("confidence_score", 0.8)),
                        source_doc_id=chunk.document_id,
                    )
                )

            yield json.dumps(ExtractionResult(
                entities=entities,
                relationships=relationships,
                raw_response=raw,
            ).model_dump(exclude_none=True))

        except Exception as exc:
            logger.error("Failed to extract from chunk %s: %s", chunk.id, exc)
            raise

    def extract_batch(self, chunks: list[TextChunk]) -> list[ExtractionResult]:
        results: list[ExtractionResult] = []
        failures = 0
        for i, chunk in enumerate(chunks):
            logger.info("Extracting chunk %d/%d (doc: %s)", i + 1, len(chunks), chunk.document_id)
            try:
                result = asyncio.run(self.extract_from_chunk(chunk))
                results.append(result)
            except Exception as exc:
                failures += 1
                logger.error("Skipping chunk %s: %s", chunk.id, exc)
        logger.info("Cache: %s", self._cache.stats)
        if chunks and not results:
            raise RuntimeError(
                f"All {len(chunks)} chunks failed extraction. "
                f"Check LLM connectivity and model availability."
            )
        if failures:
            logger.warning(
                "%d/%d chunks failed extraction; results may be incomplete.",
                failures,
                len(chunks),
            )
        return results

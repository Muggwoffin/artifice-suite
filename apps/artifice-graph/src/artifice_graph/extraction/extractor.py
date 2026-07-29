from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator

from artifice_graph.config import ExtractionConfig, load_config
from artifice_graph.extraction.llm_client import LLMClient
from artifice_graph.extraction.schemas import (
    _LLMExtractionShape,
    EXTRACTION_SYSTEM_PROMPT,
    EXTRACTION_USER_TEMPLATE,
    ExtractionResult,
)
from artifice_graph.extraction.cache import LLMResponseCache
from artifice_graph.models.document import TextChunk
from artifice_graph.models.entity import Entity, EntityType
from artifice_graph.models.relationship import Relationship

from model_harness.contract import (
    EndpointPolicy,
    ModelConnectorConfig,
    ModelProvider,
    StructuredOutputMode,
    StructuredRequest,
)
from model_harness.driver import run_structured
from model_harness.endpoint_policy import EndpointPolicy as ConcreteEndpointPolicy
from model_harness.openai_adapter import OpenAIProvider

logger = logging.getLogger(__name__)


class EntityExtractor:
    """Extract entities and relationships from text chunks via a local LLM.

    Parameters
    ----------
    llm_client:
        Legacy LLM client (for diagnostics only — extraction goes through
        the harness).
    config:
        Extraction configuration (retry policy, batch size, cache dir).
    provider:
        A :class:`~model_harness.contract.ModelProvider`.  If ``None``, an
        :class:`~model_harness.openai_adapter.OpenAIProvider` is constructed
        from *llm_client*'s config.
    endpoint_policy:
        Endpoint validation policy.  If ``None``, the default
        :class:`~model_harness.endpoint_policy.EndpointPolicy` is used.
    """

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        config: ExtractionConfig | None = None,
        *,
        provider: ModelProvider | None = None,
        endpoint_policy: EndpointPolicy | None = None,
    ) -> None:
        if config is None:
            config = load_config().extraction
        self.config = config
        self.llm = llm_client or LLMClient()
        self._cache = LLMResponseCache(config)

        # -- Harness infrastructure -------------------------------------------
        if provider is not None:
            self._provider = provider
        else:
            self._provider = OpenAIProvider(
                provider_type="ollama",
                endpoint_policy=endpoint_policy or ConcreteEndpointPolicy(),
                http_client=self.llm.inference_engine.client,
            )
        self._endpoint_policy = endpoint_policy or ConcreteEndpointPolicy()
        self._schema_json = _LLMExtractionShape.model_json_schema()

    # -- Extraction -----------------------------------------------------------

    async def extract_from_chunk(self, chunk: TextChunk) -> ExtractionResult:
        """Extract entities and relationships from a single text chunk.

        Routes through :func:`model_harness.driver.run_structured` so the
        response is schema-validated and the caller receives a guaranteed
        result with ``mode_used`` and ``repaired`` logged.
        """
        user_msg = EXTRACTION_USER_TEMPLATE.format(
            source_id=chunk.document_id, text=chunk.text
        )
        model = self.llm.config.model

        # -- Cache hit path ---------------------------------------------------
        cached = self._cache.get(model, user_msg)
        if cached is not None:
            data = _LLMExtractionShape.model_validate_json(cached)
            return _to_extraction_result(data, chunk.document_id, raw="[cached]")

        # -- Build the harness request ----------------------------------------
        model_config = ModelConnectorConfig(
            provider="ollama",
            endpoint=self.llm.config.base_url,
            model=model,
            api_key=self.llm.config.api_key or None,
            timeout_s=float(self.llm.config.timeout),
        )

        request = StructuredRequest(
            instructions=EXTRACTION_SYSTEM_PROMPT,
            input=user_msg,
            schema_json=self._schema_json,
            mode=StructuredOutputMode.PROMPTED,
            config=model_config,
        )

        # -- Run through the harness ------------------------------------------
        result = await run_structured(
            request,
            self._provider,
            _LLMExtractionShape,
            endpoint_policy=self._endpoint_policy,
        )

        logger.info(
            "Extraction chunk=%s mode=%s repaired=%s",
            chunk.id,
            result.mode_used.value,
            result.repaired,
        )

        # -- Cache the validated result ---------------------------------------
        self._cache.set(model, user_msg, result.data.model_dump_json())

        return _to_extraction_result(result.data, chunk.document_id, raw=result.raw)

    async def extract_from_chunk_stream(
        self,
        chunk: TextChunk,
    ) -> AsyncGenerator[str, None]:
        """Streaming extraction — removed in harness port.

        The harness contract (:mod:`model_harness.contract`) deliberately
        excludes streaming from :class:`~model_harness.contract.ModelProvider`,
        and this method had no callers anywhere in the codebase.  Retained as
        a stub that raises :exc:`NotImplementedError` so any downstream code
        that attempts to call it fails loudly rather than silently returning
        nothing.
        """
        raise NotImplementedError(
            "extract_from_chunk_stream was removed when the extraction path "
            "moved onto model_harness.driver.run_structured.  The harness "
            "contract deliberately excludes streaming (see contract.py:254)."
        )

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


# -- Helpers -------------------------------------------------------------------


def _to_extraction_result(
    shape: _LLMExtractionShape,
    document_id: str,
    *,
    raw: str,
) -> ExtractionResult:
    """Convert a validated harness response into the domain result type.

    Maps :class:`ExtractedEntity` / :class:`ExtractedRelationship` (the clean
    schemas the LLM produces) to :class:`Entity` / :class:`Relationship`
    (the domain types with auto-generated ids and source-document references).
    """
    entities: list[Entity] = []
    seen_names: set[str] = set()
    for e in shape.entities:
        name = e.name.strip()
        if not name or name.lower() in seen_names:
            continue
        seen_names.add(name.lower())
        entities.append(
            Entity(
                name=name,
                entity_type=e.entity_type,
                aliases=e.aliases,
                summary=e.summary,
                source_doc_ids=[document_id],
            )
        )

    relationships: list[Relationship] = []
    for r in shape.relationships:
        relationships.append(
            Relationship(
                source_entity=r.source_entity,
                target_entity=r.target_entity,
                relationship_type=r.relationship_type,
                time_frame=r.time_frame,
                evidence_quote=r.evidence_quote,
                confidence_score=r.confidence_score,
                source_doc_id=document_id,
            )
        )

    return ExtractionResult(
        entities=entities,
        relationships=relationships,
        raw_response=raw,
    )

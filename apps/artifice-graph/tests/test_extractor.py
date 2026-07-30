# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

"""Unit tests for EntityExtractor — no LLM required."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from artifice_graph.config import ExtractionConfig
from artifice_graph.models.document import TextChunk


class TestExtractFromChunkStream:
    """extract_from_chunk_stream is a removed stub that raises NotImplementedError.

    The annotation is AsyncGenerator[str, None], and the function contains an
    unreachable ``yield`` so that it really *is* an async generator.  Without
    that ``yield``, a caller writing ``async for`` would get ``TypeError``
    (coroutine object is not an async iterable) instead of
    ``NotImplementedError``.
    """

    @pytest.mark.asyncio
    async def test_async_for_raises_not_implemented(self) -> None:
        """Calling via async-for (as the type hint instructs) raises NotImplementedError."""
        with (
            patch("artifice_graph.extraction.extractor.LLMClient") as mock_llm,
            patch("artifice_graph.extraction.extractor.LLMResponseCache") as mock_cache,
            patch("artifice_graph.extraction.extractor.OpenAIProvider") as mock_provider,
        ):
            from artifice_graph.extraction.extractor import EntityExtractor

            extractor = EntityExtractor(config=ExtractionConfig())
            chunk = TextChunk(
                id="c1",
                document_id="d1",
                chunk_index=0,
                text="test text",
                start_char=0,
                end_char=9,
            )

            with pytest.raises(
                NotImplementedError,
                match="extract_from_chunk_stream",
            ):
                async for _ in extractor.extract_from_chunk_stream(chunk):
                    pass  # pragma: no cover

    def test_is_async_generator_not_coroutine(self) -> None:
        """The function object itself is an async generator, not a coroutine."""
        import inspect

        from artifice_graph.extraction.extractor import EntityExtractor

        with (
            patch("artifice_graph.extraction.extractor.LLMClient") as mock_llm,
            patch("artifice_graph.extraction.extractor.LLMResponseCache") as mock_cache,
            patch("artifice_graph.extraction.extractor.OpenAIProvider") as mock_provider,
        ):
            extractor = EntityExtractor(config=ExtractionConfig())
            chunk = TextChunk(
                id="c2",
                document_id="d2",
                chunk_index=0,
                text="test",
                start_char=0,
                end_char=4,
            )

            result = extractor.extract_from_chunk_stream(chunk)
            assert inspect.isasyncgen(result), (
                f"Expected async generator, got {type(result).__name__}"
            )

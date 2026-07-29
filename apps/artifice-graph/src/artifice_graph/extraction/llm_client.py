from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator

from artifice_graph.config import LLMConfig
from artifice_graph.extraction.inference_engine import InferenceEngine, ModelInfo
from model_harness.endpoint_policy import EndpointPolicy

logger = logging.getLogger(__name__)


class LLMClient:
    """LLM client with OpenAI-compatible interface using InferenceEngine."""

    def __init__(
        self,
        config: LLMConfig | None = None,
        inference_engine: InferenceEngine | None = None,
        endpoint_policy: EndpointPolicy | None = None,
    ) -> None:
        if config is None:
            from artifice_graph.config import load_config
            config = load_config().llm

        self.config = config

        api_key = ""
        if config.base_url.startswith("https://api.openai.com"):
            api_key = config.api_key if hasattr(config, "api_key") else ""

        self.inference_engine = (
            inference_engine
            or InferenceEngine(
                base_url=config.base_url,
                api_key=api_key,
                model=config.model,
                timeout=config.timeout,
                enable_streaming=True,
                endpoint_policy=endpoint_policy,
            )
        )

    async def chat(self, system: str, user: str) -> str:
        """Get a complete response text."""
        return await self.inference_engine.get_response_text(system, user, self.config.model)

    def chat_sync(self, system: str, user: str) -> str:
        """Get a complete response text (synchronous)."""
        return asyncio.run(self.chat(system, user))

    async def chat_stream(self, system: str, user: str) -> AsyncGenerator[str, None]:
        """Chat with streaming support."""
        async for chunk in self.inference_engine.chat_completion(system, user, self.config.model, stream=True):
            yield chunk

    async def get_models(self) -> tuple[list[ModelInfo], list[ModelInfo]]:
        """Get available models (text and vision)."""
        return await self.inference_engine.get_available_models()

    async def check_model_capabilities(self, model_name: str) -> dict:
        """Check if a model supports vision."""
        return await self.inference_engine.check_capabilities(model_name)

    async def test_connection(self) -> dict:
        """Test connection to the model server."""
        return await self.inference_engine.test_connection()

    async def close(self) -> None:
        """Close the inference engine."""
        await self.inference_engine.close()

    def close_sync(self) -> None:
        """Close the inference engine (synchronous)."""
        asyncio.run(self.close())

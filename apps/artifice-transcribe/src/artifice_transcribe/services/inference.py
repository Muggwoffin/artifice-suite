# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any

from model_harness.contract import EndpointRejected
from model_harness.endpoint_policy import EndpointPolicy
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_inference_endpoint_policy = EndpointPolicy()


async def get_available_models(base_url: str, api_key: str | None = None) -> list[str]:
    """Query {base_url}/models and return list of model IDs."""
    _inference_endpoint_policy.validate_url(base_url)
    key = api_key if api_key and api_key.strip() else "not-needed"
    try:
        client = AsyncOpenAI(base_url=base_url, api_key=key)
        response = await client.models.list()
        models = [model.id for model in response.data]
        return sorted(models)
    except Exception as exc:
        logger.error("Failed to fetch models from %s: %s", base_url, exc)
        raise


async def test_connection(base_url: str, api_key: str | None = None) -> dict:
    """Test connectivity to the endpoint and return status with details."""
    _inference_endpoint_policy.validate_url(base_url)
    key = api_key if api_key and api_key.strip() else "not-needed"
    try:
        client = AsyncOpenAI(base_url=base_url, api_key=key)
        models_resp = await client.models.list()
        count = len(models_resp.data)
        return {
            "success": True,
            "message": f"Connected successfully! Found {count} model(s).",
            "model_count": count,
        }
    except Exception as exc:
        err_msg = str(exc)
        if "CORS" in err_msg or "origin" in err_msg.lower() or "Failed to fetch" in err_msg:
            err_msg += (
                " (Hint: If running Ollama, ensure OLLAMA_ORIGINS=* is set in your environment)"
            )
        elif "10061" in err_msg or "Connection refused" in err_msg:
            err_msg += (
                " (Hint: Ensure your local model runner (Ollama, LM Studio, vLLM) is running)"
            )
        return {
            "success": False,
            "message": f"Server unreachable: {err_msg}",
            "model_count": 0,
        }


class InferenceEngine:
    """Unified inference adapter using OpenAI-compatible SDK for BYOM support."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        api_key: str | None = "not-needed",
        model_name: str = "",
        vision_enabled: bool = False,
    ):
        _inference_endpoint_policy.validate_url(base_url)
        self.base_url = base_url
        self.api_key = api_key if api_key and api_key.strip() else "not-needed"
        self.model_name = model_name
        self.vision_enabled = vision_enabled
        self.client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)

    async def generate(
        self,
        prompt: str,
        image_base64: str | None = None,
        stream: bool = False,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> str | AsyncGenerator[str, None]:
        """Generate response (text or streaming) with optional vision support."""
        content: str | list[dict[str, Any]] = prompt

        if image_base64 and self.vision_enabled:
            content = [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_base64}"
                        if not image_base64.startswith("data:")
                        else image_base64
                    },
                },
                {"type": "text", "text": prompt},
            ]

        messages = [{"role": "user", "content": content}]

        if not self.model_name:
            try:
                models = await self.client.models.list()
                if models.data:
                    self.model_name = models.data[0].id
                else:
                    self.model_name = "default"
            except Exception:
                self.model_name = "default"

        if stream:
            return self._stream_response(messages, temperature, max_tokens)
        else:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content or ""

    async def _stream_response(
        self, messages: list[dict[str, Any]], temperature: float, max_tokens: int
    ) -> AsyncGenerator[str, None]:
        stream = await self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

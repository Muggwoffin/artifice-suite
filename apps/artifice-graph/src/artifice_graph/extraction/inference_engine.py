# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unified LLM Inference Engine with OpenAI compatibility."""

from __future__ import annotations

import logging
from typing import AsyncGenerator, Any, Dict, List, Optional

import httpx

from model_harness.discovery import probe_endpoint
from model_harness.endpoint_policy import EndpointPolicy

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Heuristic indicators that a model may support vision (image inputs).
# Used by both server.py and inference_engine.py to tag vision-capable
# models without a dedicated vision API.
# ---------------------------------------------------------------------------
_VISION_INDICATORS = [
    "vision",
    "vl",
    "multi-modal",
    "image",
    "visual",
    "qwen",
    "llava",
    "gpt-4-vision",
    "claude-3",
]


class ModelInfo:
    """Data class to represent model information."""

    def __init__(self, model_info: Dict[str, Any], source: str = "ollama"):
        self.id = model_info.get("id", "")
        self.name = model_info.get("name", self.id)
        self.source = source
        self.supports_vision = model_info.get("supports_vision", False)
        self.supports_chat = model_info.get("supports_chat", True)
        self.supports_images = model_info.get("supports_images", False)
        self.max_tokens = model_info.get("max_tokens", 8192)
        self.description = model_info.get("description", "")
        self.original_data = model_info

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "source": self.source,
            "supports_vision": self.supports_vision,
            "supports_chat": self.supports_chat,
            "supports_images": self.supports_images,
            "max_tokens": self.max_tokens,
            "description": self.description,
        }


class InferenceEngine:
    """OpenAI-compatible inference engine with vision support and fallback parsing."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        api_key: str = "",
        # No default model. This previously said "gemma2:27b", a *second* layer
        # of defaults below the config layer — invisible in every UI and
        # divergent from it. The caller supplies the model; it comes from
        # config, which artifice_graph._resolution has already resolved.
        model: str = "",
        timeout: int = 30,
        enable_streaming: bool = True,
        parser: Optional[Any] = None,
        vision_mode: bool = False,
        endpoint_policy: EndpointPolicy | None = None,
    ):
        self.base_url = base_url.rstrip("/") + "/v1"
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.enable_streaming = enable_streaming
        self.parser = parser
        self.vision_mode = vision_mode

        # Validate the endpoint before any connection is made.  An engine
        # that cannot be constructed with an invalid URL is harder to
        # misuse than one that trusts its callers to validate first.
        policy = endpoint_policy or EndpointPolicy()
        policy.validate_url(self.base_url)

        self.client = httpx.AsyncClient(timeout=timeout)
        self.last_status = "disconnected"

    async def close(self) -> None:
        await self.client.aclose()

    async def health_check(self) -> bool:
        """Check if the server is reachable (delegates to discovery.probe_endpoint)."""
        policy = EndpointPolicy()
        result = await probe_endpoint(self.base_url, policy=policy, timeout_s=5)
        self.last_status = "connected" if result.reachable else "error"
        return result.reachable

    async def get_available_models(self) -> tuple[List[ModelInfo], List[ModelInfo]]:
        """
        Get available models and return both text and vision models.

        Returns:
            tuple: (text_models, vision_models)
        """
        policy = EndpointPolicy()
        result = await probe_endpoint(self.base_url, policy=policy, timeout_s=10)

        text_models: list[ModelInfo] = []
        vision_models: list[ModelInfo] = []

        model_names: set[str] = set()
        for name in result.models:
            if name in model_names:
                continue
            model_names.add(name)

            model_dict: dict[str, Any] = {"id": name, "name": name}
            mi = ModelInfo(model_dict)
            text_models.append(mi)

            if any(indicator in name.lower() for indicator in _VISION_INDICATORS):
                vi_dict: dict[str, Any] = {
                    "id": name,
                    "name": name,
                    "supports_vision": True,
                    "supports_chat": True,
                    "supports_images": True,
                    "max_tokens": 8192,
                    "description": "",
                }
                vision_models.append(ModelInfo(vi_dict))

        return text_models, vision_models

    async def _make_chat_request(
        self, system_prompt: str, user_prompt: str, model: str, stream: bool = False
    ) -> AsyncGenerator[str, None]:
        """
        Make a chat completion request with streaming support.

        Args:
            system_prompt: The system prompt
            user_prompt: The user prompt
            model: The model to use
            stream: Whether to stream the response

        Yields:
            Response chunks as they arrive
        """
        headers = {"Content-Type": "application/json"}

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "stream": stream,
        }

        if not stream:
            payload.pop("stream")

        ollama_base = self.base_url.replace("/v1", "")

        if "11434" in ollama_base and model in model.lower():
            api_path = f"{ollama_base}/api/chat"
            payload.update({"stream": False})
            if "options" not in payload:
                payload["options"] = {}
            payload["options"]["temperature"] = 0.1
        else:
            api_path = f"{self.base_url}/chat/completions"

        try:
            resp = await self.client.post(
                api_path, headers=headers, json=payload, timeout=self.timeout
            )

            if resp.status_code != 200:
                error_text = resp.text
                if "11434" in ollama_base:
                    raise RuntimeError(
                        f"Ollama request failed — server running at {ollama_base}?\n"
                        f"Make sure model '{model}' is available:\n"
                        f"  ollama list\n{error_text}"
                    )
                else:
                    raise RuntimeError(
                        f"OpenAI-compatible request failed at {self.base_url}\n{error_text}"
                    )

            if stream and "stream" in resp.headers.get("content-type", ""):
                buffer = ""
                async for chunk in resp.aiter_text():
                    if chunk:
                        yield chunk
                        if "data: [DONE]" in chunk:
                            break
            else:
                data = resp.json()

                if "11434" in ollama_base:
                    content = data.get("message", {}).get("content", "")
                else:
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

                if content:
                    yield content

        except Exception as e:
            logger.error(f"Chat request error: {e}")
            raise

    async def chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
        stream: bool = False,
    ) -> AsyncGenerator[str, None]:
        """
        Perform a chat completion with streaming support and fallback parsing.

        Args:
            system_prompt: The system prompt
            user_prompt: The user prompt
            model: The model to use (defaults to instance's model)
            options: Additional options for the request
            stream: Whether to stream the response

        Yields:
            Response chunks or complete text
        """
        model_to_use = model or self.model

        async for chunk in self._make_chat_request(
            system_prompt, user_prompt, model_to_use, stream
        ):
            yield chunk

    async def get_response_text(
        self, system_prompt: str, user_prompt: str, model: Optional[str] = None
    ) -> str:
        """
        Get a complete response text without streaming.

        Args:
            system_prompt: The system prompt
            user_prompt: The user prompt
            model: The model to use (defaults to instance's model)

        Returns:
            The complete response text
        """
        model_to_use = model or self.model

        if self.enable_streaming:
            chunks = []
            async for chunk in self.chat_completion(
                system_prompt, user_prompt, model_to_use, stream=True
            ):
                chunks.append(chunk)

            full_response = "".join(chunks)
        else:
            async for chunk in self.chat_completion(
                system_prompt, user_prompt, model_to_use, stream=False
            ):
                full_response = chunk
                break

        return full_response

    def detect_vision_capability(self, model_info: ModelInfo) -> bool:
        """Check if a model supports vision capabilities."""
        return model_info.supports_vision

    async def check_capabilities(self, model_name: str) -> Dict[str, bool]:
        """
        Check if a model supports text generation and optionally vision.

        Args:
            model_name: The name of the model to check

        Returns:
            Dictionary with capability flags
        """
        capabilities = {"text": False, "vision": False}

        try:
            text_models, vision_models = await self.get_available_models()

            for model in text_models:
                if model.id == model_name or model.name == model_name:
                    capabilities["text"] = True
                    return capabilities

            for model in vision_models:
                if model.id == model_name or model.name == model_name:
                    capabilities["text"] = True
                    capabilities["vision"] = True
                    return capabilities

        except Exception as e:
            logger.warning(f"Capability check failed for {model_name}: {e}")

        return capabilities

    async def test_connection(self) -> Dict[str, Any]:
        """Test the connection and return status with helpful error messages."""
        policy = EndpointPolicy()
        result = await probe_endpoint(self.base_url, policy=policy, timeout_s=5)

        suggestions: list[str] = []
        if result.hint:
            suggestions.append(result.hint)

        return {
            "connected": result.reachable,
            "error": None if result.reachable else "Server not reachable",
            "suggestions": suggestions,
        }


__all__ = ["InferenceEngine", "ModelInfo", "_VISION_INDICATORS"]

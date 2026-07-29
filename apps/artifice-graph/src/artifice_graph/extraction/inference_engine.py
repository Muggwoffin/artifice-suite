"""Unified LLM Inference Engine with OpenAI compatibility."""

import logging
from typing import AsyncGenerator, Any, Dict, List, Optional

import httpx

from model_harness.endpoint_policy import EndpointPolicy

logger = logging.getLogger(__name__)


class VisionCapabilityChecker:
    """Helper class to detect and check vision model capabilities."""

    @staticmethod
    def extract_vision_models(model_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        vision_models = []
        model_details = model_info.get("model", {})
        model_name = str(model_info.get("id", "")).lower()

        vision_indicators = [
            "vision", "vl", "multi-modal", "image", "visual",
            "qwen", "llava", "dot.*/llava", "vision.*gpt"
        ]

        if any(indicator in model_name for indicator in vision_indicators):
            vision_models.append({
                "id": model_info.get("id", ""),
                "name": model_info.get("name", model_info.get("id", "")),
                "supports_vision": True,
                "supports_chat": model_details.get("supports_chat", True),
                "supports_images": model_details.get("supports_images", True),
                "max_tokens": model_details.get("max_tokens", 8192),
                "description": model_details.get("description", "")
            })

        return vision_models

    @staticmethod
    def extract_openai_vision_models(model_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        vision_models = []
        for model in model_data.get("data", []):
            model_id = model.get("id", "").lower()
            vision_indicators = [
                "vision", "vl", "multi-modal", "image", "visual",
                "gpt-4-vision", "claude-3-opus", "claude-3-sonnet"
            ]

            if any(indicator in model_id for indicator in vision_indicators):
                model_obj = {
                    "id": model["id"],
                    "name": model.get("name", model["id"]),
                    "owned_by": model.get("owned_by", "openai"),
                    "created": model.get("created", 0),
                    "supports_vision": True,
                    "max_completion_tokens": model.get("max_completion_tokens"),
                    "max_context_length": model.get("max_context_length")
                }
                vision_models.append(model_obj)

        return vision_models


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
            "description": self.description
        }


class InferenceEngine:
    """OpenAI-compatible inference engine with vision support and fallback parsing."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        api_key: str = "",
        model: str = "gemma2:27b",
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
        self.vision_checker = VisionCapabilityChecker()

    async def close(self) -> None:
        await self.client.aclose()

    async def health_check(self) -> bool:
        """Check if the server is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5) as test_client:
                response = await test_client.get(
                    self.base_url.replace("/v1", ""),
                    timeout=5
                )
                self.last_status = "connected" if response.status_code == 200 else "error"
                return response.status_code == 200
        except Exception as e:
            logger.debug(f"Health check failed: {e}")
            self.last_status = "error"
            return False

    async def get_available_models(self) -> tuple[List[ModelInfo], List[ModelInfo]]:
        """
        Get available models and return both text and vision models.

        Returns:
            tuple: (text_models, vision_models)
        """
        text_models = []
        vision_models = []

        ollama_models = []
        openai_models = []

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                ollama_base = self.base_url.replace("/v1", "")

                resp = await client.get(f"{ollama_base}/api/tags", timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    for model_info in data.get("models", []):
                        ollama_models.append(model_info)

                try:
                    resp = await client.get(
                        f"{self.base_url}/models",
                        headers={"Authorization": f"Bearer {self.api_key}" if self.api_key else None},
                        timeout=10
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        openai_models = data.get("data", []) or data.get("models", [])
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Failed to fetch models: {e}")

        for model_info in ollama_models:
            vision_models.extend(
                self.vision_checker.extract_vision_models(model_info)
            )

        for model_info in openai_models:
            vision_models.extend(
                self.vision_checker.extract_openai_vision_models({"data": [model_info]})
            )
            if not any(m.id == model_info.get("id", "") for m in text_models):
                text_models.append(ModelInfo(model_info, "openai"))

        return text_models, vision_models

    async def _make_chat_request(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        stream: bool = False
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
        headers = {
            "Content-Type": "application/json"
        }

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1,
            "stream": stream
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
                api_path,
                headers=headers,
                json=payload,
                timeout=self.timeout
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
        stream: bool = False
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

        async for chunk in self._make_chat_request(system_prompt, user_prompt, model_to_use, stream):
            yield chunk

    async def get_response_text(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None
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
            async for chunk in self.chat_completion(system_prompt, user_prompt, model_to_use, stream=True):
                chunks.append(chunk)

            full_response = "".join(chunks)
        else:
            async for chunk in self.chat_completion(system_prompt, user_prompt, model_to_use, stream=False):
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
        status = {
            "connected": await self.health_check(),
            "error": None,
            "suggestios": []
        }

        if not status["connected"]:
            status["error"] = "Server not reachable"
            if self.base_url.endswith("/v1"):
                base_url = self.base_url.replace("/v1", "")
            else:
                base_url = self.base_url

            if "11434" in base_url:
                status["suggestions"].append(
                    "For Ollama: Make sure the server is running with 'ollama serve'"
                )
                status["suggestions"].append(
                    "For Ollama: Set OLLAMA_ORIGINS=* to allow cross-origin requests"
                )
            elif "1234" in base_url:
                status["suggestions"].append(
                    "For LM Studio: Ensure the LM Studio server is running and accessible"
                )

            status["suggestions"].append(
                "Check if the server URL is correct and accessible from your browser"
            )

        return status


__all__ = ["InferenceEngine", "ModelInfo", "VisionCapabilityChecker"]
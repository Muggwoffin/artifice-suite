# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

"""Unified backend abstraction for LLMs (Ollama, LM Studio, Hugging Face)."""

import logging
from typing import Any
import ollama
from openai import OpenAI
from huggingface_hub import InferenceClient
from model_harness.contract import EndpointRejected
from model_harness.endpoint_policy import EndpointPolicy
from . import config

logger = logging.getLogger(__name__)

_endpoint_policy = EndpointPolicy()


def _validate_url(url: str, field_name: str) -> str:
    """Validate a model endpoint URL through the harness policy.

    Raises :class:`~model_harness.contract.EndpointRejected` if the URL
    is not permitted by the local-first endpoint policy.
    """
    try:
        return _endpoint_policy.validate_url(url)
    except EndpointRejected as e:
        raise EndpointRejected(f"{field_name}: {e}") from e

_THINK_UNSUPPORTED_HINTS = (
    "does not support thinking",
    "thinking is not supported",
    "unknown field",
    "unexpected keyword argument",
    "think",
)


def _is_think_unsupported(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(hint in msg for hint in _THINK_UNSUPPORTED_HINTS)


class _SimpleMessage:
    def __init__(self, content: str):
        self.content = content


class _SimpleResponse:
    def __init__(self, content: str):
        self.message = _SimpleMessage(content)


class OllamaBackend:
    def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        think: bool | None = None,
        num_predict: int | None = None,
    ) -> Any:
        host = config.get("ollama_url") or "http://localhost:11434"
        _validate_url(host, "ollama_url")
        ollama.host = host
        options: dict[str, Any] = {"temperature": temperature}
        if num_predict is not None:
            options["num_predict"] = num_predict

        kwargs: dict[str, Any] = {"model": model, "messages": messages, "options": options}
        if think is not None:
            kwargs["think"] = think

        if think is None:
            return ollama.chat(**kwargs)

        try:
            return ollama.chat(**kwargs)
        except Exception as exc:
            if _is_think_unsupported(exc):
                logger.debug(
                    "Ollama model '%s' rejected think parameter (%s); retrying without.",
                    model,
                    exc,
                )
                kwargs.pop("think", None)
                return ollama.chat(**kwargs)
            raise


class OllamaOpenAIBackend:
    """Ollama via its OpenAI-compatible ``/v1`` endpoint.

    The native Ollama API carries images in an ``images`` field while
    multimodal vision models are sent ``image_url`` content blocks.  This
    backend hits the ``/v1`` endpoint so OCR can use the same message format
    across every backend without a format conversion in the middle.
    """

    def _client(self) -> OpenAI:
        base_url = (config.get("ollama_url") or "http://localhost:11434") + "/v1"
        _validate_url(base_url, "ollama_url")
        return OpenAI(base_url=base_url, api_key="ollama")

    def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        think: bool | None = None,
        num_predict: int | None = None,
    ) -> Any:
        client = self._client()
        kwargs: dict[str, Any] = {}
        if num_predict is not None:
            kwargs["max_tokens"] = num_predict

        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            **kwargs,
        )
        content = resp.choices[0].message.content or ""
        return _SimpleResponse(content)


class LMStudioBackend:
    def _client(self) -> OpenAI:
        base_url = config.get("lm_studio_url") or "http://localhost:1234/v1"
        _validate_url(base_url, "lm_studio_url")
        return OpenAI(base_url=base_url, api_key="lm-studio")

    def health_check(self) -> tuple[bool, str | None]:
        """Return (ok, error_detail)."""
        url = config.get("lm_studio_url") or "http://localhost:1234/v1"
        _validate_url(url, "lm_studio_url")
        try:
            self._client().models.list()
            return True, None
        except Exception as exc:
            return False, f"Cannot reach LM Studio at {url}. Is it running?"

    def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        think: bool | None = None,
        num_predict: int | None = None,
    ) -> Any:
        client = self._client()
        kwargs: dict[str, Any] = {}
        if num_predict is not None:
            kwargs["max_tokens"] = num_predict

        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            **kwargs,
        )
        content = resp.choices[0].message.content or ""
        return _SimpleResponse(content)


class HuggingFaceBackend:
    """Hugging Face Inference API backend.

    This backend connects to the public Hugging Face Inference API.
    Like :class:`ApiKeyBackend`, it requires
    ``ARTIFICE_ALLOW_PUBLIC_MODELS=1`` in the environment — a deliberate
    opt-in from a user who has already provided a HuggingFace token.

    There is no user-supplied URL here because the SDK always connects
    to HuggingFace's own hosted service.  The validation is a direct
    check against the endpoint policy to confirm public endpoints are
    permitted.  The same policy governs every other backend in this file.
    """

    def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        think: bool | None = None,
        num_predict: int | None = None,
    ) -> Any:
        # HuggingFace Inference API is a public cloud service; the
        # endpoint policy must permit public endpoints first.
        _validate_url(
            "https://api-inference.huggingface.co/models",
            "huggingface",
        )

        token = config.get("huggingface_token") or None
        client = InferenceClient(token=token)
        kwargs: dict[str, Any] = {}
        if num_predict is not None:
            kwargs["max_tokens"] = num_predict

        resp = client.chat_completion(
            model=model,
            messages=messages,
            temperature=temperature,
            **kwargs,
        )
        content = resp.choices[0].message.content or ""
        return _SimpleResponse(content)


class ApiKeyBackend:
    """Any OpenAI-compatible cloud API (OpenAI, Together, Groq, etc.).

    The default endpoint is ``https://api.openai.com/v1``, which is a
    public address.  The endpoint policy denies public endpoints unless
    ``ARTIFICE_ALLOW_PUBLIC_MODELS=1`` is set in the environment —
    a deliberate opt-in that a user who has already entered an API key
    must also make.  See :class:`model_harness.endpoint_policy.EndpointPolicy`.
    """

    def _client(self) -> OpenAI:
        base_url = config.get("api_base_url") or "https://api.openai.com/v1"
        api_key = config.get("api_key") or ""
        _validate_url(base_url, "api_base_url")
        return OpenAI(base_url=base_url, api_key=api_key)

    def health_check(self) -> tuple[bool, str | None]:
        """Return (ok, error_detail)."""
        api_key = config.get("api_key")
        if not api_key:
            return False, "No API key configured"
        base_url = config.get("api_base_url") or "https://api.openai.com/v1"
        _validate_url(base_url, "api_base_url")
        try:
            self._client().models.list()
            return True, None
        except Exception as exc:
            return False, str(exc)

    def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        think: bool | None = None,
        num_predict: int | None = None,
    ) -> Any:
        client = self._client()
        kwargs: dict[str, Any] = {}
        if num_predict is not None:
            kwargs["max_tokens"] = num_predict

        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            **kwargs,
        )
        content = resp.choices[0].message.content or ""
        return _SimpleResponse(content)


def get_client(backend: str) -> Any:
    b = (backend or "ollama").lower()
    if b == "lm_studio":
        return LMStudioBackend()
    elif b == "ollama_openai":
        return OllamaOpenAIBackend()
    elif b == "huggingface":
        return HuggingFaceBackend()
    elif b == "api_key":
        return ApiKeyBackend()
    else:
        return OllamaBackend()

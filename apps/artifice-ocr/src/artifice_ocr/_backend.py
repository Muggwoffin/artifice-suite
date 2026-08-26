# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unified backend abstraction for LLMs (Ollama, LM Studio, Hugging Face)."""

import logging
from typing import Any

import ollama
from huggingface_hub import InferenceClient
from model_harness.contract import EndpointRejected
from model_harness.discovery import normalise_base_url
from model_harness.endpoint_policy import EndpointPolicy
from openai import NotFoundError, OpenAI

from . import config
from ._resolution import _redact_url

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


# Distinct ``(backend, base_url)`` pairs already logged at INFO.  Backends are
# recreated per call (per page) by design, so without this the pipeline would
# emit one INFO line per page; the first construction of a given URL logs at
# INFO and repeats log at DEBUG.
_logged_base_urls: set[tuple[str, str]] = set()


def _log_base_url_once(backend: str, base_url: str) -> None:
    """Log a backend's constructed base URL once per distinct URL per process."""
    key = (backend, base_url)
    if key in _logged_base_urls:
        logger.debug("Reusing %s backend client: base_url=%s", backend, _redact_url(base_url))
        return
    _logged_base_urls.add(key)
    logger.info("Constructing %s backend client: base_url=%s", backend, _redact_url(base_url))


def _provider_404(exc: Exception, *, base_url: str, model: str) -> RuntimeError:
    """Wrap a provider 404 into a RuntimeError naming what was actually called.

    A raw ``openai.NotFoundError`` surfaces as the provider's bare message with
    no indication of which URL was attempted — the exact shape that made a
    doubled ``/v1`` invisible.  The message carries the base URL and model so
    the next such failure names itself.
    """
    return RuntimeError(
        f"Provider returned 404 for model '{model}' at {_redact_url(base_url)}: {exc}"
    )


def _guarded_chat(call, *, base_url: str, model: str) -> Any:
    """Run *call*, translating a provider 404 into a self-describing error."""
    try:
        return call()
    except NotFoundError as exc:
        raise _provider_404(exc, base_url=base_url, model=model) from exc
    except ollama.ResponseError as exc:
        if getattr(exc, "status_code", None) == 404:
            raise _provider_404(exc, base_url=base_url, model=model) from exc
        raise


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
        normalised = normalise_base_url(host)
        _validate_url(normalised, "ollama_url")
        _log_base_url_once("ollama", normalised)
        client = ollama.Client(host=normalised)
        options: dict[str, Any] = {"temperature": temperature}
        if num_predict is not None:
            options["num_predict"] = num_predict

        kwargs: dict[str, Any] = {"model": model, "messages": messages, "options": options}
        if think is not None:
            kwargs["think"] = think

        if think is None:
            return _guarded_chat(lambda: client.chat(**kwargs), base_url=normalised, model=model)

        try:
            return _guarded_chat(lambda: client.chat(**kwargs), base_url=normalised, model=model)
        except Exception as exc:
            if _is_think_unsupported(exc):
                logger.debug(
                    "Ollama model '%s' rejected think parameter (%s); retrying without.",
                    model,
                    exc,
                )
                kwargs.pop("think", None)
                return _guarded_chat(
                    lambda: client.chat(**kwargs), base_url=normalised, model=model
                )
            raise


class OllamaOpenAIBackend:
    """Ollama via its OpenAI-compatible ``/v1`` endpoint.

    The native Ollama API carries images in an ``images`` field while
    multimodal vision models are sent ``image_url`` content blocks.  This
    backend hits the ``/v1`` endpoint so OCR can use the same message format
    across every backend without a format conversion in the middle.
    """

    def _base_url(self) -> str:
        raw = config.get("ollama_url") or "http://localhost:11434"
        return normalise_base_url(raw) + "/v1"

    def _client(self) -> OpenAI:
        base_url = self._base_url()
        _validate_url(base_url, "ollama_url")
        _log_base_url_once("ollama_openai", base_url)
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
        base_url = self._base_url()
        client = self._client()
        kwargs: dict[str, Any] = {}
        if num_predict is not None:
            kwargs["max_tokens"] = num_predict

        resp = _guarded_chat(
            lambda: client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                **kwargs,
            ),
            base_url=base_url,
            model=model,
        )
        content = resp.choices[0].message.content or ""
        return _SimpleResponse(content)


class LMStudioBackend:
    """OpenAI-compatible LM Studio backend.

    .. note::

       ``LMStudioBackend.health_check`` was removed in the 2b migration.
       The same check now lives in :func:`artifice_ocr.utils.check_lm_studio`,
       which delegates to :func:`model_harness.discovery.probe_endpoint_sync`.
       Nothing is broken; the surface has moved, not disappeared.
    """

    def _base_url(self) -> str:
        return config.get("lm_studio_url") or "http://localhost:1234/v1"

    def _client(self) -> OpenAI:
        base_url = self._base_url()
        _validate_url(base_url, "lm_studio_url")
        _log_base_url_once("lm_studio", base_url)
        return OpenAI(base_url=base_url, api_key="lm-studio")

    def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        think: bool | None = None,
        num_predict: int | None = None,
    ) -> Any:
        base_url = self._base_url()
        client = self._client()
        kwargs: dict[str, Any] = {}
        if num_predict is not None:
            kwargs["max_tokens"] = num_predict

        resp = _guarded_chat(
            lambda: client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                **kwargs,
            ),
            base_url=base_url,
            model=model,
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

    def _base_url(self) -> str:
        return config.get("api_base_url") or "https://api.openai.com/v1"

    def _client(self) -> OpenAI:
        base_url = self._base_url()
        api_key = config.get("api_key") or ""
        _validate_url(base_url, "api_base_url")
        _log_base_url_once("api_key", base_url)
        return OpenAI(base_url=base_url, api_key=api_key)

    def health_check(self) -> tuple[bool, str | None]:
        """Return (ok, error_detail)."""
        api_key = config.get("api_key")
        if not api_key:
            return False, "No API key configured"
        base_url = self._base_url()
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
        base_url = self._base_url()
        client = self._client()
        kwargs: dict[str, Any] = {}
        if num_predict is not None:
            kwargs["max_tokens"] = num_predict

        resp = _guarded_chat(
            lambda: client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                **kwargs,
            ),
            base_url=base_url,
            model=model,
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

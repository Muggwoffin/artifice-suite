# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""LLM integration for copy-editing paragraphs.

Supports multiple providers (Ollama, OpenAI, Anthropic) and batches paragraphs
with dynamic token-aware chunking.  The LLM call routes through
:func:`model_harness.driver.run_structured` so the response is schema-validated
and the caller receives a guaranteed result with ``mode_used`` and ``repaired``
logged.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import requests

from artifice_draft.config import AppConfig
from artifice_draft.llm_edit import (
    LLMEdit,
    _DraftEditEntry,
    _DraftEditsShape,
)
from artifice_draft.llm_utils import (
    _compute_dynamic_batch_sizes,
    build_user_prompt,
)
from artifice_draft.models import LLMProvider, PipelineProgress, ProgressCallback
from artifice_draft.prompts import get_system_prompt

from model_harness.anthropic_adapter import AnthropicProvider
from model_harness.contract import (
    HarnessResult,
    ModelConnectorConfig,
    SchemaValidationFailed,
    StructuredOutputMode,
    StructuredOutputUnsupported,
    StructuredRequest,
)
from model_harness.driver import run_structured
from model_harness.endpoint_policy import EndpointPolicy as ConcreteEndpointPolicy
from model_harness.openai_adapter import OpenAIProvider

logger = logging.getLogger(__name__)

_endpoint_policy = ConcreteEndpointPolicy()

# ---------------------------------------------------------------------------
# Provider adapter construction
# ---------------------------------------------------------------------------

def _build_adapter(
    config: AppConfig,
    policy: ConcreteEndpointPolicy | None = None,
) -> OpenAIProvider | AnthropicProvider:
    """Build the correct :class:`ModelProvider` adapter for *config*.

    Both Ollama and OpenAI use an OpenAI-compatible chat-completions
    protocol, so they share the :class:`OpenAIProvider` adapter.
    Anthropic uses the :class:`AnthropicProvider` adapter, which
    declares the ``JSON_OBJECT`` gap in its ``supported_modes``.
    """
    if config.llm_provider == LLMProvider.ANTHROPIC:
        return AnthropicProvider(endpoint_policy=policy)
    return OpenAIProvider(
        provider_type="ollama",             # both Ollama and OpenAI support json_object
        endpoint_policy=policy,
    )


# ---------------------------------------------------------------------------
# ModelConnectorConfig mapping
# ---------------------------------------------------------------------------

def _provider_str(config: AppConfig) -> str:
    """Map draft's :class:`LLMProvider` enum to a harness ``Provider`` literal."""
    if config.llm_provider == LLMProvider.ANTHROPIC:
        return "anthropic"
    if config.llm_provider == LLMProvider.OPENAI:
        return "generic-api"               # no "openai" in the Provider literal yet
    return "ollama"


def _endpoint_for(config: AppConfig) -> str:
    """Return the endpoint URL for the active provider.

    The adapter appends ``/chat/completions`` (OpenAI) or ``/v1/messages``
    (Anthropic), so the endpoint here is the base before those path segments.
    """
    if config.llm_provider == LLMProvider.ANTHROPIC:
        return "https://api.anthropic.com"
    if config.llm_provider == LLMProvider.OPENAI:
        return config.openai_base_url.rstrip("/")
    # Ollama — the base_url typically ends with /v1 (e.g.
    # http://localhost:11434/v1).  The adapter appends /chat/completions
    # to produce http://localhost:11434/v1/chat/completions, which is the
    # correct Ollama OpenAI-compatible endpoint.
    return config.base_url.rstrip("/")


def _api_key_for(config: AppConfig) -> str | None:
    """Return the API key for the active provider, or None."""
    if config.llm_provider == LLMProvider.ANTHROPIC:
        return config.anthropic_api_key or None
    if config.llm_provider == LLMProvider.OPENAI:
        return config.openai_api_key or None
    # Ollama — no key needed, but pass "not-needed" for local adapters
    return None


# ---------------------------------------------------------------------------
# Fallback edit helpers (preserved from the old _parse_llm_response)
# ---------------------------------------------------------------------------

def _fallback_unchanged(batch: list[dict]) -> list[LLMEdit]:
    """Mark every paragraph in *batch* as unchanged.

    Used when the harness cannot produce a valid response — the same
    graceful-degradation behaviour the old ``_parse_llm_response`` provided.
    """
    return [
        LLMEdit(
            paragraph_index=p["paragraph_index"],
            original_text=p["text"],
            edited_text=None,
            status="unchanged",
        )
        for p in batch
    ]


# ---------------------------------------------------------------------------
# Response mapping (preserved from the pre-harness code)
# ---------------------------------------------------------------------------

def _map_response_to_batch_edits(
    result: list[dict], batch: list[dict], batch_start: int
) -> list[LLMEdit]:
    """Map parsed LLM response entries to LLMEdit objects using batch offsets.

    Each entry in *result* is expected to have ``paragraph_index``,
    ``edited_text`` and ``status`` keys.  The function matches entries to
    paragraphs in *batch* by index, falling back to positional lookup when the
    index does not appear in the batch but still falls within its range.
    Entries whose index is entirely outside the batch are discarded with a
    warning.
    """
    edits: list[LLMEdit] = []

    for entry in result:
        idx = entry.get("paragraph_index", batch_start)
        edited_text = entry.get("edited_text")
        status = entry.get("status", "unchanged")

        matched_para = None
        for p in batch:
            if p["paragraph_index"] == idx:
                matched_para = p
                break

        if matched_para is not None:
            edits.append(LLMEdit(
                paragraph_index=idx,
                original_text=matched_para["text"],
                edited_text=edited_text,
                status=status,
            ))
        elif batch_start <= idx < batch_start + len(batch):
            edits.append(LLMEdit(
                paragraph_index=idx,
                original_text=batch[idx - batch_start]["text"],
                edited_text=edited_text,
                status=status,
            ))
        else:
            logger.warning(
                "LLM returned index %d outside batch range [%d, %d); discarding",
                idx, batch_start, batch_start + len(batch),
            )

    return edits


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def call_ollama(
    paragraphs: list[dict] | None = None,
    batch_size: int = 5,
    system_prompt: str | None = None,
    config: AppConfig | None = None,
    on_progress: ProgressCallback | None = None,
) -> list[LLMEdit]:
    """Send a batch of paragraphs to the configured LLM and parse the response.

    Args:
        paragraphs: List of paragraph dicts from doc_parser.parse_docx().
        batch_size: Maximum number of paragraphs per API call.
        system_prompt: Optional custom system prompt; uses style-based default if None.
        config: The application configuration object.
        on_progress: Optional callback for progress updates.

    Returns a list of LLMEdit objects, one per paragraph in the chunk.
    """
    if config is None:
        config = AppConfig()

    edits: list[LLMEdit] = []
    if paragraphs is None:
        return edits

    sys_prompt = system_prompt or get_system_prompt(
        style=config.editing_style,
        custom_prompt=config.custom_system_prompt,
        style_guide_name=config.style_guide,
    )

    max_tokens = config.num_ctx
    batches = _compute_dynamic_batch_sizes(paragraphs, batch_size, max_tokens)
    total = len(paragraphs)
    processed = 0

    # ── Harness infrastructure (constructed once, reused across batches) ───
    policy = ConcreteEndpointPolicy()
    adapter = _build_adapter(config, policy=policy)
    schema_json = _DraftEditsShape.model_json_schema()

    provider_str = _provider_str(config)
    endpoint = _endpoint_for(config)
    api_key = _api_key_for(config)
    model = config.active_model

    progress = PipelineProgress(total_paragraphs=total)

    # ── Async inner loop ───────────────────────────────────────────────────
    # call_ollama is synchronous.  We run the entire batch loop inside a
    # single ``asyncio.run()`` call so the adapter (and its httpx client)
    # live within one event loop.  A fresh daemon Thread (web path) has no
    # running loop, and ``cli.py`` is plain synchronous code — both are safe.
    # If a future caller invokes call_ollama from inside a running event
    # loop, asyncio.run() will raise RuntimeError, which we catch and
    # re-raise with a clear message rather than a cryptic traceback.

    async def _run_all_batches() -> list[LLMEdit]:
        _edits: list[LLMEdit] = []
        _processed = 0

        for batch_idx, batch in enumerate(batches):
            batch_start = sum(len(b) for b in batches[:batch_idx])
            batch_end = batch_start + len(batch)

            user_prompt = build_user_prompt(batch)

            logger.info(
                "Sending batch %d–%d (%d paragraphs) to %s",
                batch_start, batch_end - 1, len(batch), config.llm_provider.value,
            )

            progress.update(
                "llm_processing", _processed,
                f"Processing paragraphs {batch_start + 1}–{batch_end} of {total}",
            )
            if on_progress:
                on_progress(progress)

            model_config = ModelConnectorConfig(
                provider=provider_str,  # type: ignore[arg-type]
                endpoint=endpoint,
                model=model,
                api_key=api_key,
                timeout_s=120.0,
            )

            request = StructuredRequest(
                instructions=sys_prompt,
                input=user_prompt,
                schema_json=schema_json,
                mode=StructuredOutputMode.PROMPTED,
                config=model_config,
            )

            try:
                result: HarnessResult[_DraftEditsShape] = await run_structured(
                    request,
                    adapter,
                    _DraftEditsShape,
                    endpoint_policy=policy,
                )
            except (StructuredOutputUnsupported, SchemaValidationFailed) as exc:
                logger.warning(
                    "Harness failed for batch %d–%d: %s",
                    batch_start, batch_end - 1, exc,
                )
                batch_edits = _fallback_unchanged(batch)
                _edits.extend(batch_edits)
                _processed += len(batch)
                continue
            except Exception:
                logger.exception(
                    "Unexpected harness error for batch %d–%d",
                    batch_start, batch_end - 1,
                )
                batch_edits = _fallback_unchanged(batch)
                _edits.extend(batch_edits)
                _processed += len(batch)
                continue

            logger.info(
                "Batch %d–%d: mode_used=%s repaired=%s",
                batch_start, batch_end - 1,
                result.mode_used.value,
                result.repaired,
            )

            # Convert validated entries to plain dicts for _map_response_to_batch_edits.
            # model_dump(exclude_none=True) omits fields the model did not
            # set, preserving the fallback defaults in the mapping function.
            entries: list[dict[str, Any]] = [
                e.model_dump(exclude_none=True) for e in result.data.edits
            ]

            batch_edits = _map_response_to_batch_edits(entries, batch, batch_start)
            _edits.extend(batch_edits)
            _processed += len(batch)

        return _edits

    # ── Sync / async boundary ──────────────────────────────────────────────
    # asyncio.run() creates a fresh event loop and runs _run_all_batches to
    # completion.  This is safe because neither call site (cli.py:180,
    # web/runtime.py:283 inside a daemon Thread) runs within an existing
    # event loop.  If a future caller violates that assumption the
    # RuntimeError is caught and re-raised with an actionable message.
    try:
        edits = asyncio.run(_run_all_batches())
    except RuntimeError as exc:
        if "cannot be called from a running event loop" in str(exc):
            raise RuntimeError(
                "call_ollama was invoked from within a running asyncio event "
                "loop.  This function is a synchronous wrapper; use the async "
                "harness path directly instead."
            ) from exc
        raise

    progress.update("llm_processing", total, f"LLM processing complete — {len(edits)} results")
    if on_progress:
        on_progress(progress)

    logger.info("LLM returned %d edit results", len(edits))
    return edits


# ---------------------------------------------------------------------------
# Model discovery (validated through the endpoint policy)
# ---------------------------------------------------------------------------

def get_available_models(base_url: str, api_key: str = "not-needed") -> list[dict]:
    """Query {base_url}/models (or /v1/models) to auto-discover available models and capabilities.

    The *base_url* is validated through
    :class:`~model_harness.endpoint_policy.EndpointPolicy` before any
    request is made — the same rule that governs every other model endpoint
    in this suite.
    """
    _endpoint_policy.validate_url(base_url)
    base = base_url.rstrip("/")
    urls_to_try = [f"{base}/models", f"{base}/v1/models"]
    if base.endswith("/v1"):
        urls_to_try = [f"{base}/models", f"{base[:-3]}/models"]
    elif base.endswith("/api"):
        urls_to_try.append(f"{base}/tags")

    headers = {}
    if api_key and api_key != "not-needed":
        headers["Authorization"] = f"Bearer {api_key}"

    last_error = None
    for url in urls_to_try:
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            models_list = []
            items = data.get("data", data.get("models", data))
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        m_id = item.get("id", item.get("name", str(item)))
                    else:
                        m_id = str(item)
                    is_vision = any(k in m_id.lower() for k in ["vision", "vl", "multimodal", "llava", "qwen2-vl", "qwen2.5-vl", "pixtral"])
                    models_list.append({"id": m_id, "name": m_id, "vision": is_vision})
                return models_list
        except Exception as e:
            last_error = e

    raise ConnectionError(
        f"Server unreachable at {base_url}. "
        f"If running Ollama locally, ensure Ollama is running and set environment variable OLLAMA_ORIGINS=* (or check CORS settings). Details: {last_error}"
    )


def test_connection(base_url: str, api_key: str = "not-needed") -> dict:
    _endpoint_policy.validate_url(base_url)
    try:
        models = get_available_models(base_url, api_key)
        return {"success": True, "models": models, "message": f"Connected successfully! Found {len(models)} models."}
    except Exception as e:
        return {"success": False, "models": [], "error": str(e)}


# ---------------------------------------------------------------------------
# Smoke test (unchanged)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m artifice_draft.llm_client test_paragraphs.json")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        raw_data = json.load(f)
        paragraphs = raw_data if isinstance(raw_data, list) else raw_data.get("paragraphs", [])

    edits = call_ollama(paragraphs=paragraphs)
    for e in edits:
        print(f"[{e.paragraph_index}] {e.status}: {e.edited_text or '(no change)'}")

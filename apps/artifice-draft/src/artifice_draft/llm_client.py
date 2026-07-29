"""LLM integration for copy-editing paragraphs.

Supports multiple providers (Ollama, OpenAI, Anthropic) and batches paragraphs
with dynamic token-aware chunking. The model is asked to return JSON with edited
text per paragraph, preserving the original structure so we can apply changes as
track edits later.
"""

import json
import logging
import re
import time
from typing import Callable, Any
from enum import Enum
from typing import Any, Callable, TypedDict

import requests

from artifice_draft.config import AppConfig
from artifice_draft.llm_edit import LLMEdit
from artifice_draft.llm_utils import (
    _CHARS_PER_TOKEN,
    _compute_dynamic_batch_sizes,
    _estimate_tokens,
    build_user_prompt,
)
from artifice_draft.models import LLMProvider, PipelineProgress, ProgressCallback
from artifice_draft.prompts import get_system_prompt

logger = logging.getLogger(__name__)


def parse_llm_json_response(raw_response: str) -> list[dict] | dict:
    """Robust parser for local models that may return malformed JSON or markdown code blocks."""
    cleaned = raw_response.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try stripping markdown code fences
    code_block_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if code_block_match:
        try:
            return json.loads(code_block_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try finding JSON array or object using regex search
    json_array_match = re.search(r"\[[\s\S]*\]", cleaned)
    if json_array_match:
        try:
            return json.loads(json_array_match.group(0))
        except json.JSONDecodeError:
            pass

    json_obj_match = re.search(r"\{[\s\S]*\}", cleaned)
    if json_obj_match:
        try:
            return json.loads(json_obj_match.group(0))
        except json.JSONDecodeError:
            pass

    raise json.JSONDecodeError("Could not extract valid JSON from response", cleaned, 0)


class InferenceEngine:
    """Unified Inference Adapter supporting any OpenAI-compatible endpoint (Ollama, LM Studio, vLLM, LocalAI, Jan.ai, OpenAI API)."""
    def __init__(self, base_url: str = "http://localhost:11434/v1", api_key: str = "not-needed", model: str = "gemma4:12b", temperature: float = 0.3, num_ctx: int = 8192, vision_enabled: bool = False):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or "not-needed"
        self.model = model
        self.temperature = temperature
        self.num_ctx = num_ctx
        self.vision_enabled = vision_enabled

    def chat_completion(self, sys_prompt: str, user_prompt: str, stream_callback: Callable[[str], None] | None = None) -> str:
        url = f"{self.base_url}/chat/completions"
        if not self.base_url.endswith("/v1") and "api.openai.com" not in self.base_url and "localhost:11434" in self.base_url:
            url = f"{self.base_url}/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.num_ctx,
            "stream": bool(stream_callback),
        }

        if stream_callback:
            try:
                response = requests.post(url, json=payload, headers=headers, stream=True, timeout=120)
                response.raise_for_status()
                full_content = []
                for line in response.iter_lines():
                    if line:
                        line_str = line.decode("utf-8")
                        if line_str.startswith("data: "):
                            data_str = line_str[6:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk_json = json.loads(data_str)
                                delta = chunk_json.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                if delta:
                                    full_content.append(delta)
                                    stream_callback(delta)
                            except Exception:
                                pass
                return "".join(full_content)
            except Exception as e:
                logger.warning("Streaming request failed, falling back to non-streaming: %s", e)
                payload["stream"] = False

        response = requests.post(url, json=payload, headers=headers, timeout=120)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


def get_available_models(base_url: str, api_key: str = "not-needed") -> list[dict]:
    """Query {base_url}/models (or /v1/models) to auto-discover available models and capabilities."""
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
    try:
        models = get_available_models(base_url, api_key)
        return {"success": True, "models": models, "message": f"Connected successfully! Found {len(models)} models."}
    except Exception as e:
        return {"success": False, "models": [], "error": str(e)}


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

    progress = PipelineProgress(total_paragraphs=total)

    for batch_idx, batch in enumerate(batches):
        batch_start = sum(len(b) for b in batches[:batch_idx])
        batch_end = batch_start + len(batch)

        user_prompt = build_user_prompt(batch)

        logger.info(
            "Sending batch %d–%d (%d paragraphs) to %s",
            batch_start, batch_end - 1, len(batch), config.llm_provider.value,
        )

        progress.update("llm_processing", processed, f"Processing paragraphs {batch_start+1}–{batch_end} of {total}")
        if on_progress:
            on_progress(progress)

        raw_response = _send_request_with_retry(
            model=config.active_model,
            sys_prompt=sys_prompt,
            user_prompt=user_prompt,
            config=config,
            stream_callback=None,
        )

        batch_edits = _parse_llm_response(raw_response, batch, batch_start)
        edits.extend(batch_edits)
        processed += len(batch)

    progress.update("llm_processing", total, f"LLM processing complete — {len(edits)} results")
    if on_progress:
        on_progress(progress)

    logger.info("LLM returned %d edit results", len(edits))
    return edits


def _recover_json_from_response(raw_response: str) -> list[dict]:
    """Extract structured entry dicts from the raw LLM response string.

    Returns a list of entry dicts.  Wraps a single-object response in a list.
    Raises :exc:`json.JSONDecodeError` or :exc:`ValueError` on failure —
    caller is responsible for the recovery path.
    """
    result = parse_llm_json_response(raw_response)
    if not isinstance(result, list):
        result = [result]
    return result


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


def _parse_llm_response(
    raw_response: str, batch: list[dict], batch_start: int
) -> list[LLMEdit]:
    """Parse the raw LLM JSON response into LLMEdit objects.

    Tries structured extraction first; falls back to marking every paragraph
    unchanged on parse failure.
    """
    edits: list[LLMEdit] = []

    try:
        result = _recover_json_from_response(raw_response)
    except (json.JSONDecodeError, ValueError):
        logger.warning(
            "Malformed JSON response for batch starting at %d; marking all unchanged",
            batch_start,
        )
        for p in batch:
            edits.append(LLMEdit(
                paragraph_index=p["paragraph_index"],
                original_text=p["text"],
                edited_text=None,
                status="unchanged",
            ))
        return edits

    return _map_response_to_batch_edits(result, batch, batch_start)


def _send_request_with_retry(
    model: str, sys_prompt: str, user_prompt: str, config: AppConfig, stream_callback: Callable[[str], None] | None = None
) -> str:
    """Route the request to the correct provider with retry logic using InferenceEngine."""
    base = getattr(config, "base_url", None) or getattr(config, "openai_base_url", "http://localhost:11434/v1")
    key = getattr(config, "api_key", None) or getattr(config, "openai_api_key", "not-needed")
    
    engine = InferenceEngine(
        base_url=base,
        api_key=key or "not-needed",
        model=model,
        temperature=config.temperature,
        num_ctx=config.num_ctx,
        vision_enabled=getattr(config, "vision_enabled", False),
    )

    for attempt in range(config.max_retries):
        try:
            logger.debug("Inference request attempt %d/%d to %s", attempt + 1, config.max_retries, engine.base_url)
            if config.llm_provider == LLMProvider.ANTHROPIC:
                return _send_anthropic_request(model, sys_prompt, user_prompt, config)
            else:
                return engine.chat_completion(sys_prompt, user_prompt, stream_callback=stream_callback)
        except (requests.RequestException, ValueError, KeyError) as e:
            if attempt == config.max_retries - 1:
                raise e
            logger.warning("Inference request failed (attempt %d/%d): %s", attempt + 1, config.max_retries, e)
            time.sleep(config.retry_delay_secs)

    return ""


def _send_ollama_request(
    model: str, sys_prompt: str, user_prompt: str, config: AppConfig
) -> str:
    """Send a request to Ollama's /api/generate endpoint."""
    payload = {
        "model": model,
        "system": sys_prompt,
        "prompt": user_prompt,
        "stream": False,
        "format": "json",
        "temperature": config.temperature,
        "num_ctx": config.num_ctx,
    }
    url = config.ollama_generate_url

    for attempt in range(config.max_retries):
        try:
            logger.debug("Ollama request attempt %d/%d to %s", attempt + 1, config.max_retries, url)
            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()
            return response.json().get("response", "")
        except (requests.RequestException, ValueError) as e:
            if attempt == config.max_retries - 1:
                raise e
            logger.warning("Ollama request failed (attempt %d/%d): %s", attempt + 1, config.max_retries, e)
            time.sleep(config.retry_delay_secs)

    return ""  # unreachable, but satisfies type checker


def _send_openai_request(
    model: str, sys_prompt: str, user_prompt: str, config: AppConfig
) -> str:
    """Send a request to the OpenAI-compatible /chat/completions endpoint."""
    url = f"{config.openai_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": config.temperature,
        "max_tokens": config.num_ctx,
        "response_format": {"type": "json_object"},
    }

    for attempt in range(config.max_retries):
        try:
            logger.debug("OpenAI request attempt %d/%d to %s", attempt + 1, config.max_retries, url)
            response = requests.post(url, json=payload, headers=headers, timeout=120)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except (requests.RequestException, ValueError, KeyError) as e:
            if attempt == config.max_retries - 1:
                raise e
            logger.warning("OpenAI request failed (attempt %d/%d): %s", attempt + 1, config.max_retries, e)
            time.sleep(config.retry_delay_secs)

    return ""


def _send_anthropic_request(
    model: str, sys_prompt: str, user_prompt: str, config: AppConfig
) -> str:
    """Send a request to the Anthropic /messages endpoint."""
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": config.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": config.num_ctx,
        "system": sys_prompt,
        "messages": [
            {"role": "user", "content": user_prompt},
        ],
        "temperature": config.temperature,
    }

    for attempt in range(config.max_retries):
        try:
            logger.debug("Anthropic request attempt %d/%d", attempt + 1, config.max_retries)
            response = requests.post(url, json=payload, headers=headers, timeout=120)
            response.raise_for_status()
            data = response.json()
            content_blocks = data.get("content", [])
            texts = [b["text"] for b in content_blocks if b.get("type") == "text"]
            return " ".join(texts)
        except (requests.RequestException, ValueError, KeyError) as e:
            if attempt == config.max_retries - 1:
                raise e
            logger.warning("Anthropic request failed (attempt %d/%d): %s", attempt + 1, config.max_retries, e)
            time.sleep(config.retry_delay_secs)

    return ""


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

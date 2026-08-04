# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for llm_client module using mocked harness responses."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

import artifice_draft.llm_edit as llm_edit_module
from artifice_draft.llm_client import (
    LLMEdit,
    _map_response_to_batch_edits,
    call_ollama,
)
from artifice_draft.llm_utils import _compute_dynamic_batch_sizes, _estimate_tokens
from artifice_draft.prompts import get_system_prompt, list_styles
from artifice_draft.config import AppConfig
from artifice_draft.models import EditingStyle, LLMProvider, PipelineProgress

from model_harness.contract import (
    HarnessResult,
    StructuredOutputMode,
    StructuredOutputUnsupported,
)
from artifice_draft.llm_edit import _DraftEditEntry, _DraftEditsShape


# -- Helper -----------------------------------------------------------------

def _harness_result(*entries: _DraftEditEntry) -> HarnessResult[_DraftEditsShape]:
    """Build a :class:`HarnessResult` with the given edit entries."""
    return HarnessResult(
        data=_DraftEditsShape(edits=list(entries)),
        mode_used=StructuredOutputMode.JSON_OBJECT,
        model="test-model",
        raw=json.dumps([e.model_dump(exclude_none=True) for e in entries]),
        repaired=False,
    )


def _as_llm_edits(*entries: _DraftEditEntry, batch: list[dict], batch_start: int = 0) -> list[LLMEdit]:
    """Convert entries to dicts and map through ``_map_response_to_batch_edits``."""
    dict_entries = [e.model_dump(exclude_none=True) for e in entries]
    return _map_response_to_batch_edits(dict_entries, batch, batch_start)


# -- call_ollama (harness-mocked) --------------------------------------------

def test_call_ollama_with_mocked_response():
    """``call_ollama`` returns correct ``LLMEdit`` objects when the harness succeeds."""
    paragraphs = [
        {"text": "Hello world", "paragraph_index": 0},
        {"text": "Second paragraph", "paragraph_index": 1},
    ]
    harness_result = _harness_result(
        _DraftEditEntry(paragraph_index=0, edited_text="Hello everyone", status="edited"),
        _DraftEditEntry(paragraph_index=1, edited_text=None, status="unchanged"),
    )

    with patch("artifice_draft.llm_client.run_structured", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = harness_result
        edits = call_ollama(paragraphs=paragraphs, batch_size=2)

    assert len(edits) == 2
    assert edits[0].paragraph_index == 0
    assert edits[0].edited_text == "Hello everyone"
    assert edits[1].paragraph_index == 1
    assert edits[1].edited_text is None


def test_call_ollama_with_invalid_json_falls_back():
    """When the harness raises ``StructuredOutputUnsupported``, every paragraph is
    marked unchanged — the same graceful-degradation behaviour the old scraper
    provided."""
    with patch("artifice_draft.llm_client.run_structured", new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = StructuredOutputUnsupported("no structured output")
        edits = call_ollama(paragraphs=[
            {"text": "Hello world", "paragraph_index": 0},
            {"text": "Second paragraph", "paragraph_index": 1},
        ], batch_size=2)

    assert len(edits) == 2
    for e in edits:
        assert e.status == "unchanged"
        assert e.edited_text is None


def test_call_ollama_harness_error_falls_back():
    """A general harness error also triggers the unchanged fallback."""
    with patch("artifice_draft.llm_client.run_structured", new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = RuntimeError("unexpected transport failure")
        edits = call_ollama(paragraphs=[
            {"text": "Test", "paragraph_index": 0},
        ], batch_size=1)

    assert len(edits) == 1
    assert edits[0].status == "unchanged"


# -- _map_response_to_batch_edits -------------------------------------------

def test_map_response_positional_fallback():
    """If an entry's paragraph_index is in range but does not match any batch
    paragraph's stored index, the function falls back to positional lookup."""
    batch = [{"text": "Original text", "paragraph_index": 10}]
    entry = _DraftEditEntry(paragraph_index=5, edited_text="Edited", status="edited")

    edits = _as_llm_edits(entry, batch=batch, batch_start=5)

    assert len(edits) == 1
    assert edits[0].paragraph_index == 5
    assert edits[0].original_text == "Original text"
    assert edits[0].edited_text == "Edited"


def test_map_response_missing_index_uses_batch_start():
    """An entry with no paragraph_index defaults to batch_start and matches positionally."""
    batch = [{"text": "Original text", "paragraph_index": 2}]
    entry = _DraftEditEntry(edited_text="Edited", status="edited")

    edits = _as_llm_edits(entry, batch=batch, batch_start=0)

    assert len(edits) == 1
    assert edits[0].paragraph_index == 0
    assert edits[0].original_text == "Original text"


def test_map_response_out_of_range_index_discarded():
    """Entries entirely outside the batch range are discarded."""
    batch = [{"text": "Hello world", "paragraph_index": 0}]
    entries = [
        _DraftEditEntry(paragraph_index=999, edited_text="Out of range", status="edited"),
        _DraftEditEntry(paragraph_index=0, edited_text="In range", status="edited"),
    ]

    edits = _as_llm_edits(*entries, batch=batch, batch_start=0)

    assert len(edits) == 1
    assert edits[0].paragraph_index == 0
    assert edits[0].edited_text == "In range"


# -- call_ollama edge cases -------------------------------------------------

def test_call_ollama_returns_empty_for_none():
    assert call_ollama(paragraphs=None) == []


def test_call_ollama_with_progress_callback():
    progress_updates = []

    def on_progress(p):
        progress_updates.append(p.percentage)

    harness_result = _harness_result(
        _DraftEditEntry(paragraph_index=0, edited_text="Fixed", status="edited"),
    )

    with patch("artifice_draft.llm_client.run_structured", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = harness_result
        edits = call_ollama(
            paragraphs=[{"text": "Hello world", "paragraph_index": 0}],
            batch_size=1,
            on_progress=on_progress,
        )

    assert len(edits) == 1
    assert len(progress_updates) > 0


def test_call_ollama_empty_paragraphs():
    assert call_ollama(paragraphs=[], batch_size=2) == []


# -- System prompts ---------------------------------------------------------

def test_get_system_prompt():
    prompt = get_system_prompt()
    assert "grammar" in prompt.lower() or "Grammar" in prompt
    assert "JSON" in prompt or "json" in prompt


def test_get_system_prompt_styles():
    for style_name in list_styles():
        style = EditingStyle(style_name)
        prompt = get_system_prompt(style=style)
        assert len(prompt) > 50


def test_get_system_prompt_custom():
    custom = "You are a pirate editor. Fix grammar, matey!"
    prompt = get_system_prompt(style=EditingStyle.CUSTOM, custom_prompt=custom)
    assert "pirate" in prompt


def test_get_system_prompt_custom_fallback():
    prompt = get_system_prompt(style=EditingStyle.CUSTOM, custom_prompt="")
    assert "grammar" in prompt.lower() or "Grammar" in prompt


# -- build_user_prompt (via llm_utils) ---------------------------------------

def test_build_user_prompt():
    from artifice_draft.llm_utils import build_user_prompt

    paragraphs = [
        {"text": "Hello world", "style_name": "Normal", "is_bold": False, "is_italic": False},
        {"text": "Second paragraph", "style_name": "Heading 1", "is_bold": True, "is_italic": False},
    ]
    prompt = build_user_prompt(paragraphs)
    assert "2 paragraphs" in prompt
    assert "Hello world" in prompt
    assert "Second paragraph" in prompt


def test_build_user_prompt_empty():
    from artifice_draft.llm_utils import build_user_prompt
    assert build_user_prompt([]) == "[]"


# -- LLMEdit ----------------------------------------------------------------

def test_llm_edit_is_changed():
    e1 = LLMEdit(paragraph_index=0, original_text="Hello", edited_text="Hi", status="edited")
    assert e1.is_changed() is True

    e2 = LLMEdit(paragraph_index=0, original_text="Hello", edited_text="Hello", status="unchanged")
    assert e2.is_changed() is False

    e3 = LLMEdit(paragraph_index=0, original_text="Hello", edited_text=None, status="unchanged")
    assert e3.is_changed() is False


def test_to_edits_dict():
    edits = [
        LLMEdit(paragraph_index=0, edited_text="A", status="edited"),
        LLMEdit(paragraph_index=1, edited_text=None, status="unchanged"),
        LLMEdit(paragraph_index=2, edited_text="C", status="edited"),
    ]
    d = LLMEdit.to_edits_dict(edits)
    assert d == {0: "A", 1: None, 2: "C"}


def test_llm_edit_reexport_identity():
    """LLMEdit imported from llm_client must be the exact class object defined in llm_edit."""
    import artifice_draft.llm_client as llm_client_module

    assert llm_client_module.LLMEdit is llm_edit_module.LLMEdit
    edit = LLMEdit(paragraph_index=0, original_text="Hello", edited_text="Hi", status="edited")
    assert isinstance(edit, llm_edit_module.LLMEdit)


# -- Config -----------------------------------------------------------------

def test_config_active_model_ollama():
    cfg = AppConfig(llm_provider=LLMProvider.OLLAMA, ollama_model="test-model")
    assert cfg.ollama_model == "test-model"
    assert cfg.active_model == "test-model"


def test_config_active_model_openai():
    cfg = AppConfig(llm_provider=LLMProvider.OPENAI, openai_model="gpt-4o")
    assert cfg.openai_model == "gpt-4o"
    assert cfg.active_model == "gpt-4o"


def test_config_active_model_anthropic():
    cfg = AppConfig(llm_provider=LLMProvider.ANTHROPIC, anthropic_model="claude-3")
    assert cfg.anthropic_model == "claude-3"
    assert cfg.active_model == "claude-3"


# -- Progress tracking ------------------------------------------------------

def test_progress_tracking():
    p = PipelineProgress(total_paragraphs=10)
    p.update("llm_processing", 5, "Processing...")
    assert p.percentage == 50.0
    p.finish("Done")
    assert p.percentage == 100.0
    assert p.stage == "done"


def test_progress_tracking_fail():
    p = PipelineProgress(total_paragraphs=10)
    p.fail("Something broke")
    assert p.error == "Something broke"
    assert p.stage == "error"


# -- Token estimation & batch sizing ----------------------------------------

def test_estimate_tokens():
    """Token estimation is plain ceiling division by _CHARS_PER_TOKEN."""
    from artifice_draft.llm_utils import _CHARS_PER_TOKEN

    assert _estimate_tokens("") == 0
    assert _estimate_tokens("a" * _CHARS_PER_TOKEN) == 1
    assert _estimate_tokens("a" * (_CHARS_PER_TOKEN + 1)) == 2
    assert _estimate_tokens("a" * (_CHARS_PER_TOKEN * 3)) == 3


def test_dynamic_batch_sizes_small():
    paragraphs = [
        {"text": "Short", "paragraph_index": 0},
        {"text": "Also short", "paragraph_index": 1},
    ]
    batches = _compute_dynamic_batch_sizes(paragraphs, max_batch_size=10, max_tokens=8192)
    assert len(batches) == 1
    assert len(batches[0]) == 2


def test_dynamic_batch_sizes_token_limit():
    long_text = "word " * 500
    paragraphs = [
        {"text": long_text, "paragraph_index": 0},
        {"text": long_text, "paragraph_index": 1},
    ]
    batches = _compute_dynamic_batch_sizes(paragraphs, max_batch_size=10, max_tokens=1000)
    assert len(batches) == 2


def test_dynamic_batch_sizes_empty():
    batches = _compute_dynamic_batch_sizes([], max_batch_size=5, max_tokens=8192)
    assert batches == []


def test_dynamic_batch_sizes_respects_max_batch_size():
    paragraphs = [{"text": "x", "paragraph_index": i} for i in range(5)]
    batches = _compute_dynamic_batch_sizes(paragraphs, max_batch_size=2, max_tokens=8192)
    assert len(batches) == 3
    assert [len(b) for b in batches] == [2, 2, 1]


# -- Harness integration tests ----------------------------------------------

def test_harness_result_shape_valid():
    """A properly-shaped ``HarnessResult`` can be constructed and its data accessed."""
    shape = _DraftEditsShape(edits=[
        _DraftEditEntry(paragraph_index=0, edited_text="Fixed", status="edited"),
    ])
    result = HarnessResult(
        data=shape,
        mode_used=StructuredOutputMode.JSON_OBJECT,
        model="test-model",
        raw='{"edits":[{"paragraph_index":0,"edited_text":"Fixed","status":"edited"}]}',
        repaired=False,
    )
    assert result.mode_used == StructuredOutputMode.JSON_OBJECT
    assert result.repaired is False
    assert len(result.data.edits) == 1
    assert result.data.edits[0].paragraph_index == 0


def test_harness_wire_schema_matches_mock_response():
    """The wire schema validates the JSON shape the mock tests historically used,
    after wrapping in the ``edits`` key."""
    raw_json = json.dumps({"edits": [
        {"paragraph_index": 0, "edited_text": "Hello everyone", "status": "edited"},
        {"paragraph_index": 1, "edited_text": None, "status": "unchanged"},
    ]})
    parsed = json.loads(raw_json)
    shape = _DraftEditsShape.model_validate(parsed)
    assert len(shape.edits) == 2
    assert shape.edits[0].edited_text == "Hello everyone"
    assert shape.edits[1].edited_text is None


def test_runtime_error_on_nested_event_loop_rewraps():
    """If call_ollama is invoked from a running event loop, the RuntimeError is
    re-raised with an actionable message."""
    with patch("artifice_draft.llm_client.asyncio.run") as mock_run:
        mock_run.side_effect = RuntimeError("cannot be called from a running event loop")
        try:
            call_ollama(paragraphs=[{"text": "Test", "paragraph_index": 0}])
            assert False, "should have raised"
        except RuntimeError as exc:
            assert "running asyncio event loop" in str(exc)


def test_schema_json_is_usable():
    """``model_json_schema()`` returns a real JSON schema dict."""
    schema = _DraftEditsShape.model_json_schema()
    assert isinstance(schema, dict)
    assert "properties" in schema
    assert "edits" in schema["properties"]


# -- Adapter construction coverage ------------------------------------------

def test_build_adapter_ollama():
    """_build_adapter returns OpenAIProvider for Ollama config."""
    from artifice_draft.llm_client import _build_adapter
    from model_harness.openai_adapter import OpenAIProvider

    cfg = AppConfig(llm_provider=LLMProvider.OLLAMA)
    adapter = _build_adapter(cfg)
    assert isinstance(adapter, OpenAIProvider)


def test_build_adapter_openai():
    """_build_adapter returns OpenAIProvider for OpenAI config."""
    from artifice_draft.llm_client import _build_adapter
    from model_harness.openai_adapter import OpenAIProvider

    cfg = AppConfig(llm_provider=LLMProvider.OPENAI)
    adapter = _build_adapter(cfg)
    assert isinstance(adapter, OpenAIProvider)


def test_build_adapter_anthropic():
    """_build_adapter returns AnthropicProvider for Anthropic config."""
    from artifice_draft.llm_client import _build_adapter
    from model_harness.anthropic_adapter import AnthropicProvider

    cfg = AppConfig(llm_provider=LLMProvider.ANTHROPIC)
    adapter = _build_adapter(cfg)
    assert isinstance(adapter, AnthropicProvider)


# -- Endpoint mapping coverage ----------------------------------------------

def test_provider_str_ollama():
    from artifice_draft.llm_client import _provider_str

    cfg = AppConfig(llm_provider=LLMProvider.OLLAMA)
    assert _provider_str(cfg) == "ollama"


def test_provider_str_openai():
    from artifice_draft.llm_client import _provider_str

    cfg = AppConfig(llm_provider=LLMProvider.OPENAI)
    assert _provider_str(cfg) == "generic-api"


def test_provider_str_anthropic():
    from artifice_draft.llm_client import _provider_str

    cfg = AppConfig(llm_provider=LLMProvider.ANTHROPIC)
    assert _provider_str(cfg) == "anthropic"


def test_endpoint_for_ollama():
    from artifice_draft.llm_client import _endpoint_for

    cfg = AppConfig(llm_provider=LLMProvider.OLLAMA, base_url="http://localhost:11434/v1")
    assert _endpoint_for(cfg) == "http://localhost:11434/v1"  # adapter appends /chat/completions


def test_endpoint_for_openai():
    from artifice_draft.llm_client import _endpoint_for

    cfg = AppConfig(llm_provider=LLMProvider.OPENAI, openai_base_url="https://api.openai.com/v1")
    assert _endpoint_for(cfg) == "https://api.openai.com/v1"


def test_endpoint_for_anthropic():
    from artifice_draft.llm_client import _endpoint_for

    cfg = AppConfig(llm_provider=LLMProvider.ANTHROPIC)
    assert _endpoint_for(cfg) == "https://api.anthropic.com"


# ---------------------------------------------------------------------------
# Endpoint policy: model discovery (now delegated to model_harness.discovery)
#
# The get_available_models and test_connection functions were removed from
# llm_client.py — they were dead code with no route exposing them.  Model
# discovery is now handled by model_harness.discovery.probe_endpoint.
# ---------------------------------------------------------------------------

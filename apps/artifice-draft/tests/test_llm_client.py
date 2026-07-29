"""Tests for llm_client module using mocked Ollama responses."""

from __future__ import annotations

import json
from unittest.mock import patch

import artifice_draft.llm_edit as llm_edit_module
from artifice_draft.llm_client import (
    LLMEdit,
    _parse_llm_response,
    _recover_json_from_response,
    _send_request_with_retry,
    _compute_dynamic_batch_sizes,
    build_user_prompt,
    call_ollama,
)
from artifice_draft.llm_utils import _estimate_tokens
from artifice_draft.prompts import get_system_prompt, list_styles
from artifice_draft.config import AppConfig
from artifice_draft.models import EditingStyle, LLMProvider, PipelineProgress


def test_call_ollama_with_mocked_response():
    mock_response = [
        {"paragraph_index": 0, "edited_text": "Hello everyone", "status": "edited"},
        {"paragraph_index": 1, "edited_text": None, "status": "unchanged"},
    ]

    with patch("artifice_draft.llm_client._send_request_with_retry", return_value=json.dumps(mock_response)):
        edits = call_ollama(paragraphs=[
            {"text": "Hello world", "paragraph_index": 0},
            {"text": "Second paragraph", "paragraph_index": 1},
        ], batch_size=2)

    assert len(edits) == 2
    assert edits[0].paragraph_index == 0
    assert edits[0].edited_text == "Hello everyone"
    assert edits[1].paragraph_index == 1
    assert edits[1].edited_text is None


def test_call_ollama_with_invalid_json_falls_back():
    with patch("artifice_draft.llm_client._send_request_with_retry", return_value="This is not valid JSON at all!"):
        edits = call_ollama(paragraphs=[
            {"text": "Hello world", "paragraph_index": 0},
            {"text": "Second paragraph", "paragraph_index": 1},
        ], batch_size=2)

    assert len(edits) == 2
    for e in edits:
        assert e.status == "unchanged"


def test_call_ollama_single_object_fallback():
    mock_response = {"paragraph_index": 0, "edited_text": "Fixed", "status": "edited"}

    with patch("artifice_draft.llm_client._send_request_with_retry", return_value=json.dumps(mock_response)):
        edits = call_ollama(paragraphs=[{"text": "Hello world", "paragraph_index": 0}], batch_size=1)

    assert len(edits) == 1
    assert edits[0].paragraph_index == 0


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


def test_build_user_prompt():
    paragraphs = [
        {"text": "Hello world", "style_name": "Normal", "is_bold": False, "is_italic": False},
        {"text": "Second paragraph", "style_name": "Heading 1", "is_bold": True, "is_italic": False},
    ]
    prompt = build_user_prompt(paragraphs)
    assert "2 paragraphs" in prompt
    assert "Hello world" in prompt
    assert "Second paragraph" in prompt


def test_build_user_prompt_empty():
    assert build_user_prompt([]) == "[]"


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


def test_call_ollama_returns_empty_for_none():
    assert call_ollama(paragraphs=None) == []


def test_call_ollama_out_of_range_index_discarded():
    mock_response = [
        {"paragraph_index": 999, "edited_text": "Out of range", "status": "edited"},
        {"paragraph_index": 0, "edited_text": "In range", "status": "edited"},
    ]

    with patch("artifice_draft.llm_client._send_request_with_retry", return_value=json.dumps(mock_response)):
        edits = call_ollama(paragraphs=[
            {"text": "Hello world", "paragraph_index": 0},
        ], batch_size=1)

    assert len(edits) == 1
    assert edits[0].paragraph_index == 0
    assert edits[0].edited_text == "In range"


def test_retry_raises_on_final_failure():
    import requests

    cfg = AppConfig(max_retries=1, retry_delay_secs=0)

    with patch("artifice_draft.llm_client.requests.post") as mock_post:
        mock_post.side_effect = requests.ConnectionError("connection refused")
        try:
            _send_request_with_retry("model", "sys", "user", cfg)
            assert False, "Should have raised"
        except requests.ConnectionError:
            pass


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


def test_call_ollama_with_progress_callback():
    mock_response = [
        {"paragraph_index": 0, "edited_text": "Fixed", "status": "edited"},
    ]
    progress_updates = []

    def on_progress(p):
        progress_updates.append(p.percentage)

    with patch("artifice_draft.llm_client._send_request_with_retry", return_value=json.dumps(mock_response)):
        edits = call_ollama(
            paragraphs=[{"text": "Hello world", "paragraph_index": 0}],
            batch_size=1,
            on_progress=on_progress,
        )

    assert len(edits) == 1
    assert len(progress_updates) > 0


def test_parse_llm_response_positional_fallback():
    """If an entry's paragraph_index is in range but does not match any batch
    paragraph's stored index, _parse_llm_response falls back to positional lookup.
    """
    batch = [{"text": "Original text", "paragraph_index": 10}]
    raw_response = json.dumps([{"paragraph_index": 5, "edited_text": "Edited", "status": "edited"}])

    edits = _parse_llm_response(raw_response, batch, batch_start=5)

    assert len(edits) == 1
    assert edits[0].paragraph_index == 5
    assert edits[0].original_text == "Original text"
    assert edits[0].edited_text == "Edited"


def test_parse_llm_response_missing_index_uses_batch_start():
    """An entry with no paragraph_index defaults to batch_start and matches positionally."""
    batch = [{"text": "Original text", "paragraph_index": 2}]
    raw_response = json.dumps([{"edited_text": "Edited", "status": "edited"}])

    edits = _parse_llm_response(raw_response, batch, batch_start=0)

    assert len(edits) == 1
    assert edits[0].paragraph_index == 0
    assert edits[0].original_text == "Original text"


def test_recover_json_from_response_wraps_single_object():
    raw = json.dumps({"paragraph_index": 0, "edited_text": "Fixed", "status": "edited"})
    result = _recover_json_from_response(raw)
    assert result == [{"paragraph_index": 0, "edited_text": "Fixed", "status": "edited"}]


def test_recover_json_from_response_preserves_list():
    raw = json.dumps([{"paragraph_index": 0, "edited_text": "Fixed", "status": "edited"}])
    result = _recover_json_from_response(raw)
    assert result == [{"paragraph_index": 0, "edited_text": "Fixed", "status": "edited"}]


def test_llm_edit_reexport_identity():
    """LLMEdit imported from llm_client must be the exact class object defined in llm_edit."""
    import artifice_draft.llm_client as llm_client_module

    assert llm_client_module.LLMEdit is llm_edit_module.LLMEdit
    edit = LLMEdit(paragraph_index=0, original_text="Hello", edited_text="Hi", status="edited")
    assert isinstance(edit, llm_edit_module.LLMEdit)


def test_estimate_tokens():
    """Token estimation is plain ceiling division by _CHARS_PER_TOKEN."""
    from artifice_draft.llm_utils import _CHARS_PER_TOKEN

    assert _estimate_tokens("") == 0
    assert _estimate_tokens("a" * _CHARS_PER_TOKEN) == 1
    assert _estimate_tokens("a" * (_CHARS_PER_TOKEN + 1)) == 2
    assert _estimate_tokens("a" * (_CHARS_PER_TOKEN * 3)) == 3


def test_dynamic_batch_sizes_respects_max_batch_size():
    paragraphs = [{"text": "x", "paragraph_index": i} for i in range(5)]
    batches = _compute_dynamic_batch_sizes(paragraphs, max_batch_size=2, max_tokens=8192)
    assert len(batches) == 3
    assert [len(b) for b in batches] == [2, 2, 1]

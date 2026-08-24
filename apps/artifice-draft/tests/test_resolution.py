# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for artifice-draft's once-per-run model resolution.

The config ships an empty ``model_name``; these cover what fills it in, and
what happens when it cannot be filled.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from artifice_draft._resolution import resolve_for_run
from artifice_draft.config import AppConfig
from artifice_draft.models import LLMProvider


class _Probe:
    """Stand-in for model_harness.discovery.ProbeResult."""

    def __init__(self, reachable: bool, models: list[str], url: str = "http://localhost:11434"):
        self.reachable = reachable
        self.models = models
        self.url = url


def _patch_probe(probe: _Probe):
    return patch("artifice_draft._resolution.probe_endpoint_sync", return_value=probe)


# ---------------------------------------------------------------------------
# __post_init__ — the sentinel rewrite
# ---------------------------------------------------------------------------


def test_post_init_propagates_ollama_model_when_model_name_unset():
    """The regression the literal-as-sentinel rewrite could have caused.

    __post_init__ used to test `model_name == "gemma4:12b"`. Once the defaults
    became empty that comparison was always False, so the provider-specific
    value would have silently stopped propagating. Nothing else covers this.
    """
    cfg = AppConfig(llm_provider=LLMProvider.OLLAMA, ollama_model="llama3.2:3b")
    assert cfg.model_name == "llama3.2:3b"


def test_post_init_leaves_explicit_model_name_alone():
    cfg = AppConfig(
        llm_provider=LLMProvider.OLLAMA,
        model_name="mistral:7b",
        ollama_model="llama3.2:3b",
    )
    assert cfg.model_name == "mistral:7b"


def test_post_init_propagates_openai_model():
    cfg = AppConfig(llm_provider=LLMProvider.OPENAI)
    assert cfg.model_name == "gpt-4o"


def test_defaults_are_empty_not_a_named_model():
    """The shipped default must not name a model the user may not have."""
    cfg = AppConfig(llm_provider=LLMProvider.OLLAMA, ollama_model="")
    assert cfg.model_name == ""
    assert cfg.ollama_model == ""


# ---------------------------------------------------------------------------
# resolve_for_run
# ---------------------------------------------------------------------------


def test_explicit_installed_model_is_kept():
    cfg = AppConfig(llm_provider=LLMProvider.OLLAMA, model_name="mistral:7b")
    with _patch_probe(_Probe(True, ["mistral:7b", "llama3.2:3b"])):
        resolve_for_run(cfg)
    assert cfg.model_name == "mistral:7b"


def test_empty_default_resolves_from_installed():
    cfg = AppConfig(llm_provider=LLMProvider.OLLAMA, ollama_model="")
    assert cfg.model_name == ""
    with _patch_probe(_Probe(True, ["llama3.2:3b"])):
        resolve_for_run(cfg)
    assert cfg.model_name == "llama3.2:3b"
    # written back to both fields so active_model agrees whichever it reads
    assert cfg.ollama_model == "llama3.2:3b"


def test_configured_but_missing_names_the_model_and_does_not_substitute():
    """A chosen model that is absent must fail, not silently become another."""
    cfg = AppConfig(llm_provider=LLMProvider.OLLAMA, model_name="gemma4:12b")
    with _patch_probe(_Probe(True, ["llama3.2:3b"])), pytest.raises(RuntimeError) as exc:
        resolve_for_run(cfg)
    msg = str(exc.value)
    assert "gemma4:12b" in msg
    assert "not installed" in msg
    assert "llama3.2:3b" not in msg  # never quietly offered as a substitute


def test_nothing_installed_gives_a_distinct_message():
    """Different remedy from configured_but_missing, so different wording."""
    cfg = AppConfig(llm_provider=LLMProvider.OLLAMA, ollama_model="")
    with _patch_probe(_Probe(True, [])), pytest.raises(RuntimeError) as exc:
        resolve_for_run(cfg)
    msg = str(exc.value)
    assert "No suitable model" in msg
    assert "not installed on" not in msg


def test_unreachable_endpoint_says_so_and_names_the_url():
    cfg = AppConfig(llm_provider=LLMProvider.OLLAMA, ollama_base_url="http://localhost:9999")
    with _patch_probe(_Probe(False, [])), pytest.raises(RuntimeError) as exc:
        resolve_for_run(cfg)
    msg = str(exc.value)
    assert "Cannot reach Ollama" in msg
    assert "http://localhost:9999" in msg


def test_non_ollama_provider_is_left_untouched():
    """OpenAI and Anthropic name models from a catalogue, not a local shelf."""
    cfg = AppConfig(llm_provider=LLMProvider.OPENAI)
    before = cfg.model_name
    with patch("artifice_draft._resolution.probe_endpoint_sync") as probe:
        resolve_for_run(cfg)
    probe.assert_not_called()
    assert cfg.model_name == before


def test_resolution_is_idempotent():
    cfg = AppConfig(llm_provider=LLMProvider.OLLAMA, ollama_model="")
    with _patch_probe(_Probe(True, ["llama3.2:3b"])):
        resolve_for_run(cfg)
        first = cfg.model_name
        resolve_for_run(cfg)
    assert cfg.model_name == first

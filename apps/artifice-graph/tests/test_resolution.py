# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for artifice-graph's once-per-run model resolution.

Graph carries two roles on potentially two endpoints, and — unlike ocr and
draft — has no in-app model picker, so "nothing has ever been chosen" is its
normal state rather than an edge case.
"""

from __future__ import annotations

import pytest
from artifice_graph._resolution import resolve_for_run
from artifice_graph.config import EmbeddingConfig, LLMConfig, PipelineConfig


class _Probe:
    """Stand-in for model_harness.discovery.ProbeResult."""

    def __init__(self, reachable: bool, models: list[str]):
        self.reachable = reachable
        self.models = models


def _patch_probe(monkeypatch, by_url: dict[str, _Probe]):
    """Probe each URL independently — graph's two roles may differ."""

    def _fake(url, *, policy, timeout_s):  # noqa: ARG001
        return by_url[url]

    monkeypatch.setattr("artifice_graph._resolution.probe_endpoint_sync", _fake)


def _cfg(llm_model: str = "", embedding_model: str = "") -> PipelineConfig:
    return PipelineConfig(
        llm=LLMConfig(model=llm_model),
        embedding=EmbeddingConfig(model=embedding_model),
    )


LLM_URL = "http://localhost:11434/v1"
EMB_URL = "http://localhost:11434"


def test_defaults_are_empty_not_named_models():
    """The shipped defaults must not name models the user may not have."""
    cfg = _cfg()
    assert cfg.llm.model == ""
    assert cfg.embedding.model == ""


def test_both_roles_resolve_from_installed(monkeypatch):
    _patch_probe(
        monkeypatch,
        {
            LLM_URL: _Probe(True, ["llama3.2:3b", "nomic-embed-text"]),
            EMB_URL: _Probe(True, ["llama3.2:3b", "nomic-embed-text"]),
        },
    )
    cfg = _cfg()
    resolve_for_run(cfg)
    assert cfg.llm.model == "llama3.2:3b"
    # The embedding role must pick the embedding model, not the first installed.
    assert cfg.embedding.model == "nomic-embed-text"


def test_explicit_installed_models_are_kept(monkeypatch):
    _patch_probe(
        monkeypatch,
        {
            LLM_URL: _Probe(True, ["mistral:7b", "llama3.2:3b"]),
            EMB_URL: _Probe(True, ["nomic-embed-text"]),
        },
    )
    cfg = _cfg(llm_model="mistral:7b", embedding_model="nomic-embed-text")
    resolve_for_run(cfg)
    assert cfg.llm.model == "mistral:7b"
    assert cfg.embedding.model == "nomic-embed-text"


def test_configured_but_missing_names_it_and_does_not_substitute(monkeypatch):
    _patch_probe(
        monkeypatch,
        {
            LLM_URL: _Probe(True, ["llama3.2:3b"]),
            EMB_URL: _Probe(True, ["nomic-embed-text"]),
        },
    )
    cfg = _cfg(llm_model="gemma2:27b")
    with pytest.raises(RuntimeError) as exc:
        resolve_for_run(cfg)
    msg = str(exc.value)
    assert "gemma2:27b" in msg
    assert "not installed" in msg


def test_embedding_role_never_falls_back_to_a_chat_model(monkeypatch):
    """A chat model in the embedding slot would produce silent nonsense."""
    _patch_probe(
        monkeypatch,
        {
            LLM_URL: _Probe(True, ["llama3.2:3b"]),
            EMB_URL: _Probe(True, ["llama3.2:3b"]),  # no embedding model present
        },
    )
    cfg = _cfg()
    with pytest.raises(RuntimeError) as exc:
        resolve_for_run(cfg)
    msg = str(exc.value)
    assert "embedding" in msg
    assert "llama3.2:3b" not in msg


def test_unreachable_endpoint_names_the_url(monkeypatch):
    _patch_probe(monkeypatch, {LLM_URL: _Probe(False, [])})
    cfg = _cfg()
    with pytest.raises(RuntimeError) as exc:
        resolve_for_run(cfg)
    msg = str(exc.value)
    assert "Cannot reach" in msg
    assert LLM_URL in msg


def test_roles_probe_their_own_endpoints(monkeypatch):
    """Graph's two roles carry separate base_urls; each must use its own."""
    seen: list[str] = []

    def _fake(url, *, policy, timeout_s):  # noqa: ARG001
        seen.append(url)
        return _Probe(True, ["llama3.2:3b", "nomic-embed-text"])

    monkeypatch.setattr("artifice_graph._resolution.probe_endpoint_sync", _fake)
    cfg = PipelineConfig(
        llm=LLMConfig(base_url="http://localhost:1111/v1"),
        embedding=EmbeddingConfig(base_url="http://localhost:2222"),
    )
    resolve_for_run(cfg)
    assert seen == ["http://localhost:1111/v1", "http://localhost:2222"]


def test_resolution_is_idempotent(monkeypatch):
    _patch_probe(
        monkeypatch,
        {
            LLM_URL: _Probe(True, ["llama3.2:3b"]),
            EMB_URL: _Probe(True, ["nomic-embed-text"]),
        },
    )
    cfg = _cfg()
    resolve_for_run(cfg)
    first = (cfg.llm.model, cfg.embedding.model)
    resolve_for_run(cfg)
    assert (cfg.llm.model, cfg.embedding.model) == first

# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for BGEM3Embedder endpoint policy enforcement."""

from __future__ import annotations

import pytest

from artifice_graph.config import EmbeddingConfig
from model_harness.contract import EndpointRejected


# ---------------------------------------------------------------------------
# Endpoint policy: constructor validates base_url
# ---------------------------------------------------------------------------


def test_embedder_rejects_link_local():
    """Construction with a link-local URL raises EndpointRejected."""
    config = EmbeddingConfig(base_url="http://169.254.169.254")
    with pytest.raises(EndpointRejected, match="link-local"):
        from artifice_graph.embedding.bge_embedder import BGEM3Embedder
        BGEM3Embedder(config=config)


def test_embedder_accepts_localhost():
    """Construction with a localhost URL succeeds."""
    from artifice_graph.embedding.bge_embedder import BGEM3Embedder
    config = EmbeddingConfig(base_url="http://localhost:11434")
    embedder = BGEM3Embedder(config=config)
    assert embedder.config.base_url == "http://localhost:11434"


def test_embedder_rejects_public_by_default():
    """A public IP is refused without ARTIFICE_ALLOW_PUBLIC_MODELS."""
    config = EmbeddingConfig(base_url="http://8.8.8.8")
    with pytest.raises(EndpointRejected, match="public address"):
        from artifice_graph.embedding.bge_embedder import BGEM3Embedder
        BGEM3Embedder(config=config)


def test_embedder_accepts_public_with_allow(monkeypatch):
    """A public IP is accepted when the policy permits public endpoints."""
    monkeypatch.setenv("ARTIFICE_ALLOW_PUBLIC_MODELS", "1")
    from artifice_graph.embedding.bge_embedder import BGEM3Embedder
    config = EmbeddingConfig(base_url="http://8.8.8.8")
    embedder = BGEM3Embedder(config=config)
    assert "8.8.8.8" in embedder.config.base_url

# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

"""Tests for InferenceEngine endpoint policy enforcement."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from artifice_graph.extraction.inference_engine import InferenceEngine
from model_harness.contract import EndpointRejected


# ---------------------------------------------------------------------------
# Endpoint policy: constructor validates base_url
# ---------------------------------------------------------------------------


def test_inference_engine_rejects_link_local():
    """Construction with a link-local URL raises EndpointRejected."""
    with pytest.raises(EndpointRejected, match="link-local"):
        InferenceEngine(base_url="http://169.254.169.254/v1")


def test_inference_engine_accepts_localhost():
    """Construction with a localhost URL succeeds."""
    engine = InferenceEngine(base_url="http://localhost:11434")
    assert engine.base_url == "http://localhost:11434/v1"


def test_inference_engine_accepts_wsl_gateway():
    """The WSL gateway address (default always-allowed) passes validation."""
    engine = InferenceEngine(base_url="http://172.21.176.1:11434/v1")
    assert "172.21.176.1" in engine.base_url


def test_inference_engine_rejects_public_by_default():
    """A public IP is refused without ARTIFICE_ALLOW_PUBLIC_MODELS."""
    with pytest.raises(EndpointRejected, match="public address"):
        InferenceEngine(base_url="http://8.8.8.8/v1")


def test_inference_engine_accepts_public_with_allow(monkeypatch):
    """A public IP is accepted when the policy permits public endpoints."""
    monkeypatch.setenv("ARTIFICE_ALLOW_PUBLIC_MODELS", "1")
    engine = InferenceEngine(base_url="http://8.8.8.8/v1")
    assert "8.8.8.8" in engine.base_url


# ---------------------------------------------------------------------------
# health_check and get_available_models do NOT follow redirects
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_check_does_not_follow_redirects():
    """health_check constructs an httpx.AsyncClient without follow_redirects."""
    engine = InferenceEngine(base_url="http://localhost:11434")

    with patch.object(httpx, "AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_get = AsyncMock()
        mock_get.status_code = 200
        mock_client.__aenter__.return_value.get.return_value = mock_get
        mock_client_cls.return_value = mock_client

        await engine.health_check()

        # Verify the client was constructed without follow_redirects
        call_kwargs = mock_client_cls.call_args
        assert call_kwargs is not None
        # follow_redirects should NOT be True (default is False)
        follow = call_kwargs.kwargs.get("follow_redirects", False)
        assert follow is False, (
            "health_check must not follow redirects — "
            f"got follow_redirects={follow!r}"
        )


@pytest.mark.asyncio
async def test_get_available_models_does_not_follow_redirects():
    """get_available_models constructs an httpx.AsyncClient without follow_redirects."""
    engine = InferenceEngine(base_url="http://localhost:11434")

    with patch.object(httpx, "AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        # First call: Ollama /api/tags returns a response
        mock_get_tags = AsyncMock()
        mock_get_tags.status_code = 200
        mock_get_tags.json.return_value = {"models": []}
        mock_client.__aenter__.return_value.get.return_value = mock_get_tags
        mock_client_cls.return_value = mock_client

        await engine.get_available_models()

        # Verify the client was constructed without follow_redirects
        call_kwargs = mock_client_cls.call_args
        assert call_kwargs is not None
        follow = call_kwargs.kwargs.get("follow_redirects", False)
        assert follow is False, (
            "get_available_models must not follow redirects — "
            f"got follow_redirects={follow!r}"
        )

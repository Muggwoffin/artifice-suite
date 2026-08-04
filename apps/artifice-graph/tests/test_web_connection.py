# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for /api/test-connection: the posted config body is what gets tested.

Bug 1 — the route was ``@app.get`` while the JS sent a POST (405).
Bug 2 — the handler called ``load_config()`` and ignored the posted body,
        so it tested the *saved* configuration even when the user typed a
        different URL into the form.
"""

from __future__ import annotations

import pytest
from pytest_httpx import HTTPXMock

# The test goes through the full FastAPI transport so that the route
# decorator, parameter binding and response serialisation are all tested.
import httpx
from artifice_graph.config import load_config
from artifice_graph.web.server import app

# Snapshot the runtime defaults so assertions don't drift when the
# environment or saved config differs.
_SAVED = load_config().llm


def _ollama_tags_url(base_url: str) -> str:
    """Mirror ``model_harness.discovery._strip_v1`` — the Ollama-native probe drops a /v1 suffix."""
    from model_harness.discovery import _strip_v1

    base = _strip_v1(base_url).rstrip("/")
    return f"{base}/api/tags"


def _openai_models_url(base_url: str) -> str:
    """Mirror ``discovery._probe_openai_models``' URL rule.

    It appends ``/models`` when the base already ends in ``/v1``, and
    ``/v1/models`` when it does not.

    Replicating the rule rather than assuming one shape is load-bearing:
    ``_SAVED`` comes from ``load_config()``, which reads ``~/.callosip/config.json``
    if the developer has one. On a machine where that file sets a base_url ending
    in ``/v1`` the old ``f"{base}/models"`` matched; in CI, which has no such file
    and falls back to config.yaml's ``http://localhost:11434``, the probe requests
    ``/v1/models`` and the mock never fired — so the test passed locally and failed
    on every CI platform.
    """
    base = base_url.rstrip("/")
    return f"{base}/models" if base.endswith("/v1") else f"{base}/v1/models"


@pytest.mark.asyncio
async def test_test_connection_is_post_not_get():
    """GET returns 405; POST is accepted (with mocked internals)."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        resp = await client.get("/api/test-connection")
        assert resp.status_code == 405, (
            f"GET /api/test-connection should return 405; got {resp.status_code}"
        )


@pytest.mark.asyncio
async def test_test_connection_uses_posted_url_and_model(httpx_mock: HTTPXMock):
    """A POST with a config body tests the posted values, not the saved ones."""
    # discovery.probe_endpoint calls /api/tags and /v1/models.
    # Mock both so the probe reports reachable.
    httpx_mock.add_response(
        url="http://localhost:12345/api/tags",
        method="GET",
        json={"models": [{"name": "test-model"}]},
    )
    httpx_mock.add_response(
        url="http://localhost:12345/v1/models",
        method="GET",
        json={"data": [{"id": "test-model"}]},
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as test_client:
        response = await test_client.post(
            "/api/test-connection",
            json={
                "llm_base_url": "http://localhost:12345",
                "llm_model": "posted-test-model",
            },
        )

    assert response.status_code == 200, (
        f"POST /api/test-connection should return 200; got {response.status_code}"
    )
    data = response.json()
    assert data["url"] == "http://localhost:12345", (
        f"Expected posted URL in response, got {data.get('url')!r}"
    )
    assert data["model"] == "posted-test-model", (
        f"Expected posted model in response, got {data.get('model')!r}"
    )
    assert data["status"] == "connected"


@pytest.mark.asyncio
async def test_test_connection_empty_body_falls_back_to_saved_config(
    httpx_mock: HTTPXMock,
):
    """When an empty body is sent, the saved config values are used."""
    # Mock based on the saved config's base URL (probe calls /api/tags + /v1/models)
    httpx_mock.add_response(
        url=_ollama_tags_url(_SAVED.base_url),
        method="GET",
        json={"models": [{"name": "test-model"}]},
    )
    httpx_mock.add_response(
        url=_openai_models_url(_SAVED.base_url),
        method="GET",
        json={"data": [{"id": "test-model"}]},
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as test_client:
        response = await test_client.post("/api/test-connection", json={})

    assert response.status_code == 200
    data = response.json()
    # With empty body, falls back to saved config defaults
    assert data["url"] == _SAVED.base_url, (
        f"Expected saved-config URL {_SAVED.base_url!r}, got {data.get('url')!r}"
    )
    assert data["status"] == "connected"


@pytest.mark.asyncio
async def test_test_connection_partial_fields_override_only_those(
    httpx_mock: HTTPXMock,
):
    """Only the posted fields override; the rest come from saved config."""
    httpx_mock.add_response(
        url="http://localhost:12346/api/tags",
        method="GET",
        json={"models": [{"name": "test-model"}]},
    )
    httpx_mock.add_response(
        url="http://localhost:12346/v1/models",
        method="GET",
        json={"data": [{"id": "test-model"}]},
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as test_client:
        response = await test_client.post(
            "/api/test-connection",
            json={
                "llm_base_url": "http://localhost:12346",
                # llm_model omitted — should fall back to saved
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "http://localhost:12346"
    assert data["model"] == _SAVED.model, (  # saved config value
        f"Expected saved config model {_SAVED.model!r}, got {data.get('model')!r}"
    )


@pytest.mark.asyncio
async def test_test_connection_failure_shape_matches_js(httpx_mock: HTTPXMock):
    """Unreachable server returns the same keys the JS consumes (pipeline.js)."""
    httpx_mock.add_exception(
        httpx.ConnectError("Connection refused"),
        url="http://localhost:12347/api/tags",
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as test_client:
        response = await test_client.post(
            "/api/test-connection",
            json={"llm_base_url": "http://localhost:12347", "llm_model": "test"},
        )

    assert response.status_code == 200
    data = response.json()
    # Keys consumed by graph/web/static/pipeline.js line 824
    assert set(data.keys()) == {"status", "error", "suggestions", "url", "model"}
    assert data["status"] == "error"
    assert data["error"] == "Server not reachable"
    assert data["suggestions"]
    assert data["url"] == "http://localhost:12347"
    assert data["model"] == "test"


@pytest.mark.asyncio
async def test_api_models_success_shape_matches_js(httpx_mock: HTTPXMock):
    """GET /api/models returns the keys consumed by pipeline.js for model dropdown."""
    httpx_mock.add_response(
        url=_ollama_tags_url(_SAVED.base_url),
        method="GET",
        json={"models": [{"name": "gemma2:27b"}, {"name": "llava:7b"}]},
    )
    httpx_mock.add_response(
        url=_openai_models_url(_SAVED.base_url),
        method="GET",
        json={"data": [{"id": "gpt-4"}]},
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as test_client:
        response = await test_client.get("/api/models")

    assert response.status_code == 200
    data = response.json()
    # Keys consumed by graph/web/static/pipeline.js lines 136-150
    assert set(data.keys()) == {"models", "vision_models", "ollama_base", "openai_base"}
    expected_ollama_base = _SAVED.base_url.rstrip("/")
    if expected_ollama_base.endswith("/v1"):
        expected_ollama_base = expected_ollama_base[:-3]
    assert data["ollama_base"] == expected_ollama_base
    assert data["openai_base"] == _SAVED.base_url
    assert {m["id"] for m in data["models"]} == {"gemma2:27b", "llava:7b", "gpt-4"}
    assert len(data["vision_models"]) == 1
    assert data["vision_models"][0]["id"] == "llava:7b"
    assert data["vision_models"][0]["supports_vision"] is True


@pytest.mark.asyncio
async def test_api_models_failure_shape_matches_js(httpx_mock: HTTPXMock):
    """GET /api/models failure path returns error so the frontend shows it."""
    saved_base = _SAVED.base_url.rstrip("/")
    if saved_base.endswith("/v1"):
        saved_base = saved_base[:-3]
    httpx_mock.add_exception(
        httpx.ConnectError("Connection refused"),
        url=f"{saved_base}/api/tags",
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as test_client:
        response = await test_client.get("/api/models")

    assert response.status_code == 200
    data = response.json()
    assert "error" in data, (
        "Unreachable server must populate 'error' so the frontend shows a failure"
    )
    assert "models" in data
    assert data["models"] == []

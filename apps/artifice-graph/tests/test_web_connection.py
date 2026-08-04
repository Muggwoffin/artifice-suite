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
    # Mock the health-check GET that the handler issues to the LLM server.
    httpx_mock.add_response(
        url="http://localhost:12345",
        method="GET",
        status_code=200,
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
    httpx_mock.add_response(status_code=200)

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
        url="http://localhost:12346",
        method="GET",
        status_code=200,
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

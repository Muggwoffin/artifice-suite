# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for POST /api/byom/model in artifice-draft.

Until this route existed the BYOM screen could detect and test an endpoint but
never record which model to use, so an app launched outside the Hub had no way
to set one at all.
"""

from __future__ import annotations

import artifice_draft.web.runtime as runtime
import pytest
from artifice_draft.web.server import app
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "_SETTINGS_PATH", tmp_path / "web_settings.json")


@pytest.fixture()
def client():
    return TestClient(app)


def test_model_choice_persists_and_shows_in_state(client):
    r = client.post("/api/byom/model", json={"model": "mistral:7b"})
    assert r.status_code == 200
    assert r.json() == {"model": "mistral:7b", "role": "chat"}

    state = client.get("/api/byom/state").json()
    assert state["model"] == "mistral:7b"


def test_choosing_a_model_makes_state_configured(client):
    """A model choice counts as configured even on the default endpoint."""
    assert client.get("/api/byom/state").json()["configured"] is False
    client.post("/api/byom/model", json={"model": "mistral:7b"})
    assert client.get("/api/byom/state").json()["configured"] is True


def test_empty_model_clears_the_choice(client):
    """Clearing returns the app to per-run resolution — a supported state."""
    client.post("/api/byom/model", json={"model": "mistral:7b"})
    r = client.post("/api/byom/model", json={"model": ""})
    assert r.status_code == 200
    assert r.json()["model"] is None
    assert client.get("/api/byom/state").json()["model"] is None


def test_whitespace_only_model_is_treated_as_cleared(client):
    r = client.post("/api/byom/model", json={"model": "   "})
    assert r.json()["model"] is None


def test_unknown_role_is_rejected(client):
    r = client.post("/api/byom/model", json={"model": "x", "role": "vision"})
    assert r.status_code == 400
    assert "vision" in r.json()["error"]

# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Route-level tests for the two native file-dialog routes.

These pin the shared file-dialog contract: every route returns
``{"state": ..., "paths": [...], "reason": ...}``, with ``paths`` populated
only for ``selected`` and ``reason`` only for ``unavailable``.  The
``shared_ui.filedialog`` async entry points are monkeypatched on the
``server`` module, so no test opens a real dialog.
"""

from pathlib import Path

import pytest
from artifice_graph.web import server
from fastapi.testclient import TestClient
from shared_ui.filedialog import DialogResult, DialogState


@pytest.fixture
def client():
    """A bare TestClient — the dialog routes read no config/queue state."""
    with TestClient(server.app) as c:
        yield c


def _install(monkeypatch, name, state, paths=(), reason=""):
    """Replace one shared_ui.filedialog async entry point on ``server``.

    Returns a dict capturing the keyword arguments the route forwarded, so a
    test can assert the FileType filters the handler built.
    """
    captured = {}

    async def fake(**kwargs):
        captured.update(kwargs)
        return DialogResult(
            state=state,
            paths=tuple(Path(p) for p in paths),
            reason=reason,
        )

    monkeypatch.setattr(server, name, fake)
    return captured


# --------------------------------------------------------------------------- #
# pick-file — the shared three-state shape
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "state,paths,reason,expected",
    [
        (
            DialogState.SELECTED,
            ("/data/notes.txt",),
            "",
            {"state": "selected", "paths": ["/data/notes.txt"], "reason": ""},
        ),
        (
            DialogState.CANCELLED,
            (),
            "",
            {"state": "cancelled", "paths": [], "reason": ""},
        ),
        (
            DialogState.UNAVAILABLE,
            (),
            "no native file dialog is available",
            {"state": "unavailable", "paths": [], "reason": "no native file dialog is available"},
        ),
    ],
)
def test_pick_file_returns_three_state_shape(client, monkeypatch, state, paths, reason, expected):
    _install(monkeypatch, "pick_files_async", state, paths, reason)
    res = client.post("/api/native/pick-file")
    assert res.status_code == 200
    assert res.json() == expected


def test_pick_file_allows_multiple_selection(client, monkeypatch):
    """C2 — several files may be selected and all are returned."""
    _install(
        monkeypatch,
        "pick_files_async",
        DialogState.SELECTED,
        paths=("/data/one.txt", "/data/two.md"),
    )
    res = client.post("/api/native/pick-file")
    assert res.json()["paths"] == ["/data/one.txt", "/data/two.md"]


def test_pick_file_builds_text_filter_plus_all_files(client, monkeypatch):
    """C4 — the handler forwards the ``*.txt *.md`` filter plus all-files."""
    captured = _install(monkeypatch, "pick_files_async", DialogState.CANCELLED)
    client.post("/api/native/pick-file")
    assert [(ft.description, tuple(ft.patterns)) for ft in captured["file_types"]] == [
        ("Text files", ("*.txt", "*.md")),
        ("All Files", ("*.*",)),
    ]


# --------------------------------------------------------------------------- #
# pick-folder
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "state,paths,reason,expected",
    [
        (
            DialogState.SELECTED,
            ("/data/vault",),
            "",
            {"state": "selected", "paths": ["/data/vault"], "reason": ""},
        ),
        (
            DialogState.CANCELLED,
            (),
            "",
            {"state": "cancelled", "paths": [], "reason": ""},
        ),
        (
            DialogState.UNAVAILABLE,
            (),
            "tkinter is not installed",
            {"state": "unavailable", "paths": [], "reason": "tkinter is not installed"},
        ),
    ],
)
def test_pick_folder_returns_three_state_shape(client, monkeypatch, state, paths, reason, expected):
    _install(monkeypatch, "pick_folder_async", state, paths, reason)
    res = client.post("/api/native/pick-folder")
    assert res.status_code == 200
    assert res.json() == expected

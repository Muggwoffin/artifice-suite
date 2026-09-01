# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Contract tests for official Tropy Developer API note write-back."""

import json
import sqlite3
from pathlib import Path

import pytest
from artifice_ocr import config
from artifice_ocr.jobs import JobItem
from artifice_ocr.tropy_api import (
    TropyAPIClient,
    TropyAPIError,
    TropyConnection,
    candidate_ports,
    connect,
    note_html,
)
from artifice_ocr.web.runtime import state


def _project(tmp_path: Path, name: str = "Archive.tropy") -> Path:
    root = tmp_path / name
    root.mkdir()
    db = root / "project.tpy"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE project (project_id TEXT, name TEXT, created TEXT, base TEXT)")
    con.execute("INSERT INTO project VALUES ('id', 'Archive', '', 'project')")
    con.commit()
    con.close()
    return root


@pytest.fixture(autouse=True)
def clean_state():
    config.reset()
    config.load_config()
    state.clear()
    yield
    state.clear()
    config.reset()


def test_candidate_ports_prefers_override_and_tropy_state(tmp_path, monkeypatch):
    (tmp_path / "state.json").write_text(json.dumps({"port": 2029}), encoding="utf-8")
    monkeypatch.setattr("artifice_ocr.tropy_api.tropy_config_dir", lambda: tmp_path)
    config.apply_overrides({"tropy_api_port": 3456})
    assert candidate_ports() == [3456, 2029, 2019]


def test_connect_uses_stable_port_and_verifies_project(tmp_path, httpx_mock, monkeypatch):
    project = _project(tmp_path)
    monkeypatch.setattr("artifice_ocr.tropy_api.tropy_config_dir", lambda: tmp_path / "missing")
    httpx_mock.add_response(
        url="http://127.0.0.1:2019/",
        json={"project": str(project), "id": "Archive", "version": "1.17", "status": "ok"},
    )
    httpx_mock.add_response(url="http://127.0.0.1:2019/project/current/", status_code=404)
    connection = connect(project)
    assert connection.port == 2019
    assert connection.project_name == "Archive"
    assert connection.project_prefix == "/project"


def test_connect_uses_named_project_routes_when_available(tmp_path, httpx_mock, monkeypatch):
    project = _project(tmp_path)
    monkeypatch.setattr("artifice_ocr.tropy_api.tropy_config_dir", lambda: tmp_path / "missing")
    httpx_mock.add_response(
        url="http://127.0.0.1:2019/",
        json={"project": str(project), "version": "1.18", "status": "ok"},
    )
    httpx_mock.add_response(
        url="http://127.0.0.1:2019/project/current/",
        json={"project": str(project), "id": "Archive", "version": "1.18", "status": "ok"},
    )
    connection = connect(project)
    assert connection.project_id == "Archive"
    assert connection.project_prefix == "/project/current"


def test_connect_blocks_wrong_open_project(tmp_path, httpx_mock, monkeypatch):
    expected = _project(tmp_path, "Expected.tropy")
    other = _project(tmp_path, "Other.tropy")
    monkeypatch.setattr("artifice_ocr.tropy_api.tropy_config_dir", lambda: tmp_path / "missing")
    for port in (2019, 2029):
        httpx_mock.add_response(
            url=f"http://127.0.0.1:{port}/",
            json={"project": str(other), "id": "Other", "version": "1.17"},
        )
    with pytest.raises(TropyAPIError, match="Other.*Expected"):
        connect(expected)


def test_note_client_uses_current_note_endpoint_and_form_data(tmp_path, httpx_mock):
    project = _project(tmp_path)
    connection = TropyConnection(2019, "Archive", "Archive", project / "project.tpy", "1.17")
    httpx_mock.add_response(
        method="POST", url="http://127.0.0.1:2019/project/current/notes", json={"id": [77]}
    )
    ids = TropyAPIClient(connection).create_note(10, "A < B", "en")
    assert ids == [77]
    request = httpx_mock.get_request()
    assert b"photo=10" in request.content
    assert b"%26lt%3B" in request.content
    assert "/project/import" not in str(request.url)
    assert note_html("A < B") == "<p>A &lt; B</p>"


def test_note_client_uses_stable_note_endpoint(tmp_path, httpx_mock):
    project = _project(tmp_path)
    connection = TropyConnection(
        2019, "current", "Archive", project / "project.tpy", "1.17", "/project"
    )
    httpx_mock.add_response(
        method="POST", url="http://127.0.0.1:2019/project/notes", json={"id": [78]}
    )
    assert TropyAPIClient(connection).create_note(10, "Text", "en") == [78]


class _FakeClient:
    duplicate = False
    writes = []

    def __init__(self, connection):
        self.connection = connection

    def photo(self, photo_id):
        return {"id": photo_id, "item": 1, "notes": [90] if self.duplicate else []}

    def note_text(self, note_id):
        return "Clean text"

    def has_identical_note(self, photo, text):
        return self.duplicate and text == "Clean text"

    def verify_current(self):
        return None

    def create_note(self, photo_id, text, language):
        self.writes.append((photo_id, text, language))
        return [100 + len(self.writes)]


def _queue_item(project: Path) -> JobItem:
    return JobItem(
        path=str(project / "assets" / "page.jpg"),
        language="en",
        source={
            "origin": "tropy-live",
            "photo_id": 10,
            "tropy_item_id": 1,
            "tropy_project": str(project / "project.tpy"),
            "item_title": "Letter",
        },
        results={"cleaned": {"cleaned_text": "Clean text"}},
    )


def test_notes_routes_preview_commit_and_skip_duplicate(tmp_path, monkeypatch):
    project = _project(tmp_path)
    connection = TropyConnection(2019, "Archive", "Archive", project / "project.tpy", "1.17")
    monkeypatch.setattr("artifice_ocr.web.routers.tropy_notes.connect", lambda path: connection)
    monkeypatch.setattr("artifice_ocr.web.routers.tropy_notes.TropyAPIClient", _FakeClient)
    _FakeClient.writes = []
    _FakeClient.duplicate = False
    state.add_items([_queue_item(project)])

    from artifice_ocr.web.routers.tropy_notes import (
        TropyNotesCommitRequest,
        TropyNotesRequest,
        tropy_notes_commit,
        tropy_notes_preview,
    )

    preview = tropy_notes_preview(
        TropyNotesRequest(source="queue", stage="cleaned", project_path=str(project))
    )
    assert preview["write_count"] == 1
    assert preview["project"]["name"] == "Archive"

    commit = tropy_notes_commit(
        TropyNotesCommitRequest(
            source="queue",
            stage="cleaned",
            project_path=str(project),
            expected_write_count=1,
        )
    )
    assert commit["written"] == 1
    assert _FakeClient.writes == [(10, "Clean text", "en")]

    _FakeClient.duplicate = True
    duplicate = tropy_notes_preview(
        TropyNotesRequest(source="queue", stage="cleaned", project_path=str(project))
    )
    assert duplicate["write_count"] == 0
    assert duplicate["counts"]["duplicate"] == 1


def test_notes_route_never_falls_back_to_another_stage(tmp_path, monkeypatch):
    project = _project(tmp_path)
    connection = TropyConnection(2019, "Archive", "Archive", project / "project.tpy", "1.17")
    monkeypatch.setattr("artifice_ocr.web.routers.tropy_notes.connect", lambda path: connection)
    monkeypatch.setattr("artifice_ocr.web.routers.tropy_notes.TropyAPIClient", _FakeClient)
    item = _queue_item(project)
    item.results = {"raw": {"extracted_text": "Raw only"}}
    state.add_items([item])

    from artifice_ocr.web.routers.tropy_notes import TropyNotesRequest, tropy_notes_preview

    data = tropy_notes_preview(
        TropyNotesRequest(source="queue", stage="cleaned", project_path=str(project))
    )
    assert data["write_count"] == 0
    assert data["counts"]["empty"] == 1

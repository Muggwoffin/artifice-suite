# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the Tropy write-back routes (preview + commit).

Runs against a synthetic ``.tpy`` project built the way
``tests/test_tropy_write.py`` builds one (real notes/transcriptions schema plus
the FTS triggers), never a real archive. The write-back setting is opt-in and
default off, so every test that needs the write path enables it explicitly and
the gate-off test asserts the default.

Items are built the way ``tropy_db.items_to_job_items`` emits them: a live
browse carries ``origin="tropy-live"``, a ``photo_id``, and the resolved
``tropy_project`` the id belongs to. That provenance is what lets the route
refuse a write when an item came from a different project than the one being
written to.
"""

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from artifice_ocr import config
from artifice_ocr.jobs import JobItem
from artifice_ocr.web.runtime import state
from fastapi.testclient import TestClient

SCHEMA = """
CREATE TABLE project (project_id TEXT, name TEXT, created TEXT, base TEXT, store TEXT);
CREATE TABLE items (id INTEGER PRIMARY KEY);
CREATE TABLE subjects (id INTEGER PRIMARY KEY, template TEXT);
CREATE TABLE images (id INTEGER PRIMARY KEY);
CREATE TABLE photos (
    id INTEGER PRIMARY KEY, item_id INTEGER, path TEXT, mimetype TEXT,
    page INTEGER DEFAULT 0, filename TEXT
);
CREATE TABLE notes (
    note_id INTEGER PRIMARY KEY, id INTEGER NOT NULL, text TEXT NOT NULL,
    state TEXT NOT NULL, language TEXT NOT NULL DEFAULT 'en',
    created NUMERIC DEFAULT CURRENT_TIMESTAMP,
    modified NUMERIC DEFAULT CURRENT_TIMESTAMP, deleted NUMERIC,
    CHECK (language != '' AND language = trim(lower(language))),
    CHECK (text != '')
);
CREATE TABLE transcriptions (
    transcription_id INTEGER PRIMARY KEY, id INTEGER NOT NULL, text TEXT,
    config TEXT, data TEXT, status NUMERIC NOT NULL DEFAULT 0,
    deleted NUMERIC, created NUMERIC DEFAULT CURRENT_TIMESTAMP,
    modified NUMERIC DEFAULT CURRENT_TIMESTAMP
);
CREATE VIRTUAL TABLE fts_notes USING fts5(id UNINDEXED, text, language UNINDEXED);
CREATE VIRTUAL TABLE fts_transcriptions USING fts5(id UNINDEXED, text);
CREATE TRIGGER notes_ai_fts AFTER INSERT ON notes BEGIN
  INSERT INTO fts_notes (rowid, id, text, language)
    VALUES (NEW.note_id, NEW.id, NEW.text, NEW.language);
END;
CREATE TRIGGER transcriptions_ai_fts AFTER INSERT ON transcriptions BEGIN
  INSERT INTO fts_transcriptions (rowid, id, text)
    VALUES (NEW.transcription_id, NEW.id, NEW.text);
END;
"""


@pytest.fixture
def project(tmp_path):
    return _build_project(tmp_path / "Archive.tropy")


def _build_project(root: Path) -> Path:
    """Build a synthetic Tropy project under ``root`` and return it."""
    (root / "assets").mkdir(parents=True)
    con = sqlite3.connect(root / "project.tpy")
    con.executescript(SCHEMA)
    con.execute("INSERT INTO project VALUES ('u','Archive','2026','project','assets')")
    con.execute("INSERT INTO items (id) VALUES (1)")
    for pid in (10, 11):
        con.execute("INSERT INTO subjects (id, template) VALUES (?, 'photo')", (pid,))
        con.execute("INSERT INTO images (id) VALUES (?)", (pid,))
        con.execute(
            "INSERT INTO photos (id,item_id,path,mimetype,page,filename) "
            "VALUES (?,1,'assets/a.pdf','application/pdf',?,'KV-2-1234.pdf')",
            (pid, pid - 10),
        )
    con.commit()
    con.close()
    return root


def _marker_project(tmp_path, marker="SECRETUSER"):
    """A project whose absolute path contains a recognisable marker."""
    return _build_project(tmp_path / marker / "Archive.tropy")


def _tpy(project) -> str:
    """The resolved ``.tpy`` path a live-browsed item from ``project`` carries."""
    return str((Path(project) / "project.tpy").resolve())


def _item(photo_id, *, text="Der Bericht", path=None, project=None):
    """A live-browsed queue item, as ``items_to_job_items`` emits one.

    ``project`` is the bundle directory the item came from; its ``.tpy`` path
    is stored resolved in ``source["tropy_project"]``. Pass ``None`` to model an
    item with no project provenance at all.
    """
    return JobItem(
        path=path or f"/pages/{photo_id}-{len(text)}.png",
        source={
            "origin": "tropy-live",
            "photo_id": photo_id,
            "tropy_project": _tpy(project) if project is not None else None,
        },
        results={"cleaned": {"cleaned_text": text}},
    )


def _no_photo_item(*, text="kein Photo"):
    """A queue item that did not come from Tropy (no ``photo_id``)."""
    return JobItem(
        path=f"/pages/no-photo-{len(text)}.png",
        results={"cleaned": {"cleaned_text": text}},
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A TestClient against the real app, with a clean queue and config."""
    config.reset()
    config.load_config()
    monkeypatch.setattr("artifice_ocr.tropy_write._tropy_is_running", lambda: False)
    state.clear()

    from artifice_ocr.web import server

    yield TestClient(server.app)

    state.clear()
    config.reset()


# --------------------------------------------------------------------------- #
# gate off
# --------------------------------------------------------------------------- #


def test_gate_off_returns_404_for_both_routes(client):
    """With the setting off (the default) neither route may advertise itself."""
    for path in ("/api/tropy/writeback/preview", "/api/tropy/writeback/commit"):
        resp = client.post(
            path,
            json={
                "project_path": None,
                "stage": "cleaned",
                "item_ids": None,
                "expected_write_count": 0,
            },
        )
        assert resp.status_code == 404, path
        assert "not enabled" in resp.json()["detail"].lower()


# --------------------------------------------------------------------------- #
# preview
# --------------------------------------------------------------------------- #


def test_preview_reports_foreign_separately_from_ineligible(client, project, tmp_path):
    """A foreign item is counted separately from ineligible (not-from-Tropy).

    The three buckets mean different things to a user: "will be written"
    (eligible), "from a different project" (foreign), "not from Tropy"
    (ineligible) — so none is folded into another.
    """
    config.apply_overrides({"tropy_writeback_enabled": True})
    other = _build_project(tmp_path / "Other.tropy")
    state.add_items([_item(10, project=project), _item(20, project=other), _no_photo_item()])

    resp = client.post(
        "/api/tropy/writeback/preview",
        json={"project_path": str(project), "stage": "cleaned", "item_ids": None},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["eligible"] == 1
    assert data["foreign"] == 1
    assert data["ineligible"] == 1
    assert data["blockers"] == []
    assert data["counts"]["notes:insert"] == 1


def test_preview_returns_blockers_verbatim(client, project, monkeypatch):
    """Blockers are returned in the preview body (200), not raised as an error."""
    config.apply_overrides({"tropy_writeback_enabled": True})
    monkeypatch.setattr("artifice_ocr.tropy_write._tropy_is_running", lambda: True)
    state.add_items([_item(10, project=project)])

    resp = client.post(
        "/api/tropy/writeback/preview",
        json={"project_path": str(project), "stage": "cleaned", "item_ids": None},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["blockers"]
    assert any("running" in b.lower() for b in data["blockers"])


def test_preview_selects_only_requested_item_ids(client, project):
    """``item_ids`` narrows the selection, mirroring the export route."""
    config.apply_overrides({"tropy_writeback_enabled": True})
    ten = _item(10, project=project)
    eleven = _item(11, text="Zweite Seite", project=project)
    state.add_items([ten, eleven])

    resp = client.post(
        "/api/tropy/writeback/preview",
        json={
            "project_path": str(project),
            "stage": "cleaned",
            "item_ids": [str(id(ten))],
        },
    )

    assert resp.status_code == 200
    assert resp.json()["eligible"] == 1


def test_preview_matches_two_spellings_of_one_project(client, project):
    """A project passed with a ``..`` segment still matches the stored path.

    The write target and the item's ``tropy_project`` are compared resolved, so
    two spellings of the same ``.tpy`` file are not read as a mismatch.
    """
    config.apply_overrides({"tropy_writeback_enabled": True})
    state.add_items([_item(10, project=project)])

    resp = client.post(
        "/api/tropy/writeback/preview",
        json={
            "project_path": str(project / "sub" / ".."),
            "stage": "cleaned",
            "item_ids": None,
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["eligible"] == 1
    assert data["foreign"] == 0


# --------------------------------------------------------------------------- #
# commit: refusal paths must not touch the database
# --------------------------------------------------------------------------- #


def test_commit_foreign_project_returns_409_and_db_unchanged(client, project, tmp_path):
    """An item from another Tropy project is refused, with nothing written."""
    config.apply_overrides({"tropy_writeback_enabled": True})
    other = _build_project(tmp_path / "Other.tropy")
    state.add_items([_item(20, project=other)])

    db = project / "project.tpy"
    before = db.read_bytes()

    resp = client.post(
        "/api/tropy/writeback/commit",
        json={
            "project_path": str(project),
            "stage": "cleaned",
            "item_ids": None,
            "expected_write_count": 0,
        },
    )

    assert resp.status_code == 409
    assert db.read_bytes() == before
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 0
    con.close()


def test_commit_no_project_returns_409_and_db_unchanged(client, project):
    """An item with no ``tropy_project`` is refused (fail closed), not written."""
    config.apply_overrides({"tropy_writeback_enabled": True})
    state.add_items([_item(10, project=None)])

    db = project / "project.tpy"
    before = db.read_bytes()

    resp = client.post(
        "/api/tropy/writeback/commit",
        json={
            "project_path": str(project),
            "stage": "cleaned",
            "item_ids": None,
            "expected_write_count": 0,
        },
    )

    assert resp.status_code == 409
    assert db.read_bytes() == before
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 0
    con.close()


def test_commit_mixed_queue_returns_409_and_nothing_written(client, project, tmp_path):
    """One foreign item in a mixed queue blocks the whole write, not just itself."""
    config.apply_overrides({"tropy_writeback_enabled": True})
    other = _build_project(tmp_path / "Other.tropy")
    state.add_items([_item(10, project=project), _item(20, project=other)])

    db = project / "project.tpy"
    before = db.read_bytes()

    resp = client.post(
        "/api/tropy/writeback/commit",
        json={
            "project_path": str(project),
            "stage": "cleaned",
            "item_ids": None,
            "expected_write_count": 1,
        },
    )

    assert resp.status_code == 409
    assert db.read_bytes() == before
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 0
    con.close()


def test_commit_blocked_returns_409_and_db_unchanged(client, project, monkeypatch):
    """A blocker present at commit time is a 409 and writes nothing."""
    config.apply_overrides({"tropy_writeback_enabled": True})
    monkeypatch.setattr("artifice_ocr.tropy_write._tropy_is_running", lambda: True)
    state.add_items([_item(10, project=project)])

    db = project / "project.tpy"
    before = db.read_bytes()

    resp = client.post(
        "/api/tropy/writeback/commit",
        json={
            "project_path": str(project),
            "stage": "cleaned",
            "item_ids": None,
            "expected_write_count": 1,
        },
    )

    assert resp.status_code == 409
    assert db.read_bytes() == before
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 0
    con.close()


def test_commit_count_mismatch_returns_409_and_db_unchanged(client, project):
    """A recomputed insertable count that differs from the client's is a 409."""
    config.apply_overrides({"tropy_writeback_enabled": True})
    state.add_items([_item(10, project=project)])

    db = project / "project.tpy"
    before = db.read_bytes()

    resp = client.post(
        "/api/tropy/writeback/commit",
        json={
            "project_path": str(project),
            "stage": "cleaned",
            "item_ids": None,
            "expected_write_count": 2,
        },
    )

    assert resp.status_code == 409
    assert db.read_bytes() == before
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 0
    con.close()


# --------------------------------------------------------------------------- #
# commit: happy path
# --------------------------------------------------------------------------- #


def test_commit_happy_path_writes_notes_with_selection(client, project):
    """A successful commit writes notes carrying the ProseMirror ``selection`` key."""
    config.apply_overrides({"tropy_writeback_enabled": True})
    state.add_items([_item(10, text="Der Bericht\n\nZweiter Absatz", project=project)])

    resp = client.post(
        "/api/tropy/writeback/commit",
        json={
            "project_path": str(project),
            "stage": "cleaned",
            "item_ids": None,
            "expected_write_count": 1,
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["written"] == 1
    assert data["errors"] == []
    assert data["backup_path"] is not None

    con = sqlite3.connect(project / "project.tpy")
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM notes").fetchone()
    con.close()

    assert row["id"] == 10
    stored = json.loads(row["state"])
    assert "selection" in stored
    assert stored["selection"] == {"type": "text", "anchor": 0, "head": 0}


def test_commit_only_writes_eligible_items(client, project):
    """Only the item from the target project is written; the rest are skipped."""
    config.apply_overrides({"tropy_writeback_enabled": True})
    state.add_items([_item(10, project=project), _no_photo_item()])

    resp = client.post(
        "/api/tropy/writeback/commit",
        json={
            "project_path": str(project),
            "stage": "cleaned",
            "item_ids": None,
            "expected_write_count": 1,
        },
    )

    assert resp.status_code == 200
    assert resp.json()["written"] == 1

    con = sqlite3.connect(project / "project.tpy")
    assert con.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 1
    con.close()


# --------------------------------------------------------------------------- #
# error path: no absolute paths in the response body
# --------------------------------------------------------------------------- #


def test_error_path_redacts_absolute_paths(client, tmp_path):
    """A write failure must not leak an absolute path in the response body.

    This is the Windows lesson: a redaction bug in this same area passed on
    POSIX (``tmp_path`` is not under ``$HOME``) and failed only on Windows
    (where it is). Assert on response *content*, not just status.
    """
    config.apply_overrides({"tropy_writeback_enabled": True})
    root = _marker_project(tmp_path)
    db = root / "project.tpy"
    state.add_items([_item(10, text="geheim", project=root)])

    def boom(text):
        raise sqlite3.OperationalError(f"cannot write {db}")

    with patch("artifice_ocr.tropy_write._prosemirror_state", boom):
        resp = client.post(
            "/api/tropy/writeback/commit",
            json={
                "project_path": str(root),
                "stage": "cleaned",
                "item_ids": None,
                "expected_write_count": 1,
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["written"] == 0
    assert data["errors"], "expected a sanitised error to be reported"

    body = resp.text
    assert "SECRETUSER" not in body
    assert str(db) not in body
    assert str(db.parent) not in body
    assert str(tmp_path) not in body
    # the exception type survived sanitisation (still diagnostic)
    assert "OperationalError" in body

# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for writing OCR results back into a Tropy project.

Everything runs against a synthetic project built to match the real schema
(including the FTS triggers), never a real archive. The write-back setting is
opt-in and default off, so the happy-path tests enable it explicitly and the
failure-mode tests assert it blocks the write when left off.
"""

import ast
import json
import logging
import shutil
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from artifice_ocr import config
from artifice_ocr.jobs import JobItem
from artifice_ocr.tropy_write import (
    TARGET_NOTES,
    TARGET_TRANSCRIPTIONS,
    TropyWriter,
    WriteEntry,
    _prosemirror_state,
    entries_from_items,
)

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


@pytest.fixture(autouse=True)
def _writeback_on(monkeypatch):
    """Tropy closed + write-back enabled for every test that doesn't override.

    The feature is opt-in and default off, so the happy-path tests need it on;
    the "disabled" tests flip it back off inside the test body.
    """
    monkeypatch.setattr("artifice_ocr.tropy_write._tropy_is_running", lambda: False)
    config.apply_overrides({"tropy_writeback_enabled": True})
    yield
    config.reset()


# --------------------------------------------------------------------------- #
# opt-in gating (default off)
# --------------------------------------------------------------------------- #


def test_writeback_defaults_off():
    """The setting must ship off, never on, unless the user opts in."""
    config.reset()
    assert config.get("tropy_writeback_enabled", "not-found") is False


def test_write_refuses_when_disabled(project):
    config.apply_overrides({"tropy_writeback_enabled": False})

    with TropyWriter(project) as w:
        preview = w.preview([WriteEntry(photo_id=10, text="Der Bericht")], [TARGET_NOTES])
        assert any("disabled" in b.lower() for b in preview.blockers)
        report = w.write(preview)

    assert report.written == 0
    assert report.errors and any("disabled" in e.lower() for e in report.errors)

    con = sqlite3.connect(project / "project.tpy")
    assert con.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 0
    con.close()


def test_disabled_write_opens_no_writable_connection(project, monkeypatch):
    """With the setting off, the write path must never open a writable handle."""
    config.apply_overrides({"tropy_writeback_enabled": False})
    opened_write = []
    real_connect = TropyWriter._connect

    def spy(self, write=False):
        if write:
            opened_write.append(True)
        return real_connect(self, write=write)

    monkeypatch.setattr(TropyWriter, "_connect", spy)

    with TropyWriter(project) as w:
        preview = w.preview([WriteEntry(photo_id=10, text="x")], [TARGET_NOTES])
        w.write(preview)

    assert opened_write == []


def test_backup_refuses_when_disabled(project):
    config.apply_overrides({"tropy_writeback_enabled": False})

    with TropyWriter(project) as w, pytest.raises(RuntimeError, match="disabled"):
        w.backup()


def test_repair_refuses_when_disabled(project):
    config.apply_overrides({"tropy_writeback_enabled": False})

    with TropyWriter(project) as w, pytest.raises(RuntimeError, match="disabled"):
        w.repair_missing_selections()


# --------------------------------------------------------------------------- #
# the read path must stay read-only
# --------------------------------------------------------------------------- #


def test_tropy_db_never_imports_tropy_write():
    """Static check: tropy_db must not import (or reference) the write module.

    This is the guarantee that browsing an archive cannot modify it. A comment
    is not enough — the assertion reads the module's import statements.
    """
    import artifice_ocr.tropy_db as tropy_db

    src = Path(tropy_db.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and "tropy_write" in node.module:
                offenders.append(f"from {node.module} import ...")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if "tropy_write" in alias.name:
                    offenders.append(f"import {alias.name}")
    assert not offenders, f"tropy_db imports the write module: {offenders}"


# --------------------------------------------------------------------------- #
# preview
# --------------------------------------------------------------------------- #


def test_preview_reports_insertable_rows_without_writing(project):
    entries = [
        WriteEntry(photo_id=10, text="Der Bericht", label="p.1"),
        WriteEntry(photo_id=11, text="Zweite Seite", label="p.2"),
    ]

    with TropyWriter(project) as w:
        preview = w.preview(entries, [TARGET_NOTES])

        assert preview.blockers == []
        assert len(preview.insertable) == 2

        con = sqlite3.connect(project / "project.tpy")
        assert con.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 0
        con.close()


def test_preview_flags_unknown_photo(project):
    entries = [WriteEntry(photo_id=999, text="orphan")]

    with TropyWriter(project) as w:
        preview = w.preview(entries, [TARGET_NOTES])

    assert preview.insertable == []
    assert preview.plans[0].action == "missing-photo"


def test_preview_flags_empty_text(project):
    with TropyWriter(project) as w:
        preview = w.preview([WriteEntry(photo_id=10, text="   ")], [TARGET_NOTES])

    assert preview.plans[0].action == "empty"


def test_preview_requires_a_target(project):
    with TropyWriter(project) as w:
        preview = w.preview([WriteEntry(photo_id=10, text="x")], [])

    assert "no write target selected" in preview.blockers


def test_running_tropy_blocks_the_write(project):
    with (
        patch("artifice_ocr.tropy_write._tropy_is_running", return_value=True),
        TropyWriter(project) as w,
    ):
        preview = w.preview([WriteEntry(photo_id=10, text="x")], [TARGET_NOTES])
        report = w.write(preview)

    assert any("Tropy is running" in b for b in preview.blockers)
    assert report.written == 0

    con = sqlite3.connect(project / "project.tpy")
    assert con.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 0
    con.close()


# --------------------------------------------------------------------------- #
# writing notes
# --------------------------------------------------------------------------- #


def test_write_notes_creates_valid_rows_and_updates_search(project):
    entries = [WriteEntry(photo_id=10, text="Der Bericht\n\nZweiter Absatz", language="DE")]

    with TropyWriter(project) as w:
        report = w.write(w.preview(entries, [TARGET_NOTES]))

    assert report.written == 1
    assert report.backup is not None and report.backup.exists()

    con = sqlite3.connect(project / "project.tpy")
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM notes").fetchone()
    assert row["id"] == 10
    assert row["text"].startswith("Der Bericht")
    assert row["language"] == "de"  # normalised to satisfy the CHECK

    state = json.loads(row["state"])
    assert state["doc"]["type"] == "doc"
    assert state["doc"]["content"][0]["content"][0]["text"] == "Der Bericht"
    assert "selection" in state  # missing this crashes Tropy's note editor on open

    # the FTS trigger fired, so Tropy's search will find it
    hits = con.execute("SELECT COUNT(*) FROM fts_notes WHERE text MATCH 'Bericht'")
    assert hits.fetchone()[0] == 1
    con.close()


def test_stored_note_carries_selection_key(project):
    """Every note written to disk must carry a top-level `selection` key.

    Regression guard: an earlier version of `_prosemirror_state()` omitted it,
    and Tropy's note editor then crashed on open (minified React error #520)
    for every note written — a stored note that can never be read back. The
    write itself succeeded, so nothing caught it. This asserts on the **stored
    JSON** and must FAIL if the key is ever dropped again.
    """
    with TropyWriter(project) as w:
        report = w.write(w.preview([WriteEntry(photo_id=10, text="Ein Satz")], [TARGET_NOTES]))
    assert report.written == 1

    con = sqlite3.connect(project / "project.tpy")
    row = con.execute("SELECT state FROM notes WHERE id = 10").fetchone()
    con.close()

    state = json.loads(row[0])
    assert isinstance(state, dict)
    assert "selection" in state
    assert state["selection"] == {"type": "text", "anchor": 0, "head": 0}


def test_write_transcriptions_marks_its_own_rows(project):
    entries = [WriteEntry(photo_id=11, text="Transkribierter Text", stage="cleaned")]

    with TropyWriter(project) as w:
        report = w.write(w.preview(entries, [TARGET_TRANSCRIPTIONS]))

    assert report.written == 1
    con = sqlite3.connect(project / "project.tpy")
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM transcriptions").fetchone()
    assert row["id"] == 11
    assert row["text"] == "Transkribierter Text"
    assert json.loads(row["config"])["generator"] == "artifice_ocr"
    assert (
        con.execute(
            "SELECT COUNT(*) FROM fts_transcriptions WHERE text MATCH 'Transkribierter'"
        ).fetchone()[0]
        == 1
    )
    con.close()


def test_both_targets_in_one_run(project):
    entries = [WriteEntry(photo_id=10, text="Beides")]

    with TropyWriter(project) as w:
        report = w.write(w.preview(entries, [TARGET_NOTES, TARGET_TRANSCRIPTIONS]))

    assert report.written == 2
    con = sqlite3.connect(project / "project.tpy")
    assert con.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM transcriptions").fetchone()[0] == 1
    con.close()


def test_rerunning_does_not_duplicate(project):
    entries = [WriteEntry(photo_id=10, text="Genau derselbe Text")]

    with TropyWriter(project) as w:
        first = w.write(w.preview(entries, [TARGET_NOTES]))
    with TropyWriter(project) as w:
        second_preview = w.preview(entries, [TARGET_NOTES])
        second = w.write(second_preview)

    assert first.written == 1
    assert second.written == 0
    assert second_preview.plans[0].action == "duplicate"

    con = sqlite3.connect(project / "project.tpy")
    assert con.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 1
    con.close()


def test_failed_write_rolls_back_completely(project):
    entries = [WriteEntry(photo_id=10, text="erste"), WriteEntry(photo_id=11, text="zweite")]

    with TropyWriter(project) as w:
        preview = w.preview(entries, [TARGET_NOTES])

        # Fail while building the second note, after the first insert has
        # already been issued inside the transaction.
        calls = {"n": 0}
        real_state = _prosemirror_state

        def flaky(text):
            calls["n"] += 1
            if calls["n"] == 2:
                raise sqlite3.OperationalError("disk full")
            return real_state(text)

        with patch("artifice_ocr.tropy_write._prosemirror_state", flaky):
            report = w.write(preview)

    assert report.written == 0
    assert report.errors
    con = sqlite3.connect(project / "project.tpy")
    assert con.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 0
    con.close()


def test_backup_can_be_skipped(project):
    with TropyWriter(project) as w:
        report = w.write(
            w.preview([WriteEntry(photo_id=10, text="x")], [TARGET_NOTES]), make_backup=False
        )

    assert report.written == 1
    assert report.backup is None


# --------------------------------------------------------------------------- #
# backup sidecars
# --------------------------------------------------------------------------- #


def test_backup_copies_wal_and_shm_sidecars(project):
    """A .tpy copied without its -wal/-shm sidecars is not a valid restore
    point. backup() must copy every sidecar that exists."""
    db = project / "project.tpy"
    (Path(str(db) + "-wal")).write_bytes(b"wal")
    (Path(str(db) + "-shm")).write_bytes(b"shm")

    with TropyWriter(project) as w:
        backup = w.backup()

    assert backup.exists()
    assert Path(str(backup) + "-wal").exists()
    assert Path(str(backup) + "-shm").exists()


def test_backup_when_no_sidecars_present(project):
    """With no -wal/-shm sidecars, backup() still produces a bare .tpy."""
    with TropyWriter(project) as w:
        backup = w.backup()

    assert backup.exists()
    assert not Path(str(backup) + "-wal").exists()
    assert not Path(str(backup) + "-shm").exists()


# --------------------------------------------------------------------------- #
# locked database
# --------------------------------------------------------------------------- #


def test_locked_database_produces_legible_blocker(project):
    """A held write lock must surface as a legible reason, never a bare
    sqlite3.OperationalError leaking out of blockers()."""
    locker = sqlite3.connect(project / "project.tpy", isolation_level=None)
    locker.execute("BEGIN IMMEDIATE")
    try:
        with TropyWriter(project) as w:
            blockers = w.blockers()
    finally:
        locker.execute("ROLLBACK")
        locker.close()

    assert all(isinstance(b, str) for b in blockers)
    lock_msgs = [b for b in blockers if "locked" in b.lower()]
    assert lock_msgs, f"expected a lock blocker, got {blockers}"


# --------------------------------------------------------------------------- #
# repairing notes written before the selection-key fix
# --------------------------------------------------------------------------- #


def test_repair_fixes_a_note_missing_selection(project):
    con = sqlite3.connect(project / "project.tpy")
    broken_state = json.dumps(
        {
            "doc": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "attrs": {"align": "left"},
                        "content": [{"type": "text", "text": "Dear Hig,"}],
                    },
                ],
            }
        }
    )
    con.execute(
        "INSERT INTO notes (id, text, state, language) VALUES (10, 'Dear Hig,', ?, 'en')",
        (broken_state,),
    )
    con.commit()
    con.close()

    with TropyWriter(project) as w:
        repaired = w.repair_missing_selections()

    con = sqlite3.connect(project / "project.tpy")
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT state, text FROM notes WHERE id = 10").fetchone()
    con.close()

    assert repaired == 1
    state = json.loads(row["state"])
    assert "selection" in state
    assert state["selection"] == {"type": "text", "anchor": 0, "head": 0}
    # nothing else about the note changed
    assert row["text"] == "Dear Hig,"
    assert state["doc"]["content"][0]["content"][0]["text"] == "Dear Hig,"


def test_repair_leaves_healthy_notes_untouched(project):
    con = sqlite3.connect(project / "project.tpy")
    healthy_state = json.dumps(
        {
            "doc": {"type": "doc", "content": [{"type": "paragraph", "attrs": {"align": "left"}}]},
            "selection": {"type": "text", "anchor": 5, "head": 5},
        }
    )
    con.execute(
        "INSERT INTO notes (id, text, state, language) VALUES (10, 'x', ?, 'en')", (healthy_state,)
    )
    con.commit()
    con.close()

    with TropyWriter(project) as w:
        repaired = w.repair_missing_selections()

    assert repaired == 0
    con = sqlite3.connect(project / "project.tpy")
    row = con.execute("SELECT state FROM notes WHERE id = 10").fetchone()
    con.close()
    assert json.loads(row[0])["selection"] == {"type": "text", "anchor": 5, "head": 5}


def test_repair_reports_nothing_to_do_when_there_are_no_notes(project):
    with TropyWriter(project) as w:
        assert w.repair_missing_selections() == 0


def test_repair_refuses_while_tropy_is_running(project):
    with (
        patch("artifice_ocr.tropy_write._tropy_is_running", return_value=True),
        TropyWriter(project) as w,
        pytest.raises(RuntimeError, match="running"),
    ):
        w.repair_missing_selections()


def test_repair_backs_up_by_default(project):
    con = sqlite3.connect(project / "project.tpy")
    con.execute(
        "INSERT INTO notes (id, text, state, language) VALUES (10, 'x', ?, 'en')",
        (json.dumps({"doc": {"type": "doc", "content": []}}),),
    )
    con.commit()
    con.close()

    with TropyWriter(project) as w:
        w.repair_missing_selections()

    backups = list(project.glob("*.backup.tpy"))
    assert len(backups) == 1


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def test_prosemirror_state_handles_blank_lines():
    state = json.loads(_prosemirror_state("eins\n\nzwei"))
    paragraphs = state["doc"]["content"]

    assert len(paragraphs) == 3
    assert "content" not in paragraphs[1]  # blank line carries no text node
    assert paragraphs[2]["content"][0]["text"] == "zwei"


def test_prosemirror_state_includes_a_selection():
    """Regression test: this key was missing entirely, which crashed Tropy's
    note editor on open (a minified React error, #520) instead of raising
    anything on our side — the write itself succeeded, so nothing here ever
    caught it. Confirmed against a real project: every one of 1101 existing
    notes has a `selection` key; a note written by this function had none."""
    state = json.loads(_prosemirror_state("some text"))

    assert "selection" in state
    assert state["selection"]["type"] == "text"
    assert isinstance(state["selection"]["anchor"], int)
    assert isinstance(state["selection"]["head"], int)


def test_entries_from_items_only_takes_tropy_pages():
    tropy_item = JobItem(path="a.pdf", source={"photo_id": 42})
    tropy_item.results = {"cleaned": {"cleaned_text": "sauber"}}
    plain_item = JobItem(path="b.png")
    plain_item.results = {"cleaned": {"cleaned_text": "ignored"}}

    entries = entries_from_items([tropy_item, plain_item])

    assert len(entries) == 1
    assert entries[0].photo_id == 42
    assert entries[0].text == "sauber"


def test_entries_from_items_falls_back_when_stage_missing():
    item = JobItem(path="a.pdf", source={"photo_id": 7})
    item.results = {"raw": {"extracted_text": "roh"}}

    entries = entries_from_items([item], stage="translated")

    assert entries[0].text == "roh"
    assert entries[0].stage == "raw_ocr"


def test_entries_use_detected_language():
    item = JobItem(path="a.pdf", source={"photo_id": 7})
    item.results = {
        "cleaned": {"cleaned_text": "text"},
        "translated": {"source_language": "fr"},
    }

    assert entries_from_items([item])[0].clean_language() == "fr"


# --------------------------------------------------------------------------- #
# F1 — TOCTOU between preview and write
# --------------------------------------------------------------------------- #


def test_blocker_appearing_after_preview_aborts_the_write(project):
    """A blocker that appears *after* preview must abort the write.

    The user previews (clean), pauses, reopens Tropy, then clicks write. The
    write-time re-check must catch it — not trust the stale preview — and
    write nothing.
    """
    calls = {"n": 0}

    def tropy_appears_later():
        calls["n"] += 1
        return calls["n"] >= 2  # first call (preview): closed; second: running

    with (
        patch("artifice_ocr.tropy_write._tropy_is_running", side_effect=tropy_appears_later),
        TropyWriter(project) as w,
    ):
        preview = w.preview([WriteEntry(photo_id=10, text="x")], [TARGET_NOTES])
        assert preview.blockers == []
        report = w.write(preview)

    assert report.written == 0
    assert any("Tropy is running" in e for e in report.errors)

    con = sqlite3.connect(project / "project.tpy")
    assert con.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 0
    con.close()


def test_backup_and_write_happen_under_a_held_write_lock(project, monkeypatch):
    """The backup copies and the inserts must run while the writer holds the
    write lock, so no concurrent writer or checkpoint can interleave between
    the ``.tpy``/``-wal``/``-shm`` copies (F1/F4)."""
    db = project / "project.tpy"
    real_copy2 = shutil.copy2
    observed = []

    def spy_copy2(src, dst, *args, **kwargs):
        if not observed:
            # First copy (the .tpy): assert another connection cannot begin a
            # write transaction, i.e. our writer is holding the write lock.
            observed.append(True)
            probe = sqlite3.connect(db, isolation_level=None, timeout=0.2)
            try:
                probe.execute("BEGIN IMMEDIATE")
                held = False
                probe.execute("ROLLBACK")
            except sqlite3.OperationalError:
                held = True
            finally:
                probe.close()
            observed.append(held)
        return real_copy2(src, dst, *args, **kwargs)

    monkeypatch.setattr(shutil, "copy2", spy_copy2)

    with TropyWriter(project) as w:
        report = w.write(w.preview([WriteEntry(photo_id=10, text="x")], [TARGET_NOTES]))

    assert report.written == 1
    assert observed == [True, True], "write lock was not held across the backup"


def test_repair_rechecks_blockers_before_writing(project):
    """repair_missing_selections re-runs the preflight before taking the lock."""
    con = sqlite3.connect(project / "project.tpy")
    con.execute(
        "INSERT INTO notes (id, text, state, language) VALUES (10, 'x', ?, 'en')",
        (json.dumps({"doc": {"type": "doc", "content": []}}),),
    )
    con.commit()
    con.close()

    calls = {"n": 0}

    def tropy_appears_later():
        calls["n"] += 1
        return calls["n"] >= 2

    with (
        patch("artifice_ocr.tropy_write._tropy_is_running", side_effect=tropy_appears_later),
        TropyWriter(project) as w,
        pytest.raises(RuntimeError, match="running"),
    ):
        w.repair_missing_selections()

    # the broken note was left untouched
    con = sqlite3.connect(project / "project.tpy")
    state = con.execute("SELECT state FROM notes WHERE id = 10").fetchone()[0]
    con.close()
    assert "selection" not in json.loads(state)


# --------------------------------------------------------------------------- #
# F2/F3 — no absolute paths in logs, blockers, or reports
# --------------------------------------------------------------------------- #


def test_successful_write_leaks_no_absolute_path(tmp_path, caplog):
    root = _marker_project(tmp_path)

    with caplog.at_level(logging.INFO), TropyWriter(root) as w:
        report = w.write(w.preview([WriteEntry(photo_id=10, text="geheim")], [TARGET_NOTES]))

    assert report.written == 1
    assert "SECRETUSER" not in caplog.text
    # the diagnostic still ran (not a vacuous pass) and still names the action
    assert "Wrote" in caplog.text
    assert "Backed up" in caplog.text


def test_error_report_and_log_redact_absolute_path(tmp_path, caplog):
    root = _marker_project(tmp_path)
    db = root / "project.tpy"

    with caplog.at_level(logging.INFO), TropyWriter(root) as w:
        preview = w.preview([WriteEntry(photo_id=10, text="geheim")], [TARGET_NOTES])

        def boom(text):
            raise sqlite3.OperationalError(f"cannot write {db}")

        with patch("artifice_ocr.tropy_write._prosemirror_state", boom):
            report = w.write(preview)

    assert report.written == 0
    assert report.errors
    assert all("SECRETUSER" not in e for e in report.errors)
    assert "SECRETUSER" not in caplog.text
    # the exception type survived sanitisation (still diagnostic)
    assert any("OperationalError" in e for e in report.errors)


def test_missing_db_error_redacts_absolute_path(tmp_path):
    missing = tmp_path / "SECRETUSER" / "Archive.tropy" / "project.tpy"
    with pytest.raises(FileNotFoundError) as excinfo:
        TropyWriter(missing)
    assert "SECRETUSER" not in str(excinfo.value)


def test_locked_blocker_redacts_absolute_path(tmp_path):
    root = _marker_project(tmp_path)
    db = root / "project.tpy"

    locker = sqlite3.connect(db, isolation_level=None)
    locker.execute("BEGIN IMMEDIATE")
    try:
        with TropyWriter(root) as w:
            blockers = w.blockers()
    finally:
        locker.execute("ROLLBACK")
        locker.close()

    lock_msgs = [b for b in blockers if "locked" in b.lower()]
    assert lock_msgs, f"expected a lock blocker, got {blockers}"
    assert all("SECRETUSER" not in b for b in blockers)

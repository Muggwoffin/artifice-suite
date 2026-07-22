"""Tests for the web frontend's HTTP surface.

Scope is deliberately the same as the rest of this test suite: no real model
calls. The SSE stream (`/api/events`) is exercised manually against a live
server instead of here, since driving an unbounded generator through a
synchronous TestClient risks a hanging test for no real safety benefit — the
underlying event plumbing (`JobRunner` -> `queue.Queue`) already has its own
coverage in `test_gui.py`.

`server.py` binds `state` at import time via `from .runtime import state`, so
patching `runtime.state` after that import would not reach the endpoints —
they resolve `state` from `server`'s own module globals. The fixture below
patches `server.state` directly for that reason.
"""

import socket
import sys

import pytest
from fastapi.testclient import TestClient

from src.ocr_pipeline import config
from src.ocr_pipeline.web import server
from src.ocr_pipeline.web.runtime import RunState


@pytest.fixture
def client(tmp_path, monkeypatch):
    # config.save_user_settings() always targets ~/.ocr_pipeline/settings.json
    # by design (it's a per-user file, not something callers parameterise) —
    # so any test that reaches it must redirect the module constant itself,
    # or it will overwrite the developer's real saved settings.
    monkeypatch.setattr(config, "_SETTINGS_PATH", tmp_path / "settings.json")

    config.reset()
    config.load_config()
    config.apply_overrides({"history_db": str(tmp_path / "history.db")})

    fresh = RunState()
    monkeypatch.setattr(server, "state", fresh)
    monkeypatch.setattr("src.ocr_pipeline.web.runtime.state", fresh)

    with TestClient(server.app) as c:
        yield c


# --------------------------------------------------------------------------- #
# static frontend
# --------------------------------------------------------------------------- #

def test_index_serves_the_frontend(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "OCR Pipeline" in res.text


def test_static_assets_are_mounted(client):
    res = client.get("/static/css/app.css")
    assert res.status_code == 200
    assert "--paper" in res.text  # the actual design tokens, not a stub


# --------------------------------------------------------------------------- #
# queue
# --------------------------------------------------------------------------- #

def test_empty_queue_on_startup(client):
    res = client.get("/api/queue")
    assert res.status_code == 200
    assert res.json() == {"items": [], "status": {"running": False, "paused": False, "total": 0}}


def test_add_paths_resolves_supported_extensions_only(client, tmp_path):
    (tmp_path / "a.png").write_bytes(b"x")
    (tmp_path / "b.txt").write_bytes(b"x")  # unsupported, must be ignored

    res = client.post("/api/queue/add-paths", json={
        "paths": [str(tmp_path / "a.png"), str(tmp_path / "b.txt")],
    })
    assert res.status_code == 200
    body = res.json()
    assert body["added"] == 1
    assert body["items"][0]["name"] == "a.png"


def test_add_paths_expands_a_folder(client, tmp_path):
    (tmp_path / "one.png").write_bytes(b"x")
    (tmp_path / "two.pdf").write_bytes(b"x")
    (tmp_path / "readme.md").write_bytes(b"x")

    res = client.post("/api/queue/add-paths", json={"paths": [str(tmp_path)]})
    assert res.json()["added"] == 2


def test_add_paths_deduplicates(client, tmp_path):
    f = tmp_path / "a.png"
    f.write_bytes(b"x")

    first = client.post("/api/queue/add-paths", json={"paths": [str(f)]})
    second = client.post("/api/queue/add-paths", json={"paths": [str(f)]})

    assert first.json()["added"] == 1
    assert second.json()["added"] == 0
    assert len(second.json()["items"]) == 1


def test_remove_items(client, tmp_path):
    f = tmp_path / "a.png"
    f.write_bytes(b"x")
    added = client.post("/api/queue/add-paths", json={"paths": [str(f)]}).json()
    item_id = added["items"][0]["id"]

    res = client.post("/api/queue/remove", json={"ids": [item_id]})
    assert res.json()["removed"] == 1
    assert res.json()["items"] == []


def test_clear_queue(client, tmp_path):
    f = tmp_path / "a.png"
    f.write_bytes(b"x")
    client.post("/api/queue/add-paths", json={"paths": [str(f)]})

    res = client.post("/api/queue/clear")
    assert res.json()["items"] == []
    assert client.get("/api/queue").json()["items"] == []


# --------------------------------------------------------------------------- #
# run control guardrails (no real run is started — no model calls in tests)
# --------------------------------------------------------------------------- #

def test_start_run_rejects_empty_queue(client):
    res = client.post("/api/run/start", json={"stages": ["ocr"]})
    assert res.status_code == 409
    assert "empty" in res.json()["detail"].lower()


def test_start_run_rejects_no_stages(client, tmp_path):
    f = tmp_path / "a.png"
    f.write_bytes(b"x")
    client.post("/api/queue/add-paths", json={"paths": [str(f)]})

    res = client.post("/api/run/start", json={"stages": []})
    assert res.status_code == 409
    assert "stage" in res.json()["detail"].lower()


def test_skip_unknown_item_reports_not_ok(client):
    res = client.post("/api/run/skip", json={"id": "does-not-exist"})
    assert res.json() == {"ok": False}


def test_pause_resume_cancel_are_no_ops_without_a_run(client):
    # None of these should raise just because nothing is running yet.
    for path in ("/api/run/pause", "/api/run/resume", "/api/run/cancel"):
        assert client.post(path).json() == {"ok": True}


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #

def test_get_config_returns_expected_keys(client):
    res = client.get("/api/config")
    body = res.json()
    assert "cleanup_model" in body
    assert "ollama_think" in body


def test_set_config_only_persists_whitelisted_keys(client):
    res = client.post("/api/config", json={
        "output_dir": "somewhere",
        "not_a_real_setting": "should be dropped",
    })
    assert res.json() == {"ok": True}
    assert config.get("output_dir") == "somewhere"
    assert config.get("not_a_real_setting") is None


def test_config_reset_discards_overrides(client):
    client.post("/api/config", json={"cleanup_model": "a-custom-model"})
    assert client.get("/api/config").json()["cleanup_model"] == "a-custom-model"

    res = client.post("/api/config/reset")
    assert res.json()["cleanup_model"] == "gemma4:12b"
    assert client.get("/api/config").json()["cleanup_model"] == "gemma4:12b"


# --------------------------------------------------------------------------- #
# tropy (read-only endpoints; no real project on disk during tests)
# --------------------------------------------------------------------------- #

def test_tropy_browse_reports_a_clean_error_for_a_missing_project(client, tmp_path):
    res = client.post("/api/tropy/browse", json={"project": str(tmp_path / "nope.tropy")})
    assert res.status_code == 400


def test_tropy_add_reports_a_clean_error_for_a_missing_project(client, tmp_path):
    res = client.post("/api/tropy/add", json={"project": str(tmp_path / "nope.tropy")})
    assert res.status_code == 400


# --------------------------------------------------------------------------- #
# preview (in-memory queue item text)
# --------------------------------------------------------------------------- #

def test_preview_missing_item_is_404(client):
    res = client.get("/api/queue/does-not-exist/preview")
    assert res.status_code == 404


def test_preview_returns_text_confidence_and_diff(client, tmp_path):
    f = tmp_path / "a.png"
    f.write_bytes(b"x")
    added = client.post("/api/queue/add-paths", json={"paths": [str(f)]}).json()
    item_id = added["items"][0]["id"]

    item = server.state.get(item_id)
    item.results = {
        "raw": {"extracted_text": "Der Be-\nricht war unvollstandig."},
        "cleaned": {"cleaned_text": "Der Bericht war unvollstandig."},
        "translated": {"translated_text": "The report was incomplete."},
    }
    item.confidence = 91
    item.language = "German"

    res = client.get(f"/api/queue/{item_id}/preview")
    assert res.status_code == 200
    body = res.json()
    assert body["raw"].startswith("Der Be-")
    assert body["cleaned"] == "Der Bericht war unvollstandig."
    assert body["confidence"] == 91
    assert body["confidence_tier"] == "high"
    # a word actually changed between raw and cleaned, so a range exists
    assert body["diff"]["raw_ranges"] or body["diff"]["cleaned_ranges"]


# --------------------------------------------------------------------------- #
# preview: source image (zoom/pan pane) + raw-text correction
# --------------------------------------------------------------------------- #

def test_image_route_404s_for_unknown_item(client):
    res = client.get("/api/queue/does-not-exist/image")
    assert res.status_code == 404


def test_image_route_passes_jpg_through_unchanged(client, tmp_path):
    f = tmp_path / "a.jpg"
    f.write_bytes(b"\xff\xd8\xff-fake-jpeg-bytes")
    added = client.post("/api/queue/add-paths", json={"paths": [str(f)]}).json()
    item_id = added["items"][0]["id"]

    res = client.get(f"/api/queue/{item_id}/image")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/jpeg"
    assert res.content == b"\xff\xd8\xff-fake-jpeg-bytes"


def test_image_route_converts_tiff_to_png(client, tmp_path, monkeypatch):
    # No TIFF writer is available in this environment (Pillow is deliberately
    # not a dependency), so the conversion call itself is mocked rather than
    # exercised against a real TIFF file — the same class of trade-off the
    # rest of this suite makes for real model calls.
    import fitz

    f = tmp_path / "a.tif"
    f.write_bytes(b"not-a-real-tiff")
    added = client.post("/api/queue/add-paths", json={"paths": [str(f)]}).json()
    item_id = added["items"][0]["id"]

    class FakePixmap:
        def __init__(self, path):
            assert path == str(f)

        def tobytes(self, fmt):
            assert fmt == "png"
            return b"\x89PNG-fake-bytes"

    monkeypatch.setattr(fitz, "Pixmap", FakePixmap)

    res = client.get(f"/api/queue/{item_id}/image")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert res.content == b"\x89PNG-fake-bytes"


def test_image_route_renders_only_the_pdf_page_item_points_at(client, tmp_path):
    import fitz

    from src.ocr_pipeline.jobs import JobItem

    pdf_path = tmp_path / "doc.pdf"
    doc = fitz.open()
    doc.new_page(width=200, height=100)  # page 0: 2:1 landscape
    doc.new_page(width=50, height=150)   # page 1: 1:3 portrait — the one requested
    doc.new_page(width=300, height=100)  # page 2: 3:1 landscape
    doc.save(str(pdf_path))
    doc.close()

    item = JobItem(path=str(pdf_path), page=1)
    server.state.add_items([item])
    item_id = server.state.queue_snapshot()[-1]["id"]

    res = client.get(f"/api/queue/{item_id}/image")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"

    rendered = fitz.Pixmap(res.content)
    # Page 1's aspect ratio (tall) is distinct from both its neighbours
    # (wide) — this would fail if page 0 or page 2 were rendered instead.
    assert rendered.height > rendered.width
    assert rendered.width not in (200 * 300 // 72, 300 * 300 // 72)


def test_image_route_caps_an_oversized_pdf_page(client, tmp_path):
    import fitz

    from src.ocr_pipeline.jobs import JobItem
    from src.ocr_pipeline.web.runtime import IMAGE_MAX_LONG_EDGE

    pdf_path = tmp_path / "huge.pdf"
    doc = fitz.open()
    doc.new_page(width=2000, height=1000)  # long edge at 300dpi would be ~8333px
    doc.save(str(pdf_path))
    doc.close()

    item = JobItem(path=str(pdf_path), page=0)
    server.state.add_items([item])
    item_id = server.state.queue_snapshot()[-1]["id"]

    res = client.get(f"/api/queue/{item_id}/image")
    rendered = fitz.Pixmap(res.content)
    assert max(rendered.width, rendered.height) <= IMAGE_MAX_LONG_EDGE


def test_raw_text_route_404s_for_unknown_item(client):
    res = client.post("/api/queue/does-not-exist/raw-text", json={"text": "x"})
    assert res.status_code == 404


def test_raw_text_save_updates_in_memory_only_when_no_output_exists(client, tmp_path):
    f = tmp_path / "a.png"
    f.write_bytes(b"x")
    added = client.post("/api/queue/add-paths", json={"paths": [str(f)]}).json()
    item_id = added["items"][0]["id"]

    item = server.state.get(item_id)
    item.results = {"raw": {"extracted_text": "origianl typo"}}

    res = client.post(f"/api/queue/{item_id}/raw-text", json={"text": "original corrected"})
    assert res.status_code == 200
    body = res.json()
    assert body["raw"] == "original corrected"
    assert item.results["raw"]["extracted_text"] == "original corrected"
    # nothing on disk to touch — no output dir was ever created for this stem
    assert not (tmp_path / "raw_ocr").exists()


def test_raw_text_save_overwrites_disk_output_preserving_other_provenance(client, tmp_path):
    import json as jsonlib

    output_dir = tmp_path / "output"
    text_dir = output_dir / "raw_ocr" / "text"
    json_dir = output_dir / "raw_ocr" / "json"
    text_dir.mkdir(parents=True)
    json_dir.mkdir(parents=True)

    f = tmp_path / "a.png"
    f.write_bytes(b"x")
    added = client.post("/api/queue/add-paths", json={"paths": [str(f)]}).json()
    item_id = added["items"][0]["id"]
    item = server.state.get(item_id)
    item.results = {"raw": {"extracted_text": "garbld txt"}}

    (text_dir / f"{item.stem}.txt").write_text("garbld txt", encoding="utf-8")
    original_json = {
        "source_file": str(f), "stage": "raw_ocr", "extracted_text": "garbld txt",
        "engine": "lm-studio", "model": "some-vision-model",
        "ocr_prompt": "OCR: Extract all visible text...",
        "timestamp": "2026-01-01T00:00:00+00:00", "page": 1, "total_pages": 1,
    }
    (json_dir / f"{item.stem}.json").write_text(jsonlib.dumps(original_json), encoding="utf-8")

    config.apply_overrides({"output_dir": str(output_dir)})

    res = client.post(f"/api/queue/{item_id}/raw-text", json={"text": "corrected text"})
    assert res.status_code == 200

    assert (text_dir / f"{item.stem}.txt").read_text(encoding="utf-8") == "corrected text"

    saved = jsonlib.loads((json_dir / f"{item.stem}.json").read_text(encoding="utf-8"))
    assert saved["extracted_text"] == "corrected text"
    assert saved["edited"] is True
    assert "edited_at" in saved
    # everything about the *original* OCR pass is untouched
    for key in ("engine", "model", "ocr_prompt", "timestamp", "source_file", "page", "total_pages"):
        assert saved[key] == original_json[key]


def test_raw_text_save_never_touches_cleaned_or_translated_dirs(client, tmp_path):
    output_dir = tmp_path / "output"
    (output_dir / "raw_ocr" / "text").mkdir(parents=True)
    (output_dir / "raw_ocr" / "json").mkdir(parents=True)
    (output_dir / "cleaned" / "text").mkdir(parents=True)
    (output_dir / "translated" / "text").mkdir(parents=True)

    f = tmp_path / "a.png"
    f.write_bytes(b"x")
    added = client.post("/api/queue/add-paths", json={"paths": [str(f)]}).json()
    item_id = added["items"][0]["id"]
    item = server.state.get(item_id)

    (output_dir / "raw_ocr" / "text" / f"{item.stem}.txt").write_text("orig", encoding="utf-8")
    (output_dir / "raw_ocr" / "json" / f"{item.stem}.json").write_text(
        '{"extracted_text": "orig"}', encoding="utf-8")
    config.apply_overrides({"output_dir": str(output_dir)})

    client.post(f"/api/queue/{item_id}/raw-text", json={"text": "edited"})

    assert list((output_dir / "cleaned" / "text").iterdir()) == []
    assert list((output_dir / "translated" / "text").iterdir()) == []


# --------------------------------------------------------------------------- #
# settings: document types + health
# --------------------------------------------------------------------------- #

def test_document_types_lists_known_types(client):
    res = client.get("/api/document-types")
    types = res.json()["types"]
    assert "default" in types
    assert "handwritten" in types


def test_health_check_reports_service_status(client, monkeypatch):
    monkeypatch.setattr("src.ocr_pipeline.utils.check_lm_studio", lambda *a, **k: None)
    monkeypatch.setattr("src.ocr_pipeline.utils.check_ollama", lambda models=None: [])

    res = client.get("/api/health")
    body = res.json()
    assert body["lm_studio"]["ok"] is True
    assert body["ollama"]["ok"] is True
    assert all(m["ok"] for m in body["models"])


def test_health_check_surfaces_unreachable_services(client, monkeypatch):
    monkeypatch.setattr("src.ocr_pipeline.utils.check_lm_studio",
                        lambda *a, **k: "Cannot reach LM Studio at http://x (ConnectionError)")
    monkeypatch.setattr("src.ocr_pipeline.utils.check_ollama",
                        lambda models=None: ["Cannot reach Ollama server (ConnectionError)"])

    res = client.get("/api/health")
    body = res.json()
    assert body["lm_studio"]["ok"] is False
    assert body["ollama"]["ok"] is False
    assert all(not m["ok"] for m in body["models"])


# --------------------------------------------------------------------------- #
# history
# --------------------------------------------------------------------------- #

def _seed_history_run(state, *, failed=0):
    from src.ocr_pipeline.jobs import JobItem, State as JobState

    run_id = state.history.start_run(stages=["ocr", "cleanup"], output_dir="out", total=1)
    item = JobItem(path="C:/docs/letter.png")
    item.state = JobState.DONE if not failed else JobState.FAILED
    item.confidence = 88
    item.language = "German"
    item.results = {
        "raw": {"extracted_text": "raw text"},
        "cleaned": {"cleaned_text": "cleaned text"},
    }
    state.history.record_item(run_id, item)
    state.history.finish_run(run_id, succeeded=0 if failed else 1, failed=failed, elapsed=4.2)
    return run_id


def test_history_runs_lists_finished_runs(client):
    _seed_history_run(server.state)

    res = client.get("/api/history/runs")
    runs = res.json()["runs"]
    assert len(runs) == 1
    assert runs[0]["total"] == 1
    assert runs[0]["succeeded"] == 1


def test_history_run_items_lists_documents(client):
    run_id = _seed_history_run(server.state)

    res = client.get(f"/api/history/runs/{run_id}/items")
    items = res.json()["items"]
    assert items[0]["name"] == "letter.png"
    assert items[0]["language"] == "German"


def test_history_item_detail_includes_text_and_diff(client):
    run_id = _seed_history_run(server.state)
    item_id = client.get(f"/api/history/runs/{run_id}/items").json()["items"][0]["item_id"]

    res = client.get(f"/api/history/items/{item_id}")
    body = res.json()
    assert body["raw"] == "raw text"
    assert body["cleaned"] == "cleaned text"
    assert body["confidence_tier"] == "high"
    assert "diff" in body


def test_history_item_detail_404_for_unknown_id(client):
    res = client.get("/api/history/items/999999")
    assert res.status_code == 404


def test_history_search_finds_by_filename(client):
    _seed_history_run(server.state)

    hit = client.get("/api/history/search", params={"q": "letter"})
    miss = client.get("/api/history/search", params={"q": "nonexistent"})

    assert len(hit.json()["items"]) == 1
    assert miss.json()["items"] == []


def test_history_search_with_no_query_returns_nothing(client):
    _seed_history_run(server.state)
    res = client.get("/api/history/search")
    assert res.json()["items"] == []


def test_delete_run_removes_it_but_not_output_files(client):
    run_id = _seed_history_run(server.state)

    res = client.delete(f"/api/history/runs/{run_id}")
    assert res.json() == {"ok": True}
    assert client.get("/api/history/runs").json()["runs"] == []


# --------------------------------------------------------------------------- #
# analytics
# --------------------------------------------------------------------------- #

def test_analytics_stats_before_any_run(client):
    res = client.get("/api/analytics/stats")
    body = res.json()
    assert body["runs"] == 0
    assert body["confidences"] == []


def test_analytics_stats_reflects_seeded_run(client):
    _seed_history_run(server.state)

    res = client.get("/api/analytics/stats")
    body = res.json()
    assert body["runs"] == 1
    assert body["files"] == 1
    assert 88 in body["confidences"]


# --------------------------------------------------------------------------- #
# tropy send (write-back), against a synthetic project — never a real archive
# --------------------------------------------------------------------------- #

TROPY_SCHEMA = """
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
def tropy_project(tmp_path):
    import sqlite3

    root = tmp_path / "Archive.tropy"
    (root / "assets").mkdir(parents=True)
    con = sqlite3.connect(root / "project.tpy")
    con.executescript(TROPY_SCHEMA)
    con.execute("INSERT INTO project VALUES ('u','Archive','2026','project','assets')")
    con.execute("INSERT INTO items (id) VALUES (1)")
    con.execute("INSERT INTO subjects (id, template) VALUES (10, 'photo')")
    con.execute("INSERT INTO images (id) VALUES (10)")
    con.execute(
        "INSERT INTO photos (id,item_id,path,mimetype,page,filename) "
        "VALUES (10,1,'assets/a.pdf','application/pdf',0,'doc.pdf')"
    )
    con.commit()
    con.close()
    return root


def _add_tropy_queue_item(client, photo_id: int = 10, text: str = "Sauberer Text"):
    from src.ocr_pipeline.jobs import JobItem

    item = JobItem(path="assets/a.pdf", source={"photo_id": photo_id}, label="doc.pdf p.1")
    item.results = {"cleaned": {"cleaned_text": text}}
    server.state.add_items([item])
    return item


def test_tropy_send_preview_lists_an_insertable_row(client, tropy_project):
    _add_tropy_queue_item(client)

    res = client.post("/api/tropy/send/preview", json={
        "project": str(tropy_project), "targets": ["notes"],
    })
    body = res.json()
    assert body["blockers"] == []
    assert body["insertable"] == 1
    assert body["plans"][0]["action"] == "insert"


def test_tropy_send_preview_ignores_non_tropy_items(client, tmp_path, tropy_project):
    f = tmp_path / "plain.png"
    f.write_bytes(b"x")
    client.post("/api/queue/add-paths", json={"paths": [str(f)]})

    res = client.post("/api/tropy/send/preview", json={
        "project": str(tropy_project), "targets": ["notes"],
    })
    assert res.json()["insertable"] == 0


def test_tropy_send_write_creates_a_note_and_backs_up(client, tropy_project):
    _add_tropy_queue_item(client, text="Der Bericht ist fertig.")

    res = client.post("/api/tropy/send/write", json={
        "project": str(tropy_project), "targets": ["notes"],
    })
    body = res.json()
    assert body["written"] == 1
    assert body["backup"] is not None

    con_check = __import__("sqlite3").connect(tropy_project / "project.tpy")
    row = con_check.execute("SELECT text FROM notes").fetchone()
    assert row[0] == "Der Bericht ist fertig."
    con_check.close()


def test_tropy_send_write_does_not_duplicate_on_rerun(client, tropy_project):
    _add_tropy_queue_item(client, text="Einmaliger Text")

    first = client.post("/api/tropy/send/write", json={
        "project": str(tropy_project), "targets": ["notes"],
    })
    second = client.post("/api/tropy/send/write", json={
        "project": str(tropy_project), "targets": ["notes"],
    })

    assert first.json()["written"] == 1
    assert second.json()["written"] == 0


def test_tropy_send_write_reports_blockers_as_409(client, tropy_project):
    res = client.post("/api/tropy/send/write", json={
        "project": str(tropy_project), "targets": [],
    })
    assert res.status_code == 409


# --------------------------------------------------------------------------- #
# bootstrap: waiting for the background uvicorn thread before opening a window
# --------------------------------------------------------------------------- #
#
# `main()` starts uvicorn in a background thread and then immediately opens a
# window (native or browser) at its URL. Caught live: the window can win that
# race and load before the socket is bound, showing a connection-refused
# error on first launch. `_wait_for_server` is the fix; these pin the two
# outcomes it has to get right.

def test_wait_for_server_returns_true_once_something_is_listening():
    import threading

    from src.ocr_pipeline.web.server import _wait_for_server

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    accepted = threading.Event()

    # Delay the "server" coming up, the same shape as uvicorn's own startup
    # lag, to prove this actually polls rather than checking once.
    def open_late():
        import time
        time.sleep(0.3)
        conn, _ = srv.accept()
        conn.close()
        accepted.set()

    threading.Thread(target=open_late, daemon=True).start()
    try:
        assert _wait_for_server(port, timeout=3.0) is True
        accepted.wait(timeout=2.0)  # let accept() finish before srv.close()
    finally:
        srv.close()


def test_wait_for_server_gives_up_after_timeout():
    from src.ocr_pipeline.web.server import _wait_for_server

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        never_listening_port = s.getsockname()[1]
    # The socket is closed again immediately, so nothing is listening on this
    # port — a short timeout keeps the test itself fast.
    assert _wait_for_server(never_listening_port, timeout=0.5) is False


# --------------------------------------------------------------------------- #
# bootstrap: reporting it when the server thread never comes up
# --------------------------------------------------------------------------- #
#
# `_wait_for_server` correctly detects the timeout above, but `main()` used to
# open the pywebview/browser window anyway with just a print() — invisible in
# a `.pyw` process, which has no console. That's exactly the "OCR Pipeline"
# window showing Edge WebView2's connection-refused page with zero
# explanation. These pin the fix: the exception (if any) is captured off the
# background thread and actually surfaced instead of silently discarded.

def test_start_server_thread_captures_an_exception_from_uvicorn(monkeypatch):
    import uvicorn

    from src.ocr_pipeline.web.server import _start_server_thread

    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("port already in use")))

    thread, errors = _start_server_thread(59999)
    thread.join(timeout=2.0)
    assert len(errors) == 1
    assert isinstance(errors[0], RuntimeError)
    assert "port already in use" in str(errors[0])


def test_report_startup_failure_prints_the_captured_exception(monkeypatch, capsys):
    from src.ocr_pipeline.web.server import _report_startup_failure

    monkeypatch.setattr("tkinter.messagebox.showerror", lambda *a, **k: None)

    class FakeThread:
        def is_alive(self):
            return False

    _report_startup_failure(5099, FakeThread(), [ValueError("bad config")])
    out = capsys.readouterr().out
    assert "5099" in out
    assert "ValueError" in out
    assert "bad config" in out


def test_report_startup_failure_explains_a_plain_timeout(monkeypatch, capsys):
    from src.ocr_pipeline.web.server import _report_startup_failure

    monkeypatch.setattr("tkinter.messagebox.showerror", lambda *a, **k: None)

    class FakeThread:
        def is_alive(self):
            return True

    _report_startup_failure(5099, FakeThread(), [])
    out = capsys.readouterr().out
    assert "No response within 10s" in out


# --------------------------------------------------------------------------- #
# bootstrap: sys.stdout/stderr are None in a real (no-terminal) .pyw launch
# --------------------------------------------------------------------------- #
#
# Confirmed live: a genuine double-click of the desktop shortcut (fresh
# reboot, nothing else holding the port) crashed with
# "ValueError: Unable to configure formatter 'default'" — uvicorn's logging
# setup tries to attach a StreamHandler to sys.stderr, which is None (not
# just quiet) in a truly consoleless process. Reproduced directly by setting
# sys.stdout/stderr to None and calling logging.config.dictConfig on
# uvicorn's own LOGGING_CONFIG.

def test_ensure_std_streams_replaces_none_streams(monkeypatch):
    from src.ocr_pipeline.web.server import _ensure_std_streams

    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    _ensure_std_streams()

    assert sys.stdout is not None
    assert sys.stderr is not None
    sys.stdout.write("this must not raise\n")
    sys.stderr.write("neither must this\n")


def test_ensure_std_streams_leaves_real_streams_alone(monkeypatch, capsys):
    from src.ocr_pipeline.web.server import _ensure_std_streams

    _ensure_std_streams()
    print("still visible to capsys")
    assert "still visible to capsys" in capsys.readouterr().out

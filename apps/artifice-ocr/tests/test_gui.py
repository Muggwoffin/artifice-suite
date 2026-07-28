"""Tests for the job runner, history store and comparison-view helpers.

These cover the non-visual layers the GUI is built on. Widget construction is
exercised separately by the smoke test; what matters here is that the runner
threads, the event stream and the history schema behave.
"""

import queue
import time
from unittest.mock import patch

import pytest

from artifice_ocr.history import HistoryStore
from artifice_ocr.jobs import JobItem, JobRunner, State


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _ocr(text="raw text", skipped=False):
    data = {"source_file": "x", "stage": "raw_ocr", "extracted_text": text,
            "_elapsed": 0.01}
    if skipped:
        data["_skipped"] = True
    return data


def _cleaned(text="cleaned text", skipped=False):
    data = {"source_file": "x", "stage": "cleaned", "cleaned_text": text,
            "raw_text": "raw text", "_elapsed": 0.01}
    if skipped:
        data["_skipped"] = True
    return data


def _translated(text="translated text", confidence=88):
    return {
        "source_file": "x", "stage": "translated", "translated_text": text,
        "cleaned_text": "cleaned text", "source_language_name": "German",
        "confidence": {"overall_score": confidence},
        "_elapsed": 0.01,
    }


def _drain(runner, timeout=10.0):
    """Run to completion and return the collected events."""
    deadline = time.monotonic() + timeout
    events = []
    while time.monotonic() < deadline:
        try:
            event = runner.events.get(timeout=0.1)
        except queue.Empty:
            if not runner.is_running:
                break
            continue
        events.append(event)
        if event.kind == "run_finished":
            break
    else:
        pytest.fail("runner did not finish within timeout")
    return events


# --------------------------------------------------------------------------- #
# JobRunner
# --------------------------------------------------------------------------- #

@patch("artifice_ocr.jobs.run_translate_step", return_value=_translated())
@patch("artifice_ocr.jobs.run_cleanup_step", return_value=_cleaned())
@patch("artifice_ocr.jobs.run_ocr_step", return_value=_ocr())
def test_runner_completes_all_stages(mock_ocr, mock_clean, mock_trans, tmp_path):
    items = [JobItem(path="a.png"), JobItem(path="b.png")]
    runner = JobRunner(items, str(tmp_path),
                       stages={"ocr", "cleanup", "translate"})
    runner.start()
    events = _drain(runner)

    assert all(i.state is State.DONE for i in items)
    for item in items:
        assert item.stages["ocr"].state is State.DONE
        assert item.stages["cleanup"].state is State.DONE
        assert item.stages["translate"].state is State.DONE
        assert item.confidence == 88
        assert item.language == "German"

    kinds = [e.kind for e in events]
    assert kinds[0] == "run_started"
    assert kinds[-1] == "run_finished"
    assert kinds.count("item_finished") == 2
    assert events[-1].payload["done"] == 2
    assert events[-1].payload["failed"] == 0


@patch("artifice_ocr.jobs.run_cleanup_step", return_value=_cleaned())
@patch("artifice_ocr.jobs.run_ocr_step", return_value=_ocr())
def test_runner_honours_stage_selection(mock_ocr, mock_clean, tmp_path):
    item = JobItem(path="a.png")
    runner = JobRunner([item], str(tmp_path), stages={"ocr", "cleanup"})
    runner.start()
    _drain(runner)

    assert item.state is State.DONE
    assert item.stages["translate"].state is State.SKIPPED
    assert "translated" not in item.results


@patch("artifice_ocr.jobs.run_cleanup_step", return_value=_cleaned())
@patch("artifice_ocr.jobs.run_ocr_step",
       side_effect=RuntimeError("LM Studio unreachable"))
def test_runner_marks_failure_without_killing_batch(mock_ocr, mock_clean, tmp_path):
    items = [JobItem(path="a.png"), JobItem(path="b.png")]
    runner = JobRunner(items, str(tmp_path), stages={"ocr", "cleanup"})
    runner.start()
    events = _drain(runner)

    assert all(i.state is State.FAILED for i in items)
    assert all("LM Studio unreachable" in i.error for i in items)
    assert events[-1].payload["failed"] == 2
    # the batch still completed rather than raising out of the worker
    assert events[-1].kind == "run_finished"


@patch("artifice_ocr.jobs.run_cleanup_step", return_value=_cleaned())
@patch("artifice_ocr.jobs.run_ocr_step", return_value=_ocr())
def test_runner_skip_marks_item_skipped(mock_ocr, mock_clean, tmp_path):
    item = JobItem(path="a.png")
    runner = JobRunner([item], str(tmp_path), stages={"ocr", "cleanup"})
    runner.skip(item)  # skip before it is picked up
    runner.start()
    _drain(runner)

    assert item.state is State.SKIPPED
    mock_ocr.assert_not_called()


@patch("artifice_ocr.jobs.run_cleanup_step", return_value=_cleaned())
@patch("artifice_ocr.jobs.run_ocr_step", return_value=_ocr())
def test_runner_cancel_stops_the_run(mock_ocr, mock_clean, tmp_path):
    items = [JobItem(path=f"{i}.png") for i in range(6)]
    runner = JobRunner(items, str(tmp_path), stages={"ocr", "cleanup"})
    runner.cancel()
    runner.start()
    _drain(runner)

    assert all(i.state is State.CANCELLED for i in items)


@patch("artifice_ocr.jobs.run_cleanup_step", return_value=_cleaned(skipped=True))
@patch("artifice_ocr.jobs.run_ocr_step", return_value=_ocr(skipped=True))
def test_runner_reports_resumed_stages_as_skipped(mock_ocr, mock_clean, tmp_path):
    item = JobItem(path="a.png")
    runner = JobRunner([item], str(tmp_path), stages={"ocr", "cleanup"})
    runner.start()
    _drain(runner)

    assert item.state is State.DONE
    assert item.stages["ocr"].state is State.SKIPPED
    assert item.stages["cleanup"].state is State.SKIPPED


@patch("artifice_ocr.jobs.run_cleanup_step", return_value=_cleaned())
@patch("artifice_ocr.jobs.run_ocr_step", return_value=_ocr())
def test_runner_pause_blocks_then_resumes(mock_ocr, mock_clean, tmp_path):
    items = [JobItem(path=f"{i}.png") for i in range(4)]
    runner = JobRunner(items, str(tmp_path), stages={"ocr", "cleanup"},
                       max_workers=1)
    runner.pause()
    runner.start()
    time.sleep(0.3)
    assert runner.is_paused
    assert all(i.state is not State.DONE for i in items)

    runner.unpause()
    _drain(runner)
    assert all(i.state is State.DONE for i in items)


def test_job_item_reset_clears_previous_state():
    item = JobItem(path="a.png")
    item.state = State.FAILED
    item.error = "boom"
    item.confidence = 20
    item.stages["ocr"].chars = 999

    item.reset({"ocr", "cleanup"})

    assert item.state is State.PENDING
    assert item.error == ""
    assert item.confidence is None
    assert item.stages["ocr"].chars == 0
    assert item.stages["ocr"].state is State.PENDING
    assert item.stages["translate"].state is State.SKIPPED


# --------------------------------------------------------------------------- #
# HistoryStore
# --------------------------------------------------------------------------- #

@pytest.fixture
def store(tmp_path):
    s = HistoryStore(tmp_path / "history.db")
    yield s
    s.close()


def _finished_item(confidence=90, state=State.DONE):
    item = JobItem(path="C:/docs/letter.png")
    item.state = state
    item.confidence = confidence
    item.language = "German"
    item.stages["ocr"].state = State.DONE
    item.stages["ocr"].chars = 1200
    item.stages["ocr"].elapsed = 4.0
    item.stages["cleanup"].state = State.DONE
    item.stages["cleanup"].chars = 1150
    item.stages["cleanup"].elapsed = 2.0
    item.results = {
        "raw": {"extracted_text": "raw"},
        "cleaned": {"cleaned_text": "clean"},
        "translated": {"translated_text": "trans"},
    }
    return item


def test_history_round_trip(store):
    run_id = store.start_run(stages=["ocr", "cleanup"], output_dir="out", total=1)
    store.record_item(run_id, _finished_item())
    store.finish_run(run_id, succeeded=1, failed=0, elapsed=6.0)

    runs = store.list_runs()
    assert len(runs) == 1
    assert runs[0]["total"] == 1
    assert runs[0]["succeeded"] == 1
    assert runs[0]["finished"] is not None

    items = store.list_items(run_id)
    assert len(items) == 1
    assert items[0]["name"] == "letter.png"
    assert items[0]["language"] == "German"
    assert items[0]["confidence"] == 90
    assert items[0]["raw_text"] == "raw"
    assert items[0]["translated_text"] == "trans"


def test_history_search_and_delete(store):
    run_id = store.start_run(stages=["ocr"], output_dir="out", total=1)
    store.record_item(run_id, _finished_item())
    store.finish_run(run_id, succeeded=1, failed=0, elapsed=1.0)

    assert len(store.search_items("letter")) == 1
    assert len(store.search_items("nothing-matches")) == 0

    store.delete_run(run_id)
    assert store.list_runs() == []
    assert store.list_items(run_id) == []


def test_history_stats_aggregates_throughput_and_confidence(store):
    run_id = store.start_run(stages=["ocr", "cleanup"], output_dir="out", total=2)
    store.record_item(run_id, _finished_item(confidence=90))
    store.record_item(run_id, _finished_item(confidence=40))
    store.finish_run(run_id, succeeded=2, failed=0, elapsed=12.0)

    stats = store.stats()
    assert stats["runs"] == 1
    assert stats["files"] == 2
    assert sorted(stats["confidences"]) == [40, 90]
    # 1200 chars over 4s, twice
    assert stats["stage_totals"]["ocr"]["chars"] == 2400
    assert stats["stage_totals"]["ocr"]["elapsed"] == 8.0
    assert stats["stage_totals"]["ocr"]["n"] == 2
    assert len(stats["recent"]) == 1


def test_history_survives_item_with_no_results(store):
    run_id = store.start_run(stages=["ocr"], output_dir="out", total=1)
    item = JobItem(path="broken.png")
    item.state = State.FAILED
    item.error = "RuntimeError: nope"
    store.record_item(run_id, item)

    rows = store.list_items(run_id)
    assert rows[0]["state"] == "failed"
    assert rows[0]["raw_text"] is None
    assert rows[0]["confidence"] is None


def test_history_records_the_pdf_page_a_tropy_item_came_from(store):
    run_id = store.start_run(stages=["ocr"], output_dir="out", total=1)
    item = _finished_item()
    item.page = 4
    store.record_item(run_id, item)

    row = store.list_items(run_id)[0]
    assert row["page"] == 4
    assert row["edited"] == 0
    assert row["edited_at"] is None


def test_history_update_raw_text_marks_the_row_edited(store):
    run_id = store.start_run(stages=["ocr"], output_dir="out", total=1)
    store.record_item(run_id, _finished_item())
    item_id = store.list_items(run_id)[0]["item_id"]

    store.update_raw_text(item_id, "corrected transcription")

    row = store.get_item(item_id)
    assert row["raw_text"] == "corrected transcription"
    assert row["edited"] == 1
    assert row["edited_at"] is not None
    # only raw_text changed — cleaned/translated are left alone
    assert row["cleaned_text"] == "clean"
    assert row["translated_text"] == "trans"


def test_history_migrates_a_database_missing_the_new_columns(tmp_path):
    """A real on-disk history.db from before this feature shipped has no
    page/edited/edited_at columns — HistoryStore must add them in place
    (never drop/recreate) so past runs survive."""
    import sqlite3

    db_path = tmp_path / "history.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT, started TEXT NOT NULL,
            finished TEXT, stages TEXT NOT NULL, output_dir TEXT NOT NULL,
            doc_type TEXT, ocr_model TEXT, cleanup_model TEXT, translate_model TEXT,
            total INTEGER NOT NULL DEFAULT 0, succeeded INTEGER NOT NULL DEFAULT 0,
            failed INTEGER NOT NULL DEFAULT 0, elapsed REAL NOT NULL DEFAULT 0
        );
        CREATE TABLE run_items (
            item_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER NOT NULL,
            source_file TEXT NOT NULL, name TEXT NOT NULL, state TEXT NOT NULL,
            language TEXT, confidence INTEGER, error TEXT, stage_json TEXT NOT NULL,
            raw_text TEXT, cleaned_text TEXT, translated_text TEXT, created TEXT NOT NULL
        );
        """
    )
    conn.execute(
        "INSERT INTO runs (started, stages, output_dir, total) VALUES (?, ?, ?, ?)",
        ("2020-01-01T00:00:00", "ocr", "out", 1),
    )
    conn.execute(
        "INSERT INTO run_items "
        "(run_id, source_file, name, state, stage_json, raw_text, created) "
        "VALUES (1, 'a.png', 'a.png', 'done', '{}', 'old raw text', '2020-01-01T00:00:00')"
    )
    conn.commit()
    conn.close()

    store = HistoryStore(db_path)
    try:
        rows = store.list_items(1)
        assert len(rows) == 1
        assert rows[0]["raw_text"] == "old raw text"
        assert rows[0]["page"] is None
        assert rows[0]["edited"] == 0
        assert rows[0]["edited_at"] is None

        store.update_raw_text(rows[0]["item_id"], "fixed")
        assert store.get_item(rows[0]["item_id"])["raw_text"] == "fixed"
    finally:
        store.close()


# --------------------------------------------------------------------------- #
# comparison-view helpers
# --------------------------------------------------------------------------- #

def test_diff_ranges_flags_changed_words():
    from artifice_ocr.gui.widgets.compare_view import _diff_ranges

    raw = "the quick br0wn fox"
    cleaned = "the quick brown fox"
    raw_ranges, clean_ranges = _diff_ranges(raw, cleaned)

    assert raw_ranges and clean_ranges
    start, end, tag = clean_ranges[0]
    assert cleaned[start:end].strip() == "brown"
    assert tag == "replace_"


def test_diff_ranges_identical_text_has_no_highlights():
    from artifice_ocr.gui.widgets.compare_view import _diff_ranges

    text = "identical in both panes"
    assert _diff_ranges(text, text) == ([], [])


def test_marker_ranges_finds_uncertainty_markers():
    from artifice_ocr.gui.widgets.compare_view import _marker_ranges

    text = "The date is [illegible] and the name is unclear."
    ranges = _marker_ranges(text)
    found = {text[s:e].lower() for s, e, _ in ranges}

    assert "[illegible]" in found
    assert "unclear" in found
    assert all(tag == "marker" for _, _, tag in ranges)


# --------------------------------------------------------------------------- #
# image pane — pure DPI math (no Tk/display needed)
# --------------------------------------------------------------------------- #

def test_dpi_for_zoom_matches_base_dpi_at_zoom_one():
    from artifice_ocr.gui.widgets.image_pane import BASE_DPI, _dpi_for_zoom

    assert _dpi_for_zoom(600, 800, 1.0) == BASE_DPI


def test_dpi_for_zoom_scales_linearly_below_the_cap():
    from artifice_ocr.gui.widgets.image_pane import _dpi_for_zoom

    assert _dpi_for_zoom(600, 800, 2.0) == pytest.approx(300.0)


def test_dpi_for_zoom_caps_the_rendered_long_edge():
    from artifice_ocr.gui.widgets.image_pane import _dpi_for_zoom

    dpi = _dpi_for_zoom(3000, 4000, 4.0, base_dpi=150, max_long_edge=4000)
    long_edge_px = 4000 / 72 * dpi
    assert long_edge_px == pytest.approx(4000, rel=1e-6)


# --------------------------------------------------------------------------- #
# History's editable raw pane + source-image pane (widget-level)
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def _widget_root():
    """A bare Tk root for widget-construction tests — separate from the
    module-scoped `_gui_root` used by the full App smoke tests below.

    Module-scoped rather than per-test: repeated Tk() creation/destruction
    in one process is exactly the fragility `_gui_root`'s own docstring
    warns about ("tk wasn't installed properly"), observed here too before
    this was made module-scoped.
    """
    tk_mod = pytest.importorskip("tkinter")
    try:
        root = tk_mod.Tk()
        root.withdraw()
    except tk_mod.TclError as exc:  # pragma: no cover - headless CI
        pytest.skip(f"no display: {exc}")

    from artifice_ocr.gui import theme
    theme.apply(root)

    yield root
    root.destroy()


def test_preview_style_compareview_has_no_image_or_editable_raw(_widget_root):
    """The plain tab (`with_image`/`editable_raw` both default off) must stay
    exactly as it was — this is what the live-queue Preview tab uses."""
    from artifice_ocr.gui.widgets.compare_view import CompareView

    view = CompareView(_widget_root)

    assert view.image is None
    assert view.panes["raw"].editable is False
    assert view.panes["raw"].save_btn is None
    assert str(view.panes["raw"].text["state"]) == "disabled"


def test_history_style_compareview_mounts_image_pane_and_editable_raw(_widget_root):
    from artifice_ocr.gui.widgets.compare_view import CompareView

    view = CompareView(_widget_root, with_image=True, editable_raw=True)

    assert view.image is not None
    assert view.panes["raw"].editable is True
    assert str(view.panes["raw"].text["state"]) == "normal"
    # only the raw pane is editable — cleaned/translated stay read-only
    assert view.panes["cleaned"].editable is False
    assert view.panes["translated"].editable is False


def test_editable_raw_pane_tracks_dirty_state_and_saves(_widget_root):
    from artifice_ocr.gui.widgets.compare_view import CompareView

    saved = []
    view = CompareView(_widget_root, editable_raw=True, on_save_raw=saved.append)
    view.show(title="doc", raw="original raw text", cleaned="cleaned text")

    raw_pane = view.panes["raw"]
    assert str(raw_pane.save_btn["state"]) == "disabled"

    raw_pane.text.delete("1.0", "end")
    raw_pane.text.insert("1.0", "corrected raw text")
    raw_pane._on_modified()
    assert str(raw_pane.save_btn["state"]) == "normal"

    raw_pane._save()
    assert saved == ["corrected raw text"]
    assert str(raw_pane.save_btn["state"]) == "disabled"
    # the correction is reflected back into the view's own state
    assert view._current["raw"] == "corrected raw text"


def test_editable_raw_pane_save_does_not_reset_scroll_or_cursor(_widget_root):
    """Re-rendering after a save must not blow away the widget the user was
    just typing in — only panes whose content actually changed get touched."""
    from artifice_ocr.gui.widgets.compare_view import CompareView

    view = CompareView(_widget_root, editable_raw=True, on_save_raw=lambda t: None)
    view.show(title="doc", raw="original", cleaned="cleaned")

    raw_pane = view.panes["raw"]
    raw_pane.text.mark_set("insert", "1.0+3c")
    raw_pane.text.delete("1.0", "end")
    raw_pane.text.insert("1.0", "original")  # content ends up unchanged
    raw_pane._save()

    assert raw_pane.text.get("1.0", "end-1c") == "original"


def test_image_pane_falls_back_to_placeholder_for_a_missing_file(_widget_root, tmp_path):
    from artifice_ocr.gui.widgets.image_pane import ImagePane

    pane = ImagePane(_widget_root)
    pane.load(str(tmp_path / "does-not-exist.png"))

    assert pane._page is None
    assert pane.canvas.find_withtag("image") == ()


def test_image_pane_renders_a_real_pdf_page(_widget_root, tmp_path):
    fitz = pytest.importorskip("fitz")

    pdf_path = tmp_path / "page.pdf"
    doc = fitz.open()
    doc.new_page(width=200, height=300)
    doc.new_page(width=200, height=300)
    doc.save(str(pdf_path))
    doc.close()

    from artifice_ocr.gui.widgets.image_pane import ImagePane

    pane = ImagePane(_widget_root)
    pane.load(str(pdf_path), page=1)
    _widget_root.update_idletasks()

    assert pane._page is not None
    assert pane.canvas.find_withtag("image") != ()
    assert pane._photo is not None

    pane.clear()
    assert pane._page is None
    assert pane.canvas.find_withtag("image") == ()


# --------------------------------------------------------------------------- #
# end-to-end: runner -> event pump -> queue table -> history
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def _gui_root(tmp_path_factory):
    """One Tk root for the whole module.

    Creating and destroying a root per test intermittently fails on Windows
    with "tk wasn't installed properly" — repeated root creation in a single
    process is fragile, so the root is made once and reset between tests.
    """
    tk = pytest.importorskip("tkinter")
    try:
        from artifice_ocr import config
        from artifice_ocr.gui.app import App
    except Exception as exc:  # pragma: no cover - missing display/tkinterdnd2
        pytest.skip(f"GUI unavailable: {exc}")

    config.load_config()
    config.apply_overrides(
        {"history_db": str(tmp_path_factory.mktemp("gui") / "history.db")}
    )
    try:
        instance = App()
    except tk.TclError as exc:  # pragma: no cover - headless CI
        pytest.skip(f"no display: {exc}")

    yield instance

    try:
        instance.history.close()
        instance.destroy()
    except Exception:
        pass


@pytest.fixture
def app(_gui_root, tmp_path):
    """The shared App, reset to a clean state with a throwaway history db."""
    import tkinter as tk

    from artifice_ocr.history import HistoryStore

    instance = _gui_root
    instance.main_view.queue.clear()
    instance.main_view.log.configure(state=tk.NORMAL)
    instance.main_view.log.delete("1.0", tk.END)
    instance.main_view.log.configure(state=tk.DISABLED)
    instance.runner = None
    instance.run_id = None
    instance._run_items = []

    instance.history.close()
    instance.history = HistoryStore(tmp_path / "history.db")
    instance.history_view.history = instance.history
    instance.analytics_view.history = instance.history

    instance.output_var.set(str(tmp_path / "out"))
    instance.var_ocr.set(True)
    instance.var_cleanup.set(True)
    instance.var_translate.set(False)
    instance.var_force.set(False)

    return instance


def _pump_until_idle(app, timeout=10.0):
    """Drive the tk loop until the runner finishes."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.update_idletasks()
        app.update()
        if app.runner is None and app.run_id is None:
            return
        time.sleep(0.02)
    pytest.fail("run did not complete within timeout")


@patch("artifice_ocr.jobs.run_translate_step", return_value=_translated())
@patch("artifice_ocr.jobs.run_cleanup_step", return_value=_cleaned())
@patch("artifice_ocr.jobs.run_ocr_step", return_value=_ocr())
def test_end_to_end_run_updates_queue_and_history(mock_o, mock_c, mock_t, app):
    app.main_view.queue.add_paths(["a.png", "b.png"])
    app.var_translate.set(True)

    app.start_run()
    _pump_until_idle(app)

    items = app.main_view.queue.items
    assert all(i.state is State.DONE for i in items)

    # the Treeview actually reflects the finished state
    row = app.main_view.queue.tree.item(str(id(items[0])))
    assert "done" in row["tags"]
    assert row["values"][0] == "a.png"

    # and the run was persisted
    runs = app.history.list_runs()
    assert len(runs) == 1
    assert runs[0]["succeeded"] == 2
    assert runs[0]["finished"] is not None
    assert len(app.history.list_items(runs[0]["run_id"])) == 2

    # preview is populated from the in-memory results
    app.preview_item(items[0])
    assert "translated text" in app.preview_view.panes["translated"].text.get("1.0", "end")


def test_queue_keeps_pages_sharing_one_pdf_but_drops_true_duplicates(app):
    """Tropy pages share a path — identity has to be the output stem."""
    pdf = "C:/archive/assets/abc123.pdf"
    pages = [
        JobItem(path=pdf, page=n, output_stem=f"Item/KV-2-1234_p{n + 1:04d}",
                label=f"KV-2-1234.pdf  p.{n + 1}")
        for n in range(3)
    ]

    assert app.main_view.queue.add_items(pages) == 3
    assert len(app.main_view.queue.tree.get_children()) == 3

    # re-adding the same pages is a no-op
    assert app.main_view.queue.add_items(list(pages)) == 0

    # the row shows the page label, not the checksum filename
    first = app.main_view.queue.tree.item(str(id(pages[0])))
    assert first["values"][0] == "KV-2-1234.pdf  p.1"


@patch("artifice_ocr.jobs.run_cleanup_step", return_value=_cleaned())
@patch("artifice_ocr.jobs.run_ocr_step", side_effect=RuntimeError("boom"))
def test_end_to_end_failure_is_recorded_not_raised(mock_o, mock_c, app):
    app.main_view.queue.add_paths(["a.png"])

    app.start_run()
    _pump_until_idle(app)

    item = app.main_view.queue.items[0]
    assert item.state is State.FAILED

    runs = app.history.list_runs()
    assert runs[0]["failed"] == 1
    rows = app.history.list_items(runs[0]["run_id"])
    assert "boom" in rows[0]["error"]

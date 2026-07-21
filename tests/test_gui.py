"""Tests for the job runner, history store and comparison-view helpers.

These cover the non-visual layers the GUI is built on. Widget construction is
exercised separately by the smoke test; what matters here is that the runner
threads, the event stream and the history schema behave.
"""

import queue
import time
from unittest.mock import patch

import pytest

from src.ocr_pipeline.history import HistoryStore
from src.ocr_pipeline.jobs import JobItem, JobRunner, State


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

@patch("src.ocr_pipeline.jobs.run_translate_step", return_value=_translated())
@patch("src.ocr_pipeline.jobs.run_cleanup_step", return_value=_cleaned())
@patch("src.ocr_pipeline.jobs.run_ocr_step", return_value=_ocr())
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


@patch("src.ocr_pipeline.jobs.run_cleanup_step", return_value=_cleaned())
@patch("src.ocr_pipeline.jobs.run_ocr_step", return_value=_ocr())
def test_runner_honours_stage_selection(mock_ocr, mock_clean, tmp_path):
    item = JobItem(path="a.png")
    runner = JobRunner([item], str(tmp_path), stages={"ocr", "cleanup"})
    runner.start()
    _drain(runner)

    assert item.state is State.DONE
    assert item.stages["translate"].state is State.SKIPPED
    assert "translated" not in item.results


@patch("src.ocr_pipeline.jobs.run_cleanup_step", return_value=_cleaned())
@patch("src.ocr_pipeline.jobs.run_ocr_step",
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


@patch("src.ocr_pipeline.jobs.run_cleanup_step", return_value=_cleaned())
@patch("src.ocr_pipeline.jobs.run_ocr_step", return_value=_ocr())
def test_runner_skip_marks_item_skipped(mock_ocr, mock_clean, tmp_path):
    item = JobItem(path="a.png")
    runner = JobRunner([item], str(tmp_path), stages={"ocr", "cleanup"})
    runner.skip(item)  # skip before it is picked up
    runner.start()
    _drain(runner)

    assert item.state is State.SKIPPED
    mock_ocr.assert_not_called()


@patch("src.ocr_pipeline.jobs.run_cleanup_step", return_value=_cleaned())
@patch("src.ocr_pipeline.jobs.run_ocr_step", return_value=_ocr())
def test_runner_cancel_stops_the_run(mock_ocr, mock_clean, tmp_path):
    items = [JobItem(path=f"{i}.png") for i in range(6)]
    runner = JobRunner(items, str(tmp_path), stages={"ocr", "cleanup"})
    runner.cancel()
    runner.start()
    _drain(runner)

    assert all(i.state is State.CANCELLED for i in items)


@patch("src.ocr_pipeline.jobs.run_cleanup_step", return_value=_cleaned(skipped=True))
@patch("src.ocr_pipeline.jobs.run_ocr_step", return_value=_ocr(skipped=True))
def test_runner_reports_resumed_stages_as_skipped(mock_ocr, mock_clean, tmp_path):
    item = JobItem(path="a.png")
    runner = JobRunner([item], str(tmp_path), stages={"ocr", "cleanup"})
    runner.start()
    _drain(runner)

    assert item.state is State.DONE
    assert item.stages["ocr"].state is State.SKIPPED
    assert item.stages["cleanup"].state is State.SKIPPED


@patch("src.ocr_pipeline.jobs.run_cleanup_step", return_value=_cleaned())
@patch("src.ocr_pipeline.jobs.run_ocr_step", return_value=_ocr())
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


# --------------------------------------------------------------------------- #
# comparison-view helpers
# --------------------------------------------------------------------------- #

def test_diff_ranges_flags_changed_words():
    from src.ocr_pipeline.gui.widgets.compare_view import _diff_ranges

    raw = "the quick br0wn fox"
    cleaned = "the quick brown fox"
    raw_ranges, clean_ranges = _diff_ranges(raw, cleaned)

    assert raw_ranges and clean_ranges
    start, end, tag = clean_ranges[0]
    assert cleaned[start:end].strip() == "brown"
    assert tag == "replace_"


def test_diff_ranges_identical_text_has_no_highlights():
    from src.ocr_pipeline.gui.widgets.compare_view import _diff_ranges

    text = "identical in both panes"
    assert _diff_ranges(text, text) == ([], [])


def test_marker_ranges_finds_uncertainty_markers():
    from src.ocr_pipeline.gui.widgets.compare_view import _marker_ranges

    text = "The date is [illegible] and the name is unclear."
    ranges = _marker_ranges(text)
    found = {text[s:e].lower() for s, e, _ in ranges}

    assert "[illegible]" in found
    assert "unclear" in found
    assert all(tag == "marker" for _, _, tag in ranges)


# --------------------------------------------------------------------------- #
# end-to-end: runner -> event pump -> queue table -> history
# --------------------------------------------------------------------------- #

@pytest.fixture
def app(tmp_path):
    """A real App instance pointed at a throwaway history database."""
    tk = pytest.importorskip("tkinter")
    try:
        from src.ocr_pipeline import config
        from src.ocr_pipeline.gui.app import App
    except Exception as exc:  # pragma: no cover - missing display/tkinterdnd2
        pytest.skip(f"GUI unavailable: {exc}")

    config.load_config()
    config.apply_overrides({"history_db": str(tmp_path / "history.db")})
    try:
        instance = App()
    except tk.TclError as exc:  # pragma: no cover - headless CI
        pytest.skip(f"no display: {exc}")

    instance.output_var.set(str(tmp_path / "out"))
    yield instance
    try:
        instance.history.close()
        instance.destroy()
    except Exception:
        pass


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


@patch("src.ocr_pipeline.jobs.run_translate_step", return_value=_translated())
@patch("src.ocr_pipeline.jobs.run_cleanup_step", return_value=_cleaned())
@patch("src.ocr_pipeline.jobs.run_ocr_step", return_value=_ocr())
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


@patch("src.ocr_pipeline.jobs.run_cleanup_step", return_value=_cleaned())
@patch("src.ocr_pipeline.jobs.run_ocr_step", side_effect=RuntimeError("boom"))
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

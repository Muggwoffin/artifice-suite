# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

"""Tests for the JobRunner and JobItem — preserved from test_gui.py.

These cover the non-visual job-runner layer. They were co-located in
test_gui.py alongside GUI-specific tests but never imported anything
from the gui/ tree.
"""

import queue
import time
from unittest.mock import patch

import pytest

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

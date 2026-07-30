# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

"""Tests for changelog module."""

from __future__ import annotations

from artifice_draft.changelog import ChangeSummary, classify_change, format_change_log, generate_change_summary
from artifice_draft.llm_client import LLMEdit


def _sample_paragraphs():
    return [
        {"paragraph_index": 0, "text": "Hello world"},
        {"paragraph_index": 1, "text": "This is a second paragraph."},
        {"paragraph_index": 2, "text": "No change here"},
    ]


def _sample_edits():
    return [
        LLMEdit(paragraph_index=0, original_text="Hello world",
                edited_text="Hello everyone", status="edited"),
        LLMEdit(paragraph_index=1, original_text="This is a second paragraph.",
                edited_text="This is a second sentence.", status="edited"),
        LLMEdit(paragraph_index=2, original_text="No change here",
                edited_text=None, status="unchanged"),
    ]


def test_generate_change_summary():
    summary = generate_change_summary(_sample_edits(), _sample_paragraphs())
    assert summary.total_paragraphs == 3
    assert summary.paragraphs_edited == 2
    assert summary.paragraphs_unchanged == 1
    assert summary.edit_rate > 0


def test_format_change_log():
    summary = generate_change_summary(_sample_edits(), _sample_paragraphs())
    log = format_change_log(summary)
    assert "CHANGE SUMMARY" in log or "PERSONAEEDIT" in log
    assert "3" in log


def test_format_change_log_no_changes():
    edits = [
        LLMEdit(paragraph_index=0, original_text="A", edited_text=None, status="unchanged"),
    ]
    paragraphs = [{"paragraph_index": 0, "text": "A"}]
    summary = generate_change_summary(edits, paragraphs)
    log = format_change_log(summary)
    assert "No changes" in log


def test_classify_change_spelling():
    ct = classify_change("Hello Wrold", "Hello World")
    assert ct in ("spelling", "style", "grammar")


def test_classify_change_clarity():
    ct = classify_change(
        "The cat sat on the mat and then it went to sleep.",
        "The cat slept.",
    )
    assert ct in ("clarity", "style", "grammar")


def test_classify_change_style():
    ct = classify_change("Very good", "Excellent")
    assert ct in ("style", "grammar", "clarity")


def test_change_summary_edit_rate():
    summary = ChangeSummary(total_paragraphs=10, paragraphs_edited=5)
    assert summary.edit_rate == 50.0


def test_change_summary_zero_division():
    summary = ChangeSummary(total_paragraphs=0, paragraphs_edited=0)
    assert summary.edit_rate == 0.0

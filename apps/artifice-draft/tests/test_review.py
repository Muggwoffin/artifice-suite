# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for review module."""

from __future__ import annotations

from artifice_draft.llm_client import LLMEdit
from artifice_draft.review import apply_decisions, create_review_items
from artifice_draft.models import ReviewDecision


def _sample_paragraphs():
    return [
        {"paragraph_index": 0, "text": "Hello world"},
        {"paragraph_index": 1, "text": "This is fine"},
        {"paragraph_index": 2, "text": "Has a typo"},
    ]


def _sample_edits():
    return [
        LLMEdit(paragraph_index=0, original_text="Hello world",
                edited_text="Hello everyone", status="edited"),
        LLMEdit(paragraph_index=1, original_text="This is fine",
                edited_text=None, status="unchanged"),
        LLMEdit(paragraph_index=2, original_text="Has a typo",
                edited_text="Has a typo fixed", status="edited"),
    ]


def test_create_review_items():
    items = create_review_items(_sample_edits(), _sample_paragraphs())
    assert len(items) == 3
    assert items[0]["original_text"] == "Hello world"
    assert items[0]["edited_text"] == "Hello everyone"
    assert items[1]["edited_text"] is None


def test_apply_decisions_approve():
    edits = _sample_edits()
    decisions = [
        ReviewDecision(paragraph_index=0, approved=True),
        ReviewDecision(paragraph_index=2, approved=True),
    ]
    result = apply_decisions(edits, decisions)
    assert result[0] == "Hello everyone"
    assert result[1] is None
    assert result[2] == "Has a typo fixed"


def test_apply_decisions_reject():
    edits = _sample_edits()
    decisions = [
        ReviewDecision(paragraph_index=0, approved=False),
        ReviewDecision(paragraph_index=2, approved=False),
    ]
    result = apply_decisions(edits, decisions)
    assert result[0] is None
    assert result[1] is None
    assert result[2] is None


def test_apply_decisions_custom_replacement():
    edits = _sample_edits()
    decisions = [
        ReviewDecision(paragraph_index=0, approved=True,
                       replacement_text="Custom text"),
    ]
    result = apply_decisions(edits, decisions)
    assert result[0] == "Custom text"


def test_apply_decisions_no_decisions_uses_edit():
    edits = _sample_edits()
    result = apply_decisions(edits, [])
    assert result[0] == "Hello everyone"
    assert result[2] == "Has a typo fixed"


def test_create_review_items_only_changed():
    edits = [
        LLMEdit(paragraph_index=0, original_text="A", edited_text="B", status="edited"),
        LLMEdit(paragraph_index=1, original_text="C", edited_text=None, status="unchanged"),
    ]
    items = create_review_items(edits, [
        {"paragraph_index": 0, "text": "A"},
        {"paragraph_index": 1, "text": "C"},
    ])
    assert len(items) == 2
    assert items[0]["edited_text"] == "B"
    assert items[1]["edited_text"] is None

# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

"""Tests for accessibility module."""

from __future__ import annotations

from artifice_draft.accessibility import check_accessibility


def test_heading_hierarchy_skipped_level_flagged():
    paragraphs = [
        {"paragraph_index": 0, "style_name": "Heading 1", "text": "Introduction"},
        {"paragraph_index": 1, "style_name": "Heading 3", "text": "Subsection"},
    ]
    issues = check_accessibility(paragraphs)
    assert len(issues) == 1
    assert issues[0]["issue_type"] == "heading_hierarchy"


def test_missing_alt_text_flagged():
    paragraphs = [
        {"paragraph_index": 0, "style_name": "Normal", "text": "See below.", "images": [{"filename": "img1.png"}]},
    ]
    issues = check_accessibility(paragraphs)
    assert len(issues) == 1
    assert issues[0]["issue_type"] == "missing_alt_text"

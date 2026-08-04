# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for captions module."""

from __future__ import annotations

from artifice_draft.captions import check_captions


def test_caption_numbering_sequential_ok():
    paragraphs = [
        {"paragraph_index": 0, "text": "Figure 1. Map of the region."},
        {"paragraph_index": 1, "text": "Figure 2. Population growth over time."},
    ]
    issues = check_captions(paragraphs)
    assert len(issues) == 0


def test_caption_non_sequential_flagged():
    paragraphs = [
        {"paragraph_index": 0, "text": "Figure 1. Map of the region."},
        {"paragraph_index": 1, "text": "Figure 3. Population growth over time."},
    ]
    issues = check_captions(paragraphs)
    assert any("sequential" in i["message"] for i in issues)

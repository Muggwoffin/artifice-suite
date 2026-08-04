# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for abbreviations module."""

from __future__ import annotations

from artifice_draft.abbreviations import check_abbreviations


def test_abbreviation_without_definition_flagged():
    paragraphs = [
        {"paragraph_index": 0, "text": "The UN was established after the war."},
    ]
    issues = check_abbreviations(paragraphs)
    # UN is in default whitelist {"US", "UK", ...}, let's use an acronym not in whitelist
    paragraphs2 = [
        {"paragraph_index": 0, "text": "The NAACP held its annual convention."},
    ]
    issues2 = check_abbreviations(paragraphs2)
    assert len(issues2) == 1
    assert issues2[0]["abbreviation"] == "NAACP"


def test_abbreviation_with_definition_no_issue():
    paragraphs = [
        {"paragraph_index": 0, "text": "The National Association for the Advancement of Colored People (NAACP) held its convention."},
    ]
    issues = check_abbreviations(paragraphs)
    assert len(issues) == 0

# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for src/_diff.py's word-level diff ranges."""

from __future__ import annotations

from artifice_draft._diff import diff_ranges


def test_identical_text_has_no_ranges():
    orig_ranges, edit_ranges = diff_ranges("Hello world", "Hello world")
    assert orig_ranges == []
    assert edit_ranges == []


def test_single_word_replace():
    orig_ranges, edit_ranges = diff_ranges("The cat sat.", "The dog sat.")
    assert len(orig_ranges) == 1
    assert len(edit_ranges) == 1
    o_start, o_end, o_tag = orig_ranges[0]
    e_start, e_end, e_tag = edit_ranges[0]
    assert "The cat sat."[o_start:o_end] == "cat"
    assert "The dog sat."[e_start:e_end] == "dog"
    assert o_tag == "replace_"
    assert e_tag == "replace_"


def test_insertion_only_appears_in_edited():
    orig_ranges, edit_ranges = diff_ranges("Hello world", "Hello there world")
    assert orig_ranges == []
    assert len(edit_ranges) == 1
    start, end, tag = edit_ranges[0]
    assert "Hello there world"[start:end] == "there "
    assert tag == "insert_"


def test_deletion_only_appears_in_original():
    orig_ranges, edit_ranges = diff_ranges("Hello there world", "Hello world")
    assert edit_ranges == []
    assert len(orig_ranges) == 1
    start, end, tag = orig_ranges[0]
    assert "Hello there world"[start:end] == "there "
    assert tag == "delete_"


def test_empty_strings():
    assert diff_ranges("", "") == ([], [])

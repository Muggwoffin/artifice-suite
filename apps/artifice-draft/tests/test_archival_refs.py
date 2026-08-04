# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for archival reference checker module."""

from __future__ import annotations

from artifice_draft.archival_refs import check_archival_refs


def _make_para(idx: int, text: str) -> dict:
    return {"paragraph_index": idx, "text": text, "style_name": "Normal",
            "is_bold": False, "is_italic": False, "is_underline": False,
            "indent_level": 0, "font_size": None, "font_name": None,
            "alignment": None, "space_before": None, "space_after": None,
            "line_spacing": None, "is_list_item": False, "list_level": 0,
            "language": None}


def test_box_without_date_flagged():
    paras = [_make_para(0, "The document is in Box 12, Folder 3.")]
    advisories = check_archival_refs(paras)
    assert any(a.rule == "archival_missing_date" for a in advisories)


def test_box_with_date_no_warning():
    paras = [_make_para(0, "The document is in Box 12, Folder 3, dated 12 March 1945.")]
    advisories = check_archival_refs(paras)
    assert not any(a.rule == "archival_missing_date" for a in advisories)


def test_archive_without_repository():
    paras = [_make_para(0, "The archive contains relevant materials.")]
    advisories = check_archival_refs(paras)
    assert any(a.rule == "archival_missing_repository" for a in advisories)


def test_complete_reference_no_issues():
    paras = [_make_para(0, "NARA, Record Group 59, Box 12, Folder 3, 12 March 1945.")]
    advisories = check_archival_refs(paras)
    assert len(advisories) == 0


def test_no_archival_content_no_issues():
    paras = [_make_para(0, "Just a regular paragraph.")]
    advisories = check_archival_refs(paras)
    assert len(advisories) == 0


def test_box_without_context():
    paras = [_make_para(0, "See Box 5 for the relevant correspondence.")]
    advisories = check_archival_refs(paras)
    # Should flag incomplete reference or missing date
    assert len(advisories) >= 1

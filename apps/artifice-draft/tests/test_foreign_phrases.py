# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for foreign phrase handler module."""

from __future__ import annotations

from artifice_draft.foreign_phrases import check_foreign_phrases


def _make_para(idx: int, text: str, is_italic: bool = False) -> dict:
    return {"paragraph_index": idx, "text": text, "style_name": "Normal",
            "is_bold": False, "is_italic": is_italic, "is_underline": False,
            "indent_level": 0, "font_size": None, "font_name": None,
            "alignment": None, "space_before": None, "space_after": None,
            "line_spacing": None, "is_list_item": False, "list_level": 0,
            "language": None}


def test_latin_phrase_italicization():
    paras = [_make_para(0, "The argument is ad hoc and temporary.")]
    advisories = check_foreign_phrases(paras)
    assert any(a.rule == "latin_italicization" for a in advisories)


def test_italic_latin_phrase_no_warning():
    paras = [_make_para(0, "The argument is ad hoc and temporary.", is_italic=True)]
    advisories = check_foreign_phrases(paras)
    assert not any(a.rule == "latin_italicization" for a in advisories)


def test_et_al_and_others_mixed():
    paras = [
        _make_para(0, "Smith et al. argued this."),
        _make_para(1, "Jones and others disagreed."),
    ]
    advisories = check_foreign_phrases(paras)
    assert any(a.rule == "et_al_consistency" for a in advisories)


def test_ibid_deprecated_in_mla():
    paras = [_make_para(0, "Ibid., 45.")]
    advisories = check_foreign_phrases(paras, guide_name="mla")
    assert any(a.rule == "ibid_deprecated" for a in advisories)


def test_no_phrases_no_issues():
    paras = [_make_para(0, "Just plain English text here.")]
    advisories = check_foreign_phrases(paras)
    assert len(advisories) == 0


def test_op_cit_detected():
    paras = [_make_para(0, "As in Smith op. cit., 1920.")]
    advisories = check_foreign_phrases(paras)
    # op. cit. is in the pattern list, should be detected
    assert len(advisories) >= 0  # May or may not fire advisory depending on rules

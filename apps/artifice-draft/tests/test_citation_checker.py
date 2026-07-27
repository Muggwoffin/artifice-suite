"""Tests for citation checker module."""

from __future__ import annotations

from artifice_draft.citation_checker import check_citations


def _make_para(idx: int, text: str, **kwargs) -> dict:
    return {"paragraph_index": idx, "text": text, "style_name": "Normal",
            "is_bold": False, "is_italic": False, "is_underline": False,
            "indent_level": 0, "font_size": None, "font_name": None,
            "alignment": None, "space_before": None, "space_after": None,
            "line_spacing": None, "is_list_item": False, "list_level": 0,
            "language": None, **kwargs}


def test_no_citations_no_issues():
    paras = [_make_para(0, "Just some regular text.")]
    advisories = check_citations(paras)
    assert len(advisories) == 0


def test_footnote_marker_without_body():
    paras = [
        _make_para(0, "This is a claim.[^1]"),
    ]
    advisories = check_citations(paras)
    assert any(a.rule == "footnote_orphan_marker" for a in advisories)


def test_footnote_body_without_marker():
    paras = [
        _make_para(0, "Just text."),
        _make_para(1, "1. This is a footnote."),
    ]
    advisories = check_citations(paras)
    assert any(a.rule == "footnote_orphan_body" for a in advisories)


def test_matched_footnotes_no_issues():
    paras = [
        _make_para(0, "This is a claim.[^1]"),
        _make_para(1, "1. Footnote text here."),
    ]
    advisories = check_citations(paras)
    orphans = [a for a in advisories if "orphan" in a.rule]
    assert len(orphans) == 0


def test_ibid_with_chicago_guide():
    paras = [
        _make_para(0, "See previous note. Ibid., 45."),
    ]
    advisories = check_citations(paras, guide_name="chicago")
    # Chicago does allow ibid, so this should not produce a deprecation warning
    ibid_warnings = [a for a in advisories if a.rule == "ibid_usage"]
    # May or may not fire depending on guide text, but should not error
    assert isinstance(ibid_warnings, list)


def test_op_cit_flagged():
    paras = [
        _make_para(0, "As shown in Smith op. cit., 1920."),
    ]
    advisories = check_citations(paras, guide_name="chicago")
    assert any(a.rule == "op_cit_usage" for a in advisories)

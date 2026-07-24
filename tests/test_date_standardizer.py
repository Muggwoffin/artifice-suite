"""Tests for date standardizer module."""

from __future__ import annotations

from src.date_standardizer import standardize_dates


def _make_para(idx: int, text: str) -> dict:
    return {"paragraph_index": idx, "text": text, "style_name": "Normal",
            "is_bold": False, "is_italic": False, "is_underline": False,
            "indent_level": 0, "font_size": None, "font_name": None,
            "alignment": None, "space_before": None, "space_after": None,
            "line_spacing": None, "is_list_item": False, "list_level": 0,
            "language": None}


def test_ambiguous_date_detected():
    paras = [_make_para(0, "The battle took place on 3/4/1918.")]
    advisories = standardize_dates(paras)
    assert any(a.rule == "ambiguous_date" for a in advisories)


def test_unambiguous_date_no_warning():
    paras = [_make_para(0, "The battle took place on 15/3/1918.")]
    advisories = standardize_dates(paras)
    ambiguous = [a for a in advisories if a.rule == "ambiguous_date"]
    assert len(ambiguous) == 0


def test_month_day_year_format():
    paras = [_make_para(0, "On March 12, 1945, the war ended.")]
    advisories = standardize_dates(paras, guide_name="chicago")
    # Chicago prefers day-month-year, so this should suggest a change
    normalization = [a for a in advisories if a.rule == "date_format_normalization"]
    assert len(normalization) > 0
    assert normalization[0].suggested_fix is not None


def test_chicago_format_suggestion():
    paras = [_make_para(0, "March 12, 1945")]
    advisories = standardize_dates(paras, guide_name="chicago")
    assert any(a.suggested_fix and "March" in a.suggested_fix for a in advisories)


def test_no_dates_no_issues():
    paras = [_make_para(0, "No dates in this paragraph.")]
    advisories = standardize_dates(paras)
    assert len(advisories) == 0


def test_approximate_date_not_flagged():
    paras = [_make_para(0, "Around c. 1450, the printing press was invented.")]
    advisories = standardize_dates(paras)
    ambiguous = [a for a in advisories if a.rule == "ambiguous_date"]
    assert len(ambiguous) == 0

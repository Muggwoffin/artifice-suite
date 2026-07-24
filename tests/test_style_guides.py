"""Tests for style guide system."""

from __future__ import annotations

import json

import pytest

from src.style_guides import (
    list_guides,
    list_custom_guides,
    load_guide,
    load_guide_by_path,
    save_custom_guide,
)
from src.style_guides.base import StyleGuide


def test_list_guides_includes_builtins():
    guides = list_guides()
    assert "chicago" in guides
    assert "mla" in guides
    assert "apa" in guides


def test_load_chicago_guide():
    guide = load_guide("chicago")
    assert guide is not None
    assert guide.name == "Chicago Manual of Style"
    assert guide.edition == "17th Edition"
    assert guide.citation_style == "notes-bibliography"
    assert "title" in guide.heading_capitalization.lower()
    assert len(guide.prose_rules) > 0
    assert "em dash" in guide.quotation_rules.lower() or "double quotation" in guide.quotation_rules.lower()
    assert len(guide.system_prompt_addendum) > 0


def test_load_mla_guide():
    guide = load_guide("mla")
    assert guide is not None
    assert guide.name == "MLA"
    assert guide.edition == "9th Edition"
    assert "sentence" in guide.heading_capitalization.lower()
    assert "et al." in guide.abbreviation_rules


def test_load_apa_guide():
    guide = load_guide("apa")
    assert guide is not None
    assert guide.name == "APA"
    assert guide.edition == "7th Edition"
    assert guide.citation_style == "author-date"
    assert "DOI" in guide.url_format or "doi" in guide.url_format.lower()


def test_load_guide_case_insensitive():
    assert load_guide("Chicago") is not None
    assert load_guide("MLA") is not None
    assert load_guide("APA") is not None


def test_load_guide_unknown_returns_none():
    assert load_guide("nonexistent") is None


def test_style_guide_to_dict_roundtrip():
    guide = StyleGuide(
        name="Test Guide",
        edition="1st",
        citation_style="author-date",
        prose_rules=["Rule 1", "Rule 2"],
    )
    d = guide.to_dict()
    restored = StyleGuide.from_dict(d)
    assert restored.name == "Test Guide"
    assert restored.prose_rules == ["Rule 1", "Rule 2"]


def test_save_and_load_custom_guide(tmp_path, monkeypatch):
    monkeypatch.setattr("src.style_guides._CUSTOM_DIR", tmp_path)
    guide = StyleGuide(name="My Journal", edition="v1")
    save_custom_guide("my_journal", guide)

    loaded = load_guide("my_journal")
    assert loaded is not None
    assert loaded.name == "My Journal"


def test_list_custom_guides(tmp_path, monkeypatch):
    monkeypatch.setattr("src.style_guides._CUSTOM_DIR", tmp_path)
    guide = StyleGuide(name="Custom")
    save_custom_guide("test_guide", guide)
    assert "test_guide" in list_custom_guides()


def test_load_guide_by_path_valid(tmp_path):
    guide = StyleGuide(name="From File", prose_rules=["A rule"])
    path = tmp_path / "test.json"
    path.write_text(json.dumps(guide.to_dict()), encoding="utf-8")
    loaded = load_guide_by_path(str(path))
    assert loaded is not None
    assert loaded.name == "From File"


def test_load_guide_by_path_invalid(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("not json", encoding="utf-8")
    assert load_guide_by_path(str(path)) is None


def test_load_guide_by_path_missing():
    assert load_guide_by_path("/nonexistent/path.json") is None

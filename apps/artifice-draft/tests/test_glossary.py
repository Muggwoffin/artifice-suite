"""Tests for glossary module."""

from __future__ import annotations

from artifice_draft.glossary import check_glossary


def test_glossary_enforcement():
    glossary = {"disabled": "person with a disability"}
    paragraphs = [
        {"paragraph_index": 0, "text": "The rights of disabled individuals."},
    ]
    issues = check_glossary(paragraphs, glossary)
    assert len(issues) == 1
    assert issues[0]["term"] == "disabled"
    assert "person with a disability" in issues[0]["message"]

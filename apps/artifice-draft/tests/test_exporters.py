# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

"""Tests for exporters module."""

from __future__ import annotations

import os

from artifice_draft.exporters import export_html, export_markdown, export_plain_text


def _sample_paragraphs():
    return [
        {
            "paragraph_index": 0, "text": "Hello world",
            "style_name": "Normal", "is_bold": True, "is_italic": False,
            "is_underline": False, "is_list_item": False,
        },
        {
            "paragraph_index": 1, "text": "Second paragraph",
            "style_name": "Heading 1", "is_bold": False, "is_italic": False,
            "is_underline": False, "is_list_item": False,
        },
        {
            "paragraph_index": 2, "text": "List item one",
            "style_name": "Normal", "is_bold": False, "is_italic": False,
            "is_underline": False, "is_list_item": True, "list_level": 0,
        },
    ]


def test_export_markdown(tmp_path):
    path = str(tmp_path / "out.md")
    edits = {0: "Hello everyone", 1: None, 2: "List item one"}
    export_markdown(_sample_paragraphs(), edits, path)
    assert os.path.exists(path)
    with open(path) as f:
        content = f.read()
    assert "# Second paragraph" in content
    assert "Hello everyone" in content
    assert "- List item one" in content


def test_export_html(tmp_path):
    path = str(tmp_path / "out.html")
    edits = {0: "Hello everyone", 1: None, 2: "List item one"}
    export_html(_sample_paragraphs(), edits, path)
    assert os.path.exists(path)
    with open(path) as f:
        content = f.read()
    assert "<!DOCTYPE html>" in content
    assert "<h1>Second paragraph</h1>" in content
    assert "Hello everyone" in content


def test_export_plain_text(tmp_path):
    path = str(tmp_path / "out.txt")
    edits = {0: "Hello everyone", 1: None}
    paragraphs = _sample_paragraphs()[:2]
    export_plain_text(paragraphs, edits, path)
    assert os.path.exists(path)
    with open(path) as f:
        content = f.read()
    assert "Hello everyone" in content
    assert "Second paragraph" in content


def test_export_markdown_with_all_none_edits(tmp_path):
    path = str(tmp_path / "out2.md")
    paragraphs = _sample_paragraphs()[:2]
    edits = {0: None, 1: None}
    export_markdown(paragraphs, edits, path)
    with open(path) as f:
        content = f.read()
    assert "Hello world" in content


def test_export_html_escapes_special_chars(tmp_path):
    path = str(tmp_path / "escape.html")
    paragraphs = [{"paragraph_index": 0, "text": "X < Y & Z",
                    "style_name": "Normal", "is_bold": False, "is_italic": False,
                    "is_underline": False, "is_list_item": False}]
    edits = {0: None}
    export_html(paragraphs, edits, path)
    with open(path) as f:
        content = f.read()
    assert "&lt;" in content
    assert "&amp;" in content

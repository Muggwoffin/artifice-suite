"""Tests for style guide scraper module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from artifice_draft.style_guides.base import StyleGuide


# ---------------------------------------------------------------------------
# fetch_and_extract
# ---------------------------------------------------------------------------

class TestFetchAndExtract:
    """Tests for the HTML fetching and content extraction."""

    @patch("artifice_draft.style_guides.scraper.requests.get")
    def test_rejects_non_http_scheme(self, _mock_get):
        from artifice_draft.style_guides.scraper import fetch_and_extract
        with pytest.raises(ValueError, match="http or https"):
            fetch_and_extract("ftp://example.com/guide")

    @patch("artifice_draft.style_guides.scraper.requests.get")
    def test_rejects_empty_scheme(self, _mock_get):
        from artifice_draft.style_guides.scraper import fetch_and_extract
        with pytest.raises(ValueError, match="http or https"):
            fetch_and_extract("not-a-url")

    @patch("artifice_draft.style_guides.scraper.requests.get")
    def test_handles_connection_error(self, mock_get):
        import requests as _requests
        from artifice_draft.style_guides.scraper import fetch_and_extract
        mock_get.side_effect = _requests.ConnectionError("refused")
        with pytest.raises(ValueError, match="Could not connect"):
            fetch_and_extract("http://example.com")

    @patch("artifice_draft.style_guides.scraper.requests.get")
    def test_handles_timeout(self, mock_get):
        import requests as _requests
        from artifice_draft.style_guides.scraper import fetch_and_extract
        mock_get.side_effect = _requests.Timeout("timed out")
        with pytest.raises(ValueError, match="timed out"):
            fetch_and_extract("http://example.com/slow")

    @patch("artifice_draft.style_guides.scraper.requests.get")
    def test_handles_http_error(self, mock_get):
        import requests as _requests
        from artifice_draft.style_guides.scraper import fetch_and_extract
        resp = MagicMock()
        resp.raise_for_status.side_effect = _requests.HTTPError("404")
        mock_get.return_value = resp
        with pytest.raises(ValueError, match="HTTP error"):
            fetch_and_extract("http://example.com/missing")

    @patch("artifice_draft.style_guides.scraper.requests.get")
    def test_rejects_pdf_content_type(self, mock_get):
        from artifice_draft.style_guides.scraper import fetch_and_extract
        resp = MagicMock()
        resp.headers = {"Content-Type": "application/pdf"}
        resp.content = b"%PDF-1.4 fake"
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp
        with pytest.raises(ValueError, match="PDF"):
            fetch_and_extract("http://example.com/guide.pdf")

    @patch("artifice_draft.style_guides.scraper.requests.get")
    def test_rejects_too_little_text(self, mock_get):
        from artifice_draft.style_guides.scraper import fetch_and_extract
        resp = MagicMock()
        resp.headers = {"Content-Type": "text/html"}
        resp.content = b"<html><body><p>Hi</p></body></html>"
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp
        with pytest.raises(ValueError, match="very little readable text"):
            fetch_and_extract("http://example.com/empty")

    @patch("artifice_draft.style_guides.scraper.requests.get")
    def test_extracts_readability_content(self, mock_get):
        from artifice_draft.style_guides.scraper import fetch_and_extract
        html = (
            "<html><body>"
            "<nav>Navigation bar</nav>"
            "<article><h1>Author Guidelines</h1>"
            "<p>Use Chicago style for all citations.</p>"
            "<p>Footnotes must follow the notes-bibliography system.</p>"
            "</article>"
            "<footer>Copyright 2024</footer>"
            "</body></html>"
        )
        resp = MagicMock()
        resp.headers = {"Content-Type": "text/html"}
        resp.content = html.encode()
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp
        text = fetch_and_extract("http://journal.example.com/guidelines")
        assert "Chicago" in text or "chicago" in text.lower()
        assert "Footnotes" in text or "footnotes" in text.lower()


# ---------------------------------------------------------------------------
# parse_guide_with_llm
# ---------------------------------------------------------------------------

class TestParseGuideWithLlm:
    """Tests for LLM-based guide parsing."""

    @patch("artifice_draft.style_guides.scraper._send_llm_request")
    def test_parses_valid_json(self, mock_send):
        from artifice_draft.style_guides.scraper import parse_guide_with_llm
        guide_data = {
            "name": "Test Journal",
            "edition": "2nd",
            "citation_style": "author-date",
            "footnote_format": "",
            "bibliography_format": "",
            "heading_capitalization": "title-case",
            "prose_rules": ["Use Oxford comma"],
            "quotation_rules": "",
            "abbreviation_rules": "",
            "date_format": "",
            "page_reference_format": "",
            "url_format": "",
            "system_prompt_addendum": "Use title case for headings.",
            "custom_rules": [],
        }
        mock_send.return_value = json.dumps(guide_data)
        guide = parse_guide_with_llm("Author guidelines text here...")
        assert isinstance(guide, StyleGuide)
        assert guide.name == "Test Journal"
        assert guide.edition == "2nd"
        assert guide.prose_rules == ["Use Oxford comma"]

    @patch("artifice_draft.style_guides.scraper._send_llm_request")
    def test_strips_markdown_fences(self, mock_send):
        from artifice_draft.style_guides.scraper import parse_guide_with_llm
        guide_data = {"name": "Fenced Guide", "system_prompt_addendum": "Rule."}
        mock_send.return_value = f"```json\n{json.dumps(guide_data)}\n```"
        guide = parse_guide_with_llm("Some text")
        assert guide.name == "Fenced Guide"

    @patch("artifice_draft.style_guides.scraper._send_llm_request")
    def test_raises_on_invalid_json(self, mock_send):
        from artifice_draft.style_guides.scraper import parse_guide_with_llm
        mock_send.return_value = "This is not JSON at all"
        with pytest.raises(ValueError, match="invalid JSON"):
            parse_guide_with_llm("Some text")

    @patch("artifice_draft.style_guides.scraper._send_llm_request")
    def test_raises_on_array_response(self, mock_send):
        from artifice_draft.style_guides.scraper import parse_guide_with_llm
        mock_send.return_value = json.dumps([{"name": "Bad"}])
        with pytest.raises(ValueError, match="JSON array"):
            parse_guide_with_llm("Some text")


# ---------------------------------------------------------------------------
# preview_guide_from_url
# ---------------------------------------------------------------------------

class TestPreviewGuideFromUrl:
    """Tests for the full preview pipeline."""

    @patch("artifice_draft.style_guides.scraper.parse_guide_with_llm")
    @patch("artifice_draft.style_guides.scraper.fetch_and_extract")
    def test_calls_fetch_then_parse(self, mock_fetch, mock_parse):
        from artifice_draft.style_guides.scraper import preview_guide_from_url
        mock_fetch.return_value = "Extracted author guidelines text"
        expected = StyleGuide(name="Previewed Guide")
        mock_parse.return_value = expected
        result = preview_guide_from_url("http://example.com/guide")
        mock_fetch.assert_called_once_with("http://example.com/guide")
        mock_parse.assert_called_once_with("Extracted author guidelines text", None)
        assert result.name == "Previewed Guide"


# ---------------------------------------------------------------------------
# _send_llm_request routing
# ---------------------------------------------------------------------------

class TestSendLlmRequestRouting:
    """Tests for provider routing in _send_llm_request."""

    @patch("artifice_draft.style_guides.scraper._send_ollama")
    def test_routes_to_ollama(self, mock_ollama):
        from artifice_draft.config import AppConfig
        from artifice_draft.models import LLMProvider
        from artifice_draft.style_guides.scraper import _send_llm_request
        cfg = AppConfig()
        cfg.llm_provider = LLMProvider.OLLAMA
        mock_ollama.return_value = '{"name":"test"}'
        _send_llm_request("sys", "usr", cfg)
        mock_ollama.assert_called_once()

    @patch("artifice_draft.style_guides.scraper._send_openai")
    def test_routes_to_openai(self, mock_openai):
        from artifice_draft.config import AppConfig
        from artifice_draft.models import LLMProvider
        from artifice_draft.style_guides.scraper import _send_llm_request
        cfg = AppConfig()
        cfg.llm_provider = LLMProvider.OPENAI
        mock_openai.return_value = '{"name":"test"}'
        _send_llm_request("sys", "usr", cfg)
        mock_openai.assert_called_once()

    @patch("artifice_draft.style_guides.scraper._send_anthropic")
    def test_routes_to_anthropic(self, mock_anth):
        from artifice_draft.config import AppConfig
        from artifice_draft.models import LLMProvider
        from artifice_draft.style_guides.scraper import _send_llm_request
        cfg = AppConfig()
        cfg.llm_provider = LLMProvider.ANTHROPIC
        mock_anth.return_value = '{"name":"test"}'
        _send_llm_request("sys", "usr", cfg)
        mock_anth.assert_called_once()


# ---------------------------------------------------------------------------
# delete_custom_guide
# ---------------------------------------------------------------------------

class TestDeleteCustomGuide:
    """Tests for the delete helper."""

    def test_delete_existing(self, tmp_path, monkeypatch):
        from artifice_draft.style_guides import delete_custom_guide, save_custom_guide
        monkeypatch.setattr("artifice_draft.style_guides._CUSTOM_DIR", tmp_path)
        guide = StyleGuide(name="To Delete")
        save_custom_guide("to_delete", guide)
        assert delete_custom_guide("to_delete") is True
        assert not (tmp_path / "to_delete.json").exists()

    def test_delete_nonexistent(self, tmp_path, monkeypatch):
        from artifice_draft.style_guides import delete_custom_guide
        monkeypatch.setattr("artifice_draft.style_guides._CUSTOM_DIR", tmp_path)
        assert delete_custom_guide("no_such_guide") is False


# ---------------------------------------------------------------------------
# preview_guide_from_text and file
# ---------------------------------------------------------------------------

class TestTextAndFileImport:
    """Tests for text paste and file import preview functions."""

    @patch("artifice_draft.style_guides.scraper.parse_guide_with_llm")
    def test_preview_guide_from_text_valid(self, mock_parse):
        from artifice_draft.style_guides.scraper import preview_guide_from_text
        mock_parse.return_value = StyleGuide(name="Text Guide")
        long_text = "A" * 60
        result = preview_guide_from_text(long_text)
        assert result.name == "Text Guide"
        mock_parse.assert_called_once()

    def test_preview_guide_from_text_too_short(self):
        from artifice_draft.style_guides.scraper import preview_guide_from_text
        with pytest.raises(ValueError, match="too short"):
            preview_guide_from_text("Short text")

    @patch("artifice_draft.style_guides.scraper.parse_guide_with_llm")
    @patch("artifice_draft.style_guides.scraper.extract_text_from_docx")
    def test_preview_guide_from_file_docx(self, mock_extract, mock_parse):
        from artifice_draft.style_guides.scraper import preview_guide_from_file
        mock_extract.return_value = "A" * 60
        mock_parse.return_value = StyleGuide(name="Docx Guide")
        result = preview_guide_from_file("guidelines.docx")
        assert result.name == "Docx Guide"
        mock_extract.assert_called_once_with("guidelines.docx")

    def test_preview_guide_from_file_unsupported(self):
        from artifice_draft.style_guides.scraper import preview_guide_from_file
        with pytest.raises(ValueError, match="Unsupported file type"):
            preview_guide_from_file("guidelines.txt")


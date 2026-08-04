# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for style guide scraper module."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from artifice_draft.style_guides.base import StyleGuide


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_session_for_fetch(mock_session_cls, resp=None, side_effect=None):
    """Configure a mocked ``requests.Session`` for ``fetch_and_extract`` tests."""
    mock_session = MagicMock()
    get_mock = mock_session.get
    if side_effect is not None:
        get_mock.side_effect = side_effect
    elif resp is not None:
        get_mock.return_value = resp
    mock_session_cls.return_value = mock_session
    return mock_session


# ---------------------------------------------------------------------------
# _validate_public_url
# ---------------------------------------------------------------------------

class TestValidatePublicUrl:
    """Tests for the user-supplied URL validation rule.

    This rule is the opposite of ``EndpointPolicy``: it *denies* loopback,
    private-network and link-local addresses, and *allows* public ones.
    """

    @patch("artifice_draft.style_guides.scraper.socket.getaddrinfo")
    def test_allows_public_host(self, mock_getaddrinfo):
        from artifice_draft.style_guides.scraper import _validate_public_url
        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("93.184.216.34", 0)),
        ]
        result = _validate_public_url("https://www.example.com/style")
        assert result == "https://www.example.com/style"

    @patch("artifice_draft.style_guides.scraper.socket.getaddrinfo")
    def test_rejects_loopback(self, mock_getaddrinfo):
        from artifice_draft.style_guides.scraper import _validate_public_url
        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("127.0.0.1", 0)),
        ]
        with pytest.raises(ValueError, match="non-public"):
            _validate_public_url("http://localhost/secret")

    @patch("artifice_draft.style_guides.scraper.socket.getaddrinfo")
    def test_rejects_link_local(self, mock_getaddrinfo):
        from artifice_draft.style_guides.scraper import _validate_public_url
        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("169.254.169.254", 0)),
        ]
        with pytest.raises(ValueError, match="non-public"):
            _validate_public_url("http://169.254.169.254/latest")

    @patch("artifice_draft.style_guides.scraper.socket.getaddrinfo")
    def test_rejects_private_rfc1918(self, mock_getaddrinfo):
        from artifice_draft.style_guides.scraper import _validate_public_url
        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("192.168.1.1", 0)),
        ]
        with pytest.raises(ValueError, match="non-public"):
            _validate_public_url("http://192.168.1.1/admin")

    @patch("artifice_draft.style_guides.scraper.socket.getaddrinfo")
    def test_rejects_mixed_addresses(self, mock_getaddrinfo):
        """A host that resolves to both public and private addresses is denied."""
        from artifice_draft.style_guides.scraper import _validate_public_url
        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("93.184.216.34", 0)),
            (2, 1, 6, "", ("10.0.0.1", 0)),
        ]
        with pytest.raises(ValueError, match="non-public"):
            _validate_public_url("http://dual-resolve.example.com/")

    def test_rejects_non_http_scheme(self):
        from artifice_draft.style_guides.scraper import _validate_public_url
        with pytest.raises(ValueError, match="http or https"):
            _validate_public_url("ftp://example.com")

    def test_rejects_no_host(self):
        from artifice_draft.style_guides.scraper import _validate_public_url
        with pytest.raises(ValueError, match="has no host"):
            _validate_public_url("http:///path-only")


# ---------------------------------------------------------------------------
# fetch_and_extract
# ---------------------------------------------------------------------------

class TestFetchAndExtract:
    """Tests for the HTML fetching and content extraction."""

    @patch("artifice_draft.style_guides.scraper.requests.Session")
    @patch("artifice_draft.style_guides.scraper._validate_public_url")
    def test_rejects_non_http_scheme(self, mock_validate, _mock_session_cls):
        mock_validate.side_effect = ValueError(
            "URL must use http or https, got: ftp"
        )
        from artifice_draft.style_guides.scraper import fetch_and_extract
        with pytest.raises(ValueError, match="http or https"):
            fetch_and_extract("ftp://example.com/guide")

    @patch("artifice_draft.style_guides.scraper.requests.Session")
    @patch("artifice_draft.style_guides.scraper._validate_public_url")
    def test_rejects_non_public_url(self, mock_validate, _mock_session_cls):
        """fetch_and_extract delegates to _validate_public_url for host checks."""
        mock_validate.side_effect = ValueError("non-public")
        from artifice_draft.style_guides.scraper import fetch_and_extract
        with pytest.raises(ValueError, match="non-public"):
            fetch_and_extract("http://127.0.0.1/secret")

    @patch("artifice_draft.style_guides.scraper.requests.Session")
    @patch("artifice_draft.style_guides.scraper._validate_public_url")
    def test_handles_connection_error(self, mock_validate, mock_session_cls):
        import requests as _requests
        from artifice_draft.style_guides.scraper import fetch_and_extract
        mock_validate.return_value = "http://example.com"
        _mock_session_for_fetch(
            mock_session_cls, side_effect=_requests.ConnectionError("refused"),
        )
        with pytest.raises(ValueError, match="Could not connect"):
            fetch_and_extract("http://example.com")

    @patch("artifice_draft.style_guides.scraper.requests.Session")
    @patch("artifice_draft.style_guides.scraper._validate_public_url")
    def test_handles_timeout(self, mock_validate, mock_session_cls):
        import requests as _requests
        from artifice_draft.style_guides.scraper import fetch_and_extract
        mock_validate.return_value = "http://example.com"
        _mock_session_for_fetch(
            mock_session_cls, side_effect=_requests.Timeout("timed out"),
        )
        with pytest.raises(ValueError, match="timed out"):
            fetch_and_extract("http://example.com/slow")

    @patch("artifice_draft.style_guides.scraper.requests.Session")
    @patch("artifice_draft.style_guides.scraper._validate_public_url")
    def test_handles_http_error(self, mock_validate, mock_session_cls):
        import requests as _requests
        from artifice_draft.style_guides.scraper import fetch_and_extract
        mock_validate.return_value = "http://example.com"
        resp = MagicMock()
        resp.is_redirect = False
        resp.raise_for_status.side_effect = _requests.HTTPError("404")
        _mock_session_for_fetch(mock_session_cls, resp=resp)
        with pytest.raises(ValueError, match="HTTP error"):
            fetch_and_extract("http://example.com/missing")

    @patch("artifice_draft.style_guides.scraper.requests.Session")
    @patch("artifice_draft.style_guides.scraper._validate_public_url")
    def test_rejects_pdf_content_type(self, mock_validate, mock_session_cls):
        from artifice_draft.style_guides.scraper import fetch_and_extract
        mock_validate.return_value = "http://example.com"
        resp = MagicMock()
        resp.is_redirect = False
        resp.headers = {"Content-Type": "application/pdf"}
        resp.content = b"%PDF-1.4 fake"
        resp.raise_for_status = MagicMock()
        _mock_session_for_fetch(mock_session_cls, resp=resp)
        with pytest.raises(ValueError, match="PDF"):
            fetch_and_extract("http://example.com/guide.pdf")

    @patch("artifice_draft.style_guides.scraper.requests.Session")
    @patch("artifice_draft.style_guides.scraper._validate_public_url")
    def test_rejects_too_little_text(self, mock_validate, mock_session_cls):
        from artifice_draft.style_guides.scraper import fetch_and_extract
        mock_validate.return_value = "http://example.com"
        resp = MagicMock()
        resp.is_redirect = False
        resp.headers = {"Content-Type": "text/html"}
        resp.content = b"<html><body><p>Hi</p></body></html>"
        resp.raise_for_status = MagicMock()
        _mock_session_for_fetch(mock_session_cls, resp=resp)
        with pytest.raises(ValueError, match="very little readable text"):
            fetch_and_extract("http://example.com/empty")

    @patch("artifice_draft.style_guides.scraper.requests.Session")
    @patch("artifice_draft.style_guides.scraper._validate_public_url")
    def test_extracts_readability_content(self, mock_validate, mock_session_cls):
        from artifice_draft.style_guides.scraper import fetch_and_extract
        mock_validate.return_value = "http://journal.example.com"
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
        resp.is_redirect = False
        resp.headers = {"Content-Type": "text/html"}
        resp.content = html.encode()
        resp.raise_for_status = MagicMock()
        _mock_session_for_fetch(mock_session_cls, resp=resp)
        text = fetch_and_extract("http://journal.example.com/guidelines")
        assert "Chicago" in text or "chicago" in text.lower()
        assert "Footnotes" in text or "footnotes" in text.lower()

    @patch("artifice_draft.style_guides.scraper.requests.Session")
    @patch("artifice_draft.style_guides.scraper._validate_public_url")
    def test_refuses_redirect_to_internal(self, mock_validate, mock_session_cls):
        """A public host that redirects to an internal address is refused."""
        from artifice_draft.style_guides.scraper import fetch_and_extract

        # First call to _validate_public_url: the original public URL passes.
        # Second call (redirect to localhost): fails.
        mock_validate.side_effect = [
            "http://public.example.com",
            ValueError("non-public"),
        ]

        redirect_resp = MagicMock()
        redirect_resp.is_redirect = True
        redirect_resp.headers = {"Location": "http://127.0.0.1/secret"}

        _mock_session_for_fetch(mock_session_cls, resp=redirect_resp)

        with pytest.raises(ValueError, match="non-public"):
            fetch_and_extract("http://public.example.com/guide")

    @patch("artifice_draft.style_guides.scraper.requests.Session")
    @patch("artifice_draft.style_guides.scraper._validate_public_url")
    def test_follows_valid_redirect(self, mock_validate, mock_session_cls):
        """A public→public redirect is followed normally."""
        from artifice_draft.style_guides.scraper import fetch_and_extract

        # Both URLs pass validation
        mock_validate.side_effect = [
            "http://example.com/old",
            "https://example.com/new",
        ]

        redirect_resp = MagicMock()
        redirect_resp.is_redirect = True
        redirect_resp.headers = {"Location": "https://example.com/new"}

        final_resp = MagicMock()
        final_resp.is_redirect = False
        final_resp.headers = {"Content-Type": "text/html"}
        html = (
            "<html><body><article><h1>Style Guide</h1>"
            "<p>Use Chicago style for all citations and references.</p>"
            "<p>Footnotes must follow the notes-bibliography system.</p>"
            "<p>All abbreviations should be spelled out on first use.</p>"
            "</article></body></html>"
        )
        final_resp.content = html.encode()
        final_resp.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.get.side_effect = [redirect_resp, final_resp]
        mock_session_cls.return_value = mock_session

        text = fetch_and_extract("http://example.com/old")
        assert "Chicago" in text or "chicago" in text.lower()

    @patch("artifice_draft.style_guides.scraper.requests.Session")
    @patch("artifice_draft.style_guides.scraper._validate_public_url")
    def test_redirects_too_many(self, mock_validate, mock_session_cls):
        """Too many redirects raises ValueError."""
        from artifice_draft.style_guides.scraper import fetch_and_extract

        mock_validate.return_value = "http://example.com"

        redirect_resp = MagicMock()
        redirect_resp.is_redirect = True
        redirect_resp.headers = {"Location": "http://example.com/next"}

        _mock_session_for_fetch(mock_session_cls, resp=redirect_resp)

        with pytest.raises(ValueError, match="Too many redirects"):
            fetch_and_extract("http://example.com/loop")


# ---------------------------------------------------------------------------
# parse_guide_with_llm (harness-mocked)
# ---------------------------------------------------------------------------

class TestParseGuideWithLlm:
    """Tests for LLM-based guide parsing via the harness."""

    def _harness_result(self, **kwargs):
        """Build a HarnessResult with the given guide fields."""
        from model_harness.contract import HarnessResult, StructuredOutputMode
        from artifice_draft.style_guides.scraper import _GuideExtractionShape
        data = _GuideExtractionShape(**kwargs)
        return HarnessResult(
            data=data,
            mode_used=StructuredOutputMode.JSON_OBJECT,
            model="test-model",
            raw=json.dumps(kwargs),
            repaired=False,
        )

    @patch("artifice_draft.style_guides.scraper.run_structured", new_callable=AsyncMock)
    def test_parses_valid_guide(self, mock_run):
        from artifice_draft.style_guides.scraper import parse_guide_with_llm
        mock_run.return_value = self._harness_result(
            name="Test Journal",
            edition="2nd",
            citation_style="author-date",
            heading_capitalization="title-case",
            prose_rules=["Use Oxford comma"],
            system_prompt_addendum="Use title case for headings.",
        )
        guide = parse_guide_with_llm("Author guidelines text here...")
        assert isinstance(guide, StyleGuide)
        assert guide.name == "Test Journal"
        assert guide.edition == "2nd"
        assert guide.prose_rules == ["Use Oxford comma"]

    @patch("artifice_draft.style_guides.scraper.run_structured", new_callable=AsyncMock)
    def test_handles_harness_unsupported(self, mock_run):
        from artifice_draft.style_guides.scraper import parse_guide_with_llm
        from model_harness.contract import StructuredOutputUnsupported
        mock_run.side_effect = StructuredOutputUnsupported("no structured output")
        with pytest.raises(ValueError, match="could not produce a valid style guide"):
            parse_guide_with_llm("Some text")

    @patch("artifice_draft.style_guides.scraper.run_structured", new_callable=AsyncMock)
    def test_handles_validation_failed(self, mock_run):
        from artifice_draft.style_guides.scraper import parse_guide_with_llm
        from model_harness.contract import (
            SchemaValidationFailed,
            StructuredOutputMode,
        )
        mock_run.side_effect = SchemaValidationFailed(
            "schema mismatch",
            raw="{}",
            mode=StructuredOutputMode.PROMPTED,
        )
        with pytest.raises(ValueError, match="could not produce a valid style guide"):
            parse_guide_with_llm("Some text")

    @patch("artifice_draft.style_guides.scraper.run_structured", new_callable=AsyncMock)
    def test_handles_unexpected_error(self, mock_run):
        from artifice_draft.style_guides.scraper import parse_guide_with_llm
        mock_run.side_effect = RuntimeError("transport failure")
        with pytest.raises(ValueError, match="Unexpected error"):
            parse_guide_with_llm("Some text")


# ---------------------------------------------------------------------------
# _build_harness_adapter / helpers
# ---------------------------------------------------------------------------

class TestHarnessHelpers:
    """Tests for the adapter-construction helpers."""

    def test_builds_openai_adapter_for_ollama(self):
        from artifice_draft.config import AppConfig
        from artifice_draft.models import LLMProvider
        from artifice_draft.style_guides.scraper import _build_harness_adapter
        from model_harness.openai_adapter import OpenAIProvider
        cfg = AppConfig()
        cfg.llm_provider = LLMProvider.OLLAMA
        adapter = _build_harness_adapter(cfg)
        assert isinstance(adapter, OpenAIProvider)

    def test_builds_openai_adapter_for_openai(self):
        from artifice_draft.config import AppConfig
        from artifice_draft.models import LLMProvider
        from artifice_draft.style_guides.scraper import _build_harness_adapter
        from model_harness.openai_adapter import OpenAIProvider
        cfg = AppConfig()
        cfg.llm_provider = LLMProvider.OPENAI
        adapter = _build_harness_adapter(cfg)
        assert isinstance(adapter, OpenAIProvider)

    def test_builds_anthropic_adapter(self):
        from artifice_draft.config import AppConfig
        from artifice_draft.models import LLMProvider
        from artifice_draft.style_guides.scraper import _build_harness_adapter
        from model_harness.anthropic_adapter import AnthropicProvider
        cfg = AppConfig()
        cfg.llm_provider = LLMProvider.ANTHROPIC
        cfg.anthropic_api_key = "test-key"
        adapter = _build_harness_adapter(cfg)
        assert isinstance(adapter, AnthropicProvider)
        assert adapter._max_tokens == cfg.num_ctx

    def test_provider_string_ollama(self):
        from artifice_draft.config import AppConfig
        from artifice_draft.models import LLMProvider
        from artifice_draft.style_guides.scraper import _provider_string
        cfg = AppConfig()
        cfg.llm_provider = LLMProvider.OLLAMA
        assert _provider_string(cfg) == "ollama"

    def test_provider_string_openai(self):
        from artifice_draft.config import AppConfig
        from artifice_draft.models import LLMProvider
        from artifice_draft.style_guides.scraper import _provider_string
        cfg = AppConfig()
        cfg.llm_provider = LLMProvider.OPENAI
        assert _provider_string(cfg) == "generic-api"

    def test_provider_string_anthropic(self):
        from artifice_draft.config import AppConfig
        from artifice_draft.models import LLMProvider
        from artifice_draft.style_guides.scraper import _provider_string
        cfg = AppConfig()
        cfg.llm_provider = LLMProvider.ANTHROPIC
        assert _provider_string(cfg) == "anthropic"


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
        result = preview_guide_from_url("https://www.example.com/guide")
        mock_fetch.assert_called_once_with("https://www.example.com/guide")
        mock_parse.assert_called_once_with("Extracted author guidelines text", None)
        assert result.name == "Previewed Guide"


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

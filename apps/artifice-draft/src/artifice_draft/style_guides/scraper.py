"""Scrape a journal style guide from a URL and convert it to a StyleGuide.

Uses readability-lxml to extract the main article content from any HTML page,
then asks the LLM to parse the extracted text into the StyleGuide schema.
The result is returned (not saved) so the caller can show a review step.
"""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import urlparse

import requests

from artifice_draft.config import AppConfig
from artifice_draft.style_guides.base import StyleGuide

logger = logging.getLogger(__name__)

# --- rate-limit / safety constants ----------------------------------------- #
_MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB — journal guidelines are small
_REQUEST_TIMEOUT = 30  # seconds
_USER_AGENT = (
    "ArtificeDraft/1.0 (+https://github.com/anomalyco/opencode) "
    "style-guide-scraper"
)

# The LLM prompt that asks it to parse extracted text into StyleGuide JSON.
_EXTRACTION_SYSTEM_PROMPT = """\
You are a text analyst. You will receive the main body text of a journal's \
author guidelines or style guide webpage. Your task is to extract the editing \
rules and formatting conventions and return a JSON object matching this schema:

{
  "name": "string — the journal or style guide name",
  "edition": "string — edition or version, if stated",
  "citation_style": "string — e.g. 'notes-bibliography', 'author-date', 'MLA'",
  "footnote_format": "string — rules for footnote formatting, with examples if available",
  "bibliography_format": "string — rules for bibliography/reference list formatting",
  "heading_capitalization": "string — e.g. 'title-case', 'sentence-case'",
  "prose_rules": ["string — individual prose/style rules, one per element"],
  "quotation_rules": "string — rules for direct quotations",
  "abbreviation_rules": "string — rules for abbreviations and acronyms",
  "date_format": "string — how dates should be formatted",
  "page_reference_format": "string — how page numbers/references should appear",
  "url_format": "string — rules for URLs and DOIs",
  "system_prompt_addendum": "string — a concise summary of ALL the key editing rules, \
written as clear instructions an LLM editor should follow. This is the most important \
field: it should distill the entire style guide into actionable rules.",
  "custom_rules": ["string — any rules that don't fit the above categories"]
}

Rules:
- Return ONLY valid JSON, no markdown fences, no commentary.
- If a field is not addressed in the source text, use an empty string (or empty array).
- The system_prompt_addendum should be thorough — it is the primary text the editor \
LLM will read. Include as many concrete rules as the source text supports.
- For prose_rules, extract each distinct rule as a separate list element.
- If the source text is not a style guide at all, return an object with only \
"name" set to a description of what the page contained, and all other fields empty.
"""


def fetch_and_extract(url: str) -> str:
    """Fetch *url* and return the readable text content.

    Uses readability-lxml to strip navigation, ads, and boilerplate.
    Raises ``ValueError`` for bad URLs or network failures.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL must use http or https, got: {parsed.scheme or '(none)'}")

    try:
        resp = requests.get(
            url,
            timeout=_REQUEST_TIMEOUT,
            headers={"User-Agent": _USER_AGENT},
            allow_redirects=True,
        )
        resp.raise_for_status()
    except requests.ConnectionError as exc:
        raise ValueError(f"Could not connect to {url}: {exc}") from exc
    except requests.Timeout as exc:
        raise ValueError(f"Request timed out after {_REQUEST_TIMEOUT}s: {url}") from exc
    except requests.HTTPError as exc:
        raise ValueError(f"HTTP error fetching {url}: {exc}") from exc
    except requests.RequestException as exc:
        raise ValueError(f"Failed to fetch {url}: {exc}") from exc

    content_type = resp.headers.get("Content-Type", "")
    if "pdf" in content_type.lower():
        raise ValueError(
            "The URL points to a PDF file. Please provide a link to an HTML page."
        )

    raw = resp.content[:_MAX_RESPONSE_BYTES]
    if len(resp.content) > _MAX_RESPONSE_BYTES:
        logger.warning(
            "Response from %s exceeded %d bytes; truncated", url, _MAX_RESPONSE_BYTES
        )

    try:
        from readability import Document as ReadabilityDocument
    except ImportError:
        raise ImportError(
            "readability-lxml is required for URL import. "
            "Install it with: pip install readability-lxml"
        )

    try:
        doc = ReadabilityDocument(raw.decode("utf-8", errors="replace"))
        html_content = doc.summary()
    except Exception as exc:
        raise ValueError(f"Could not extract readable content from {url}: {exc}") from exc

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        raise ImportError(
            "beautifulsoup4 is required for URL import. "
            "Install it with: pip install beautifulsoup4"
        )

    soup = BeautifulSoup(html_content, "html.parser")
    text = soup.get_text(separator="\n", strip=True)

    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    if len(text) < 50:
        raise ValueError(
            "The page contained very little readable text. "
            "Please check the URL points to a style guide or author guidelines page."
        )

    return text


def parse_guide_with_llm(
    extracted_text: str, config: AppConfig | None = None
) -> StyleGuide:
    """Send extracted text to the LLM and parse the response into a StyleGuide.

    Raises ``ValueError`` if the LLM returns unparseable output.
    """
    if config is None:
        config = AppConfig()

    user_prompt = (
        "Below is the extracted text from a journal's author guidelines page. "
        "Parse it into the StyleGuide JSON schema.\n\n"
        f"--- BEGIN EXTRACTED TEXT ---\n{extracted_text}\n--- END EXTRACTED TEXT ---"
    )

    raw_response = _send_llm_request(
        system_prompt=_EXTRACTION_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        config=config,
    )

    cleaned = raw_response.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "The LLM returned invalid JSON. "
            "Try again, or check that your LLM provider is reachable."
        ) from exc

    if not isinstance(data, dict):
        raise ValueError("The LLM returned a JSON array instead of an object.")

    return StyleGuide.from_dict(data)


def preview_guide_from_url(
    url: str, config: AppConfig | None = None
) -> StyleGuide:
    """Fetch a URL, extract content, and parse it into a StyleGuide.

    This is the main entry point: it orchestrates fetch → extract → LLM parse.
    The result is NOT saved; the caller is responsible for showing a review and
    calling ``save_custom_guide()`` if approved.
    """
    text = fetch_and_extract(url)
    return parse_guide_with_llm(text, config)


# ---------------------------------------------------------------------------
# alternative import methods (text, docx, pdf)
# ---------------------------------------------------------------------------


def extract_text_from_docx(path: str) -> str:
    """Extract plain text paragraphs from a .docx file.

    Raises ``ValueError`` if the file cannot be read or contains no text.
    """
    try:
        from docx import Document
    except ImportError:
        raise ImportError(
            "python-docx is required to import from .docx files. "
            "Install it with: pip install python-docx"
        )

    try:
        doc = Document(path)
    except Exception as exc:
        raise ValueError(f"Could not read .docx file {path}: {exc}") from exc

    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    text = "\n\n".join(paragraphs).strip()
    if len(text) < 50:
        raise ValueError(
            "The .docx file contains very little readable text. "
            "Please check the file contains a style guide or author guidelines."
        )
    return text


def extract_text_from_pdf(path: str) -> str:
    """Extract text from a PDF file.

    Uses PyMuPDF (fitz) — install with ``pip install PyMuPDF``.
    Raises ``ValueError`` if the file cannot be read or contains no text.
    """
    try:
        import fitz
    except ImportError:
        raise ImportError(
            "PyMuPDF is required to import from PDF files. "
            "Install it with: pip install PyMuPDF"
        )

    try:
        doc = fitz.open(path)
    except Exception as exc:
        raise ValueError(f"Could not read PDF file {path}: {exc}") from exc

    pages = []
    for page_num in range(len(doc)):
        text = doc[page_num].get_text().strip()
        if text:
            pages.append(text)
    doc.close()

    text = "\n\n".join(pages).strip()
    if len(text) < 50:
        raise ValueError(
            "The PDF file contains very little readable text. "
            "Please check the file contains a style guide or author guidelines."
        )
    return text


def preview_guide_from_text(
    text: str, config: AppConfig | None = None
) -> StyleGuide:
    """Parse raw text directly into a StyleGuide via LLM.

    The result is NOT saved; the caller is responsible for showing a review
    and calling ``save_custom_guide()`` if approved.
    """
    text = text.strip()
    if len(text) < 50:
        raise ValueError(
            "The provided text is too short. "
            "Please paste at least 50 characters of a style guide or author guidelines."
        )
    return parse_guide_with_llm(text, config)


def preview_guide_from_file(
    path: str, config: AppConfig | None = None
) -> StyleGuide:
    """Read a .docx or .pdf file, extract text, and parse into a StyleGuide.

    The result is NOT saved; the caller is responsible for showing a review
    and calling ``save_custom_guide()`` if approved.
    """
    lower = path.lower()
    if lower.endswith(".docx"):
        text = extract_text_from_docx(path)
    elif lower.endswith(".pdf"):
        text = extract_text_from_pdf(path)
    else:
        raise ValueError(
            f"Unsupported file type: {path}. Please provide a .docx or .pdf file."
        )
    return parse_guide_with_llm(text, config)


# ---------------------------------------------------------------------------
# internal: raw LLM call
# ---------------------------------------------------------------------------

def _send_llm_request(
    system_prompt: str, user_prompt: str, config: AppConfig
) -> str:
    """Route a single LLM request to the configured provider."""
    if config.llm_provider.value == "ollama":
        return _send_ollama(system_prompt, user_prompt, config)
    elif config.llm_provider.value == "openai":
        return _send_openai(system_prompt, user_prompt, config)
    elif config.llm_provider.value == "anthropic":
        return _send_anthropic(system_prompt, user_prompt, config)
    raise ValueError(f"Unsupported provider: {config.llm_provider}")


def _send_ollama(
    system_prompt: str, user_prompt: str, config: AppConfig
) -> str:
    payload = {
        "model": config.active_model,
        "system": system_prompt,
        "prompt": user_prompt,
        "stream": False,
        "format": "json",
        "temperature": 0.2,
        "num_ctx": config.num_ctx,
    }
    resp = requests.post(
        config.ollama_generate_url, json=payload, timeout=120,
    )
    resp.raise_for_status()
    return resp.json().get("response", "")


def _send_openai(
    system_prompt: str, user_prompt: str, config: AppConfig
) -> str:
    url = f"{config.openai_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.active_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": config.num_ctx,
        "response_format": {"type": "json_object"},
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=120)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _send_anthropic(
    system_prompt: str, user_prompt: str, config: AppConfig
) -> str:
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": config.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.active_model,
        "max_tokens": config.num_ctx,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
        "temperature": 0.2,
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=120)
    resp.raise_for_status()
    blocks = resp.json().get("content", [])
    return " ".join(b["text"] for b in blocks if b.get("type") == "text")

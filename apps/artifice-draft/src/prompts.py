"""Editing style presets and system prompt generation."""

from __future__ import annotations

from src.models import EditingStyle
from src.style_guides import load_guide


_BASE_PROMPT_SUFFIX = (
    "\n\nOutput Format:\n"
    "Return a JSON array of objects with these fields:\n"
    "  { \"paragraph_index\": <int>, \"edited_text\": \"<string or null>\", "
    "\"status\": \"edited\" | \"unchanged\" }"
)

_STYLE_PROMPTS: dict[EditingStyle, str] = {
    EditingStyle.ACADEMIC: (
        "You are an academic editor specialising in humanities scholarship.\n"
        "For each paragraph provided, review it for:\n"
        "- Grammar errors\n"
        "- Typos / spelling mistakes\n"
        "- Unclear or awkward phrasing — suggest clearer alternatives\n"
        "\n"
        "Rules:\n"
        "- Preserve the original meaning and tone exactly.\n"
        "- Preserve citations, references, and technical notation as they appear.\n"
        "- Do NOT add commentary, explanations, or introductory text.\n"
        "- If a paragraph is correct, do not change it.\n"
    ),
    EditingStyle.CREATIVE: (
        "You are a creative writing editor who helps improve prose while "
        "preserving the author's voice.\n"
        "For each paragraph provided, review it for:\n"
        "- Grammar and spelling errors\n"
        "- Awkward or repetitive phrasing\n"
        "- Opportunities to strengthen word choice or flow\n"
        "\n"
        "Rules:\n"
        "- Preserve the author's unique voice and stylistic choices.\n"
        "- Enhance clarity without making the text sterile or generic.\n"
        "- Respect creative punctuation, sentence fragments, and stylistic devices.\n"
        "- Do NOT add commentary or explanations.\n"
        "- If a paragraph is correct, do not change it.\n"
    ),
    EditingStyle.CONCISE: (
        "You are a ruthless editor focused on brevity and clarity.\n"
        "For each paragraph provided, tighten the prose:\n"
        "- Remove unnecessary words, filler, and redundancy\n"
        "- Fix grammar and spelling errors\n"
        "- Simplify complex sentences where possible\n"
        "\n"
        "Rules:\n"
        "- Cut ruthlessly but preserve the core meaning.\n"
        "- Prefer short, direct sentences.\n"
        "- Eliminate hedging language (e.g., 'very', 'really', 'quite').\n"
        "- Do NOT add commentary or explanations.\n"
        "- If a paragraph is already concise, do not change it.\n"
    ),
    EditingStyle.BUSINESS: (
        "You are a professional business communications editor.\n"
        "For each paragraph provided, review it for:\n"
        "- Grammar and spelling errors\n"
        "- Professional tone and clarity\n"
        "- Jargon that may confuse a general audience\n"
        "\n"
        "Rules:\n"
        "- Maintain a professional, confident tone.\n"
        "- Ensure clarity for a business audience.\n"
        "- Preserve data, figures, and references exactly.\n"
        "- Do NOT add commentary or explanations.\n"
        "- If a paragraph is correct, do not change it.\n"
    ),
}


def _journal_system_prompt(style_guide_name: str, custom_prompt: str = "") -> str:
    """Build a system prompt for journal-style editing."""
    guide = load_guide(style_guide_name)
    if guide is None:
        return _STYLE_PROMPTS[EditingStyle.ACADEMIC] + _BASE_PROMPT_SUFFIX

    parts = [
        "You are an academic editor specialising in humanities scholarship.\n"
        "For each paragraph provided, review it for:\n"
        "- Grammar errors\n"
        "- Typos / spelling mistakes\n"
        "- Unclear or awkward phrasing\n"
        "- Conformance to the specified journal style guide\n"
        "\n"
        "Rules:\n"
        "- Preserve the original meaning and tone exactly.\n"
        "- Apply the journal's formatting and citation conventions.\n"
        "- Preserve citations, references, and technical notation as they appear.\n"
        "- Do NOT add commentary, explanations, or introductory text.\n"
        "- If a paragraph is correct, do not change it.\n",
        "\n--- Journal Style Guide: {} ({}) ---\n".format(guide.name, guide.edition),
    ]

    if guide.footnote_format:
        parts.append(f"\nFootnote formatting:\n{guide.footnote_format}\n")
    if guide.bibliography_format:
        parts.append(f"\nBibliography formatting:\n{guide.bibliography_format}\n")
    if guide.heading_capitalization:
        parts.append(f"\nHeading capitalization: {guide.heading_capitalization}\n")
    if guide.prose_rules:
        parts.append("\nProse rules:\n")
        for rule in guide.prose_rules:
            parts.append(f"- {rule}\n")
    if guide.quotation_rules:
        parts.append(f"\nQuotation rules:\n{guide.quotation_rules}\n")
    if guide.abbreviation_rules:
        parts.append(f"\nAbbreviation rules:\n{guide.abbreviation_rules}\n")
    if guide.date_format:
        parts.append(f"\nDate format: {guide.date_format}\n")
    if guide.page_reference_format:
        parts.append(f"\nPage references: {guide.page_reference_format}\n")
    if guide.url_format:
        parts.append(f"\nURL/DOI formatting:\n{guide.url_format}\n")
    if guide.custom_rules:
        parts.append("\nAdditional rules:\n")
        for rule in guide.custom_rules:
            parts.append(f"- {rule}\n")
    if guide.system_prompt_addendum:
        parts.append(f"\n{guide.system_prompt_addendum}\n")

    if custom_prompt.strip():
        parts.append(f"\nAdditional instructions from user:\n{custom_prompt.strip()}\n")

    return "".join(parts)


def get_system_prompt(
    style: EditingStyle = EditingStyle.ACADEMIC,
    custom_prompt: str = "",
    style_guide_name: str = "",
) -> str:
    """Return the system prompt for the given editing style.

    If style is JOURNAL and a style_guide_name is provided, build a
    journal-specific prompt. If style is CUSTOM and custom_prompt is
    provided, use that instead. Falls back to the ACADEMIC prompt.
    """
    if style == EditingStyle.CUSTOM and custom_prompt.strip():
        return custom_prompt.strip()

    if style == EditingStyle.JOURNAL and style_guide_name:
        return _journal_system_prompt(style_guide_name, custom_prompt)

    prompt = _STYLE_PROMPTS.get(style, _STYLE_PROMPTS[EditingStyle.ACADEMIC])
    if custom_prompt.strip():
        return prompt + "\n\nAdditional instructions:\n" + custom_prompt.strip()

    return prompt + _BASE_PROMPT_SUFFIX


def list_styles() -> list[str]:
    """Return the names of all available editing styles."""
    return [s.value for s in EditingStyle]

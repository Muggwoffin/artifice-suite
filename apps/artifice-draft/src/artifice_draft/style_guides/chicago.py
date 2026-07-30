# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

"""Built-in Chicago Manual of Style (17th edition) style guide."""

from __future__ import annotations

from .base import StyleGuide


def chicago_guide() -> StyleGuide:
    return StyleGuide(
        name="Chicago Manual of Style",
        edition="17th Edition",
        citation_style="notes-bibliography",
        footnote_format=(
            "First footnote: First Name Last Name, Title in Italicized Case "
            "(Place: Publisher, Year), page number.\n"
            "Subsequent footnotes: Last Name, Shortened Title, page number.\n"
            "Ibid. may be used for consecutive references to the same source.\n"
            "Example: 1. Joan W. Scott, Gender and the Politics of History "
            "(New York: Columbia University Press, 1988), 25."
        ),
        bibliography_format=(
            "Last Name, First Name. Title in Italicized Case. Place: Publisher, Year.\n"
            "Example: Scott, Joan W. Gender and the Politics of History. "
            "New York: Columbia University Press, 1988."
        ),
        heading_capitalization="title-case",
        prose_rules=[
            "Use Title Case for all headings and subheadings.",
            "Use the serial (Oxford) comma before the final 'and' or 'or' in a list of three or more items.",
            "Use em dashes (—) for parenthetical statements, not en dashes.",
            "Do not use a period after headings.",
            "Use scare quotes for unfamiliar or ironic terms on first use only.",
            "Write out numbers one through one hundred; use numerals for 101 and above.",
            "Use 'while' only to mean 'during the time that,' not 'whereas.'",
            "Prefer active voice; use passive voice only when the actor is unknown or unimportant.",
            "Avoid beginning sentences with numerals; spell out or restructure.",
            "Use 'percent' (not '%') in running text.",
        ],
        quotation_rules=(
            "Use double quotation marks for all quotations in the text.\n"
            "Use single quotation marks only for quotations within quotations.\n"
            "Block quotes: use for prose quotations of more than 100 words or "
            "more than two paragraphs. Indent the entire block one-half inch from "
            "the left margin, omit quotation marks, and do not indent the first line."
        ),
        abbreviation_rules=(
            "Spell out all acronyms and abbreviations on first use, followed by the "
            "abbreviation in parentheses. Use the abbreviation thereafter.\n"
            "Use 'et al.' only in parenthetical citations and notes, not in running text.\n"
            "Use 'ibid.' sparingly and only for immediate consecutive references.\n"
            "Do not use 'cf.' — use 'see' instead."
        ),
        date_format="d MMMM yyyy (e.g., 12 March 1945)",
        page_reference_format="page number (e.g., 25 or 25-27)",
        url_format=(
            "Include a URL or DOI as the final element of a footnote or bibliography entry.\n"
            "Access dates are recommended for online sources that may change.\n"
            "Format: Accessed Month Day, Year. URL"
        ),
        system_prompt_addendum=(
            "IMPORTANT: This document must conform to the Chicago Manual of Style (17th edition).\n\n"
            "Apply the following Chicago-style rules when editing:\n"
            "- Use the Notes-Bibliography citation system. Footnotes should follow Chicago format.\n"
            "- Use Title Case for all headings.\n"
            "- Use the serial (Oxford) comma consistently.\n"
            "- Use double quotation marks for text quotations; single quotes only within double quotes.\n"
            "- Block-quote any prose quotation exceeding 100 words (indent, no quotation marks).\n"
            "- Use em dashes (—), not en dashes, for parenthetical breaks.\n"
            "- Spell out numbers one through one hundred; use numerals above.\n"
            "- Use 'percent' not '%' in running text.\n"
            "- Dates: day-month-year (12 March 1945), no ordinal suffixes.\n"
            "- Spell out acronyms on first use with abbreviation in parentheses.\n"
            "- Prefer active voice. Use passive only when the agent is unknown.\n"
            "- Do not use 'cf.' — use 'see' instead for cross-references.\n"
        ),
    )

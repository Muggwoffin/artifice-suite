# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

"""Built-in APA (7th edition) style guide."""

from __future__ import annotations

from .base import StyleGuide


def apa_guide() -> StyleGuide:
    return StyleGuide(
        name="APA",
        edition="7th Edition",
        citation_style="author-date",
        footnote_format=(
            "APA does not use footnotes for citations. Use parenthetical "
            "author-date references: (Author, Year, p. X).\n"
            "Footnotes may be used for supplementary content only."
        ),
        bibliography_format=(
            "Title this list 'References.'\n"
            "Last Name, First Initial. (Year). Title of article in sentence case. "
            "Journal Name in Title Case and Italics, Volume(Issue), pages. DOI\n"
            "Use hanging indentation."
        ),
        heading_capitalization="sentence-case",
        prose_rules=[
            "Use sentence case for all headings (capitalize only the first word and proper nouns).",
            "Use the serial (Oxford) comma in all lists.",
            "Use active voice preferred; use passive voice only when the agent is unknown.",
            "Use bias-free and inclusive language.",
            "Use past tense for describing results; present tense for discussing implications.",
            "Use numerals for numbers 10 and above; spell out numbers below 10.",
            "Use 'and' in narrative citations and '&' in parenthetical citations.",
            "Abbreviate journal names following the APA Journal Abbreviation List.",
        ],
        quotation_rules=(
            "Use double quotation marks for all in-text quotations.\n"
            "Block quotes: use for direct quotations of 40 or more words. "
            "Indent the entire block 0.5 inches from the left margin, "
            "omit quotation marks, and include the author, year, and page number."
        ),
        abbreviation_rules=(
            "Spell out acronyms on first use with the abbreviation in parentheses.\n"
            "Use 'et al.' for works with three or more authors from the first citation.\n"
            "Do not use 'ibid.' or Latin abbreviations in running text."
        ),
        date_format="Month Day, Year (e.g., March 12, 1945)",
        page_reference_format="p. # or pp. #-# (e.g., p. 25 or pp. 25-27)",
        url_format=(
            "Include a DOI as a hyperlink (https://doi.org/xxxxx) at the end of references.\n"
            "Do not include 'Retrieved from' unless a retrieval date is needed.\n"
            "Include DOIs for all works that have them."
        ),
        system_prompt_addendum=(
            "IMPORTANT: This document must conform to APA style (7th edition).\n\n"
            "Apply the following APA-style rules when editing:\n"
            "- Use author-date parenthetical citations: (Author, Year).\n"
            "- Use sentence case for headings (capitalize only the first word and proper nouns).\n"
            "- Use the serial (Oxford) comma consistently.\n"
            "- Use 'and' in narrative citations ('Smith and Jones, 2020') and '&' in parenthetical ('Smith & Jones, 2020').\n"
            "- Use 'et al.' for three or more authors from the first citation.\n"
            "- Block-quote direct quotations of 40 or more words (indent 0.5 inches).\n"
            "- Spell out numbers below 10; use numerals for 10 and above.\n"
            "- Use active voice preferred; passive voice only when the agent is unknown.\n"
            "- Use bias-free, inclusive language throughout.\n"
            "- Include DOIs as hyperlinks in all references.\n"
            "- Use past tense for describing methods and results.\n"
        ),
    )

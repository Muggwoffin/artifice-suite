# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

"""Built-in MLA (9th edition) style guide."""

from __future__ import annotations

from .base import StyleGuide


def mla_guide() -> StyleGuide:
    return StyleGuide(
        name="MLA",
        edition="9th Edition",
        citation_style="author-page parenthetical",
        footnote_format=(
            "MLA does not typically use footnotes for citations. Use parenthetical "
            "author-page references: (Author Page).\n"
            "Endnotes may be used sparingly for supplementary information, not citations."
        ),
        bibliography_format=(
            "Title this list 'Works Cited.'\n"
            "Last Name, First Name. Title of Source. Container, Other Contributors, "
            "Version, Number, Publisher, Publication Date, Location.\n"
            "Use hanging indentation (first line flush left, subsequent lines indented 0.5 inches)."
        ),
        heading_capitalization="sentence-case",
        prose_rules=[
            "Use sentence case for all headings (capitalize only the first word and proper nouns).",
            "Write in present tense when discussing literature or texts.",
            "Use the serial comma only when clarity requires it (MLA is flexible here).",
            "Use inclusive language and avoid gendered pronouns for generic references.",
            "Italicize titles of longer works (books, journals, films); use quotation marks for shorter works (articles, poems, chapters).",
            "Write out numbers that can be expressed in one or two words; use numerals for others.",
            "Use 'al.' not 'et al.' in parenthetical citations with three or more authors.",
        ],
        quotation_rules=(
            "Use double quotation marks for quotations in the text.\n"
            "Use single quotation marks only for quotations within quotations.\n"
            "Block quotes: use for prose quotations of four or more lines (or "
            "more than three lines of poetry). Indent one-half inch from the left "
            "margin, omit quotation marks."
        ),
        abbreviation_rules=(
            "Spell out acronyms on first use with the abbreviation in parentheses.\n"
            "MLA does not use 'ibid.' or 'op. cit.'\n"
            "Use 'et al.' in parenthetical citations when a source has three or more authors."
        ),
        date_format="Month Day, Year (e.g., March 12, 1945)",
        page_reference_format="page number with no 'p.' or 'pp.' (e.g., 25)",
        url_format=(
            "Include a DOI or URL at the end of the Works Cited entry.\n"
            "Do not include 'Accessed' dates unless no publication date is available.\n"
            "Use https:// in URLs."
        ),
        system_prompt_addendum=(
            "IMPORTANT: This document must conform to MLA style (9th edition).\n\n"
            "Apply the following MLA-style rules when editing:\n"
            "- Use parenthetical author-page citations, not footnotes.\n"
            "- Use sentence case for headings (capitalize only the first word and proper nouns).\n"
            "- Write in present tense when discussing texts ('Shakespeare writes' not 'Shakespeare wrote').\n"
            "- Italicize titles of longer works; use quotation marks for shorter works.\n"
            "- Block-quote prose of four or more lines (indent 0.5 inches, no quotation marks).\n"
            "- Use 'et al.' for three or more authors in parenthetical citations.\n"
            "- Do not use 'ibid.' or 'op. cit.' — use parenthetical citations instead.\n"
            "- Spell out numbers expressible in one or two words.\n"
            "- Use inclusive, non-gendered language for generic references.\n"
        ),
    )

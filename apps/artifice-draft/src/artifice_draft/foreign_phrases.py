# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Latin and foreign phrase italicization and consistency checking."""

from __future__ import annotations

import re
from dataclasses import dataclass

from artifice_draft.style_guides import load_guide

# Common Latin phrases used in academic writing
_LATIN_PHRASES = [
    "ad hoc", "ad hominem", "caveat emptor", "de facto", "de jure",
    "et al.", "et cetera", "ex officio", "ex post facto",
    "ibid.", "id.", "in loco parentis", "in medias res", "in vitro",
    "ipse dixit", "loc. cit.", "magnum opus", "mea culpa",
    "nota bene", "op. cit.", "per capita", "per se", "post hoc",
    "prima facie", "pro bono", "pro rata", "pro tem",
    "quid pro quo", "sic", "tabula rasa", "terra incognita",
    "vice versa", "vis-à-vis",
]

# Build regex pattern from phrases (sorted longest first to avoid partial matches)
_PHRASE_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(p) for p in sorted(_LATIN_PHRASES, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

# Phrases that should typically be italicized
_SHOULD_ITALICIZE = {
    "ad hoc", "ad hominem", "caveat emptor", "de facto", "de jure",
    "in medias res", "in vitro", "ipse dixit",
    "magnum opus", "mea culpa", "nota bene",
    "per se", "prima facie", "pro bono", "pro rata", "pro tem",
    "quid pro quo", "sic", "tabula rasa", "terra incognita",
    "vice versa", "vis-à-vis",
}

# Abbreviation-style Latin terms (should NOT be italicized)
_NO_ITALICIZE = {"et al.", "ibid.", "id.", "loc. cit.", "op. cit.", "e.g.", "i.e.", "etc."}


@dataclass
class ForeignPhraseAdvisory:
    """A single foreign phrase formatting advisory."""

    paragraph_index: int
    rule: str
    message: str
    severity: str  # "warning" | "info"
    original_text: str = ""


def check_foreign_phrases(
    paragraphs: list[dict],
    guide_name: str = "",
) -> list[ForeignPhraseAdvisory]:
    """Check Latin/foreign phrase formatting and consistency.

    Args:
        paragraphs: Parsed paragraph dicts from doc_parser.
        guide_name: Name of the active style guide.

    Returns:
        List of ForeignPhraseAdvisory objects.
    """
    advisories: list[ForeignPhraseAdvisory] = []
    guide = load_guide(guide_name) if guide_name else None

    # Track occurrences of phrases for consistency checks
    phrase_occurrences: dict[str, list[tuple[int, bool]]] = {}  # phrase -> [(para_idx, is_italic)]

    for para in paragraphs:
        idx = para["paragraph_index"]
        text = para["text"]
        is_italic = para.get("is_italic", False)

        for match in _PHRASE_PATTERN.finditer(text):
            phrase = match.group(1).lower().rstrip(".")

            # Check italicization
            if phrase in _SHOULD_ITALICIZE and not is_italic:
                advisories.append(ForeignPhraseAdvisory(
                    paragraph_index=idx,
                    rule="latin_italicization",
                    message=f"'{match.group(1)}' is a Latin phrase that should typically be italicized.",
                    severity="info",
                    original_text=match.group(1),
                ))

            # Track for consistency
            phrase_occurrences.setdefault(phrase, []).append((idx, is_italic))

    # Check consistency of "et al." usage
    et_al_occurrences = []
    for para in paragraphs:
        if re.search(r"\bet al\.?\b", para["text"], re.IGNORECASE) or re.search(r"\bet al\.?\s", para["text"], re.IGNORECASE):
            et_al_occurrences.append(para["paragraph_index"])

    if et_al_occurrences:
        # Check if "et al." and "and others" are mixed
        and_others = [
            para["paragraph_index"]
            for para in paragraphs
            if re.search(r"\band others\b", para["text"], re.IGNORECASE)
        ]
        if and_others:
            advisories.append(ForeignPhraseAdvisory(
                paragraph_index=and_others[0],
                rule="et_al_consistency",
                message="Mix of 'et al.' and 'and others' detected — pick one and use it consistently.",
                severity="warning",
            ))

    # Check "ibid." usage against guide
    if guide:
        ibid_paras = [
            para["paragraph_index"]
            for para in paragraphs
            if re.search(r"\bibid\.?\b", para["text"], re.IGNORECASE)
        ]
        if ibid_paras:
            abbrev_rules = (guide.abbreviation_rules or "").lower()
            if "not" in abbrev_rules and "ibid" in abbrev_rules:
                advisories.append(ForeignPhraseAdvisory(
                    paragraph_index=ibid_paras[0],
                    rule="ibid_deprecated",
                    message="This style guide discourages 'ibid.' — use a shortened citation instead.",
                    severity="info",
                ))

    return advisories

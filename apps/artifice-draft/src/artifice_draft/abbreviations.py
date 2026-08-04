# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Abbreviation extraction and validation module for academic papers."""

from __future__ import annotations

import re
from typing import TypedDict


class AbbreviationIssue(TypedDict):
    paragraph_index: int
    abbreviation: str
    message: str


def check_abbreviations(paragraphs: list[dict]) -> list[AbbreviationIssue]:
    """Scan paragraphs for uppercase abbreviations (2-6 letters) and verify

    whether they are introduced with a definition on first use.
    """
    issues: list[AbbreviationIssue] = []
    seen_defs: set[str] = set()

    # Pattern for uppercase acronyms: 2 to 6 capital letters
    acronym_pattern = re.compile(r'\b[A-Z]{2,6}\b')

    for entry in paragraphs:
        text = entry.get("text", "")
        idx = entry.get("paragraph_index", 0)

        matches = acronym_pattern.findall(text)
        for acr in matches:
            # Common false positives in academic writing
            if acr in {"I", "A", "THE", "AND", "FOR", "BUT", "OR", "IN", "ON", "BY", "WITH"}:
                continue

            # Check if defined in this paragraph or earlier
            # Definition pattern: "Full Name (ACR)" or "ACR (Full Name)"
            def_pattern1 = re.compile(rf'.*?\(({acr})\)')
            def_pattern2 = re.compile(rf'({acr})\s+\(.*?\)')

            if acr in seen_defs:
                continue

            if def_pattern1.search(text) or def_pattern2.search(text):
                seen_defs.add(acr)
            else:
                # If not seen yet and not defined here, flag it as potentially undefined
                # (unless it's a very standard abbreviation like US, UK, etc.)
                if acr not in {"US", "UK", "EU", "UN", "BCE", "CE", "AD", "BC"}:
                    # Check if defined later or earlier across document
                    is_defined_elsewhere = False
                    for other in paragraphs:
                        otext = other.get("text", "")
                        if def_pattern1.search(otext) or def_pattern2.search(otext):
                            is_defined_elsewhere = True
                            break

                    if not is_defined_elsewhere and acr not in seen_defs:
                        seen_defs.add(acr) # Report once per document to avoid spam
                        issues.append({
                            "paragraph_index": idx,
                            "abbreviation": acr,
                            "message": f"Abbreviation '{acr}' used without explicit definition/expansion.",
                        })

    return issues

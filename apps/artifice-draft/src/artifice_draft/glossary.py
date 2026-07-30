# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

"""Custom glossary and terminology enforcement module."""

from __future__ import annotations

import re
from typing import TypedDict


class GlossaryIssue(TypedDict):
    paragraph_index: int
    term: str
    message: str


def check_glossary(paragraphs: list[dict], glossary: dict[str, str]) -> list[GlossaryIssue]:
    """Check paragraphs for prohibited terms or preferred terminology replacements.

    Glossary maps prohibited/variant term -> preferred term.
    """
    issues: list[GlossaryIssue] = []
    if not glossary:
        return issues

    for entry in paragraphs:
        text = entry.get("text", "")
        idx = entry.get("paragraph_index", 0)

        for term, preferred in glossary.items():
            pattern = re.compile(rf'\b{re.escape(term)}\b', re.IGNORECASE)
            if pattern.search(text):
                issues.append({
                    "paragraph_index": idx,
                    "term": term,
                    "message": f"Non-preferred terminology '{term}' used. Recommended: '{preferred}'.",
                })

    return issues

# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

"""Cross-document consistency checks for proper nouns and naming."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class ConsistencyAdvisory:
    """A single consistency advisory."""

    paragraph_index: int
    rule: str
    message: str
    severity: str  # "warning" | "info"
    occurrences: list[int] | None = None


def _extract_proper_nouns(text: str) -> list[str]:
    """Extract words that look like proper nouns (capitalized, not at sentence start)."""
    words = re.findall(r"\b([A-Z][a-z]{2,})\b", text)
    return words


def _extract_names(text: str) -> list[str]:
    """Extract potential personal names (two or three consecutive capitalized words)."""
    names = re.findall(r"\b([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b", text)
    return names


def check_consistency(
    paragraphs: list[dict],
) -> list[ConsistencyAdvisory]:
    """Check for naming and spelling consistency across the document.

    Args:
        paragraphs: Parsed paragraph dicts from doc_parser.

    Returns:
        List of ConsistencyAdvisory objects.
    """
    advisories: list[ConsistencyAdvisory] = []

    # Track all proper nouns and their paragraph occurrences
    proper_noun_map: dict[str, list[int]] = defaultdict(list)
    name_map: dict[str, list[int]] = defaultdict(list)

    for para in paragraphs:
        idx = para["paragraph_index"]
        text = para["text"]

        for noun in _extract_proper_nouns(text):
            proper_noun_map[noun].append(idx)

        for name in _extract_names(text):
            name_map[name].append(idx)

    # Check for inconsistent capitalization of the same word
    case_groups: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for noun, indices in proper_noun_map.items():
        lower = noun.lower()
        case_groups[lower][noun].extend(indices)

    for lower, variants in case_groups.items():
        if len(variants) > 1:
            forms = sorted(variants.keys())
            all_indices = []
            for indices in variants.values():
                all_indices.extend(indices)
            advisories.append(ConsistencyAdvisory(
                paragraph_index=min(all_indices),
                rule="inconsistent_capitalization",
                message=(
                    f"Inconsistent capitalization of '{forms[0]}': "
                    f"found {', '.join(forms)}. "
                    f"Use one form consistently."
                ),
                severity="warning",
                occurrences=sorted(set(all_indices)),
            ))

    # Check for variant spellings of names (multi-word)
    name_variants: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for name, indices in name_map.items():
        normalized = name.lower().replace(" ", "")
        name_variants[normalized][name].extend(indices)

    for normalized, variants in name_variants.items():
        if len(variants) > 1:
            forms = sorted(variants.keys())
            all_indices = []
            for indices in variants.values():
                all_indices.extend(indices)
            advisories.append(ConsistencyAdvisory(
                paragraph_index=min(all_indices),
                rule="inconsistent_name_spelling",
                message=(
                    f"Inconsistent spelling of name: "
                    f"found {', '.join(forms)}. "
                    f"Use one form consistently."
                ),
                severity="warning",
                occurrences=sorted(set(all_indices)),
            ))

    return advisories

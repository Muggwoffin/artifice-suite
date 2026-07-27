"""Footnote and citation validation against journal style guide rules."""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.style_guides import load_guide


@dataclass
class CitationAdvisory:
    """A single citation formatting advisory."""

    paragraph_index: int
    rule: str
    message: str
    severity: str  # "warning" | "info"
    suggested_fix: str | None = None


# Patterns for common footnote markers
_FOOTNOTE_MARKER_RE = re.compile(r"\[\^(\d+)\]|(?<!\d)(\d+)(?=\s|$|[.,;:])")
_SUPERSCRIPT_RE = re.compile(r"\[\^(\d+)\]")

# Patterns for footnote bodies (indented paragraphs or those starting with a number)
_FOOTNOTE_BODY_RE = re.compile(r"^\s*(\d+)\.\s")

# Latin abbreviations commonly found in footnotes
_IBID_RE = re.compile(r"\bibid\.?\b", re.IGNORECASE)
_OP_CIT_RE = re.compile(r"\bop\.\s*cit\.?\b", re.IGNORECASE)
_LOC_CIT_RE = re.compile(r"\bloc\.\s*cit\.?\b", re.IGNORECASE)


def check_citations(
    paragraphs: list[dict],
    guide_name: str = "",
) -> list[CitationAdvisory]:
    """Check footnote/citation formatting against journal rules.

    Args:
        paragraphs: Parsed paragraph dicts from doc_parser.
        guide_name: Name of the active style guide (e.g., "chicago").

    Returns:
        List of CitationAdvisory objects describing issues found.
    """
    advisories: list[CitationAdvisory] = []

    guide = load_guide(guide_name) if guide_name else None

    marker_indices: dict[int, int] = {}  # footnote number -> paragraph index
    body_indices: dict[int, int] = {}  # footnote number -> paragraph index

    body_para_indices: set[int] = set()

    for para in paragraphs:
        idx = para["paragraph_index"]
        text = para["text"]

        # Check if this is a footnote body first
        body_match = _FOOTNOTE_BODY_RE.match(text)
        if body_match:
            num = int(body_match.group(1))
            body_indices[num] = idx
            body_para_indices.add(idx)

    for para in paragraphs:
        idx = para["paragraph_index"]
        text = para["text"]

        # Skip footnote body paragraphs for marker collection
        if idx in body_para_indices:
            continue

        # Collect footnote markers in body text
        for match in _FOOTNOTE_MARKER_RE.finditer(text):
            num_str = match.group(1) or match.group(2)
            if num_str:
                num = int(num_str)
                if num not in marker_indices:
                    marker_indices[num] = idx

    # Check for footnote numbering gaps and orphans
    all_numbers = sorted(set(list(marker_indices.keys()) + list(body_indices.keys())))
    if all_numbers:
        for i in range(1, max(all_numbers) + 1):
            if i not in marker_indices and i not in body_indices:
                continue
            if i not in marker_indices and i in body_indices:
                advisories.append(CitationAdvisory(
                    paragraph_index=body_indices.get(i, 0),
                    rule="footnote_orphan_body",
                    message=f"Footnote body {i} exists but is never referenced in the text.",
                    severity="warning",
                ))
            elif i in marker_indices and i not in body_indices:
                advisories.append(CitationAdvisory(
                    paragraph_index=marker_indices[i],
                    rule="footnote_orphan_marker",
                    message=f"Footnote marker [{i}] is referenced but no corresponding footnote body exists.",
                    severity="warning",
                ))

    # Check for duplicate footnote numbers
    seen_markers: dict[int, list[int]] = {}
    for para in paragraphs:
        idx = para["paragraph_index"]
        for match in _FOOTNOTE_MARKER_RE.finditer(para["text"]):
            num_str = match.group(1) or match.group(2)
            if num_str:
                num = int(num_str)
                seen_markers.setdefault(num, []).append(idx)

    for num, indices in seen_markers.items():
        if len(indices) > 1:
            advisories.append(CitationAdvisory(
                paragraph_index=indices[0],
                rule="duplicate_footnote_marker",
                message=f"Footnote marker [{num}] appears multiple times (paragraphs {[i + 1 for i in indices]}).",
                severity="warning",
            ))

    # Check Latin abbreviation usage against guide rules
    if guide:
        for para in paragraphs:
            idx = para["paragraph_index"]
            text = para["text"]

            if _IBID_RE.search(text):
                if "ibid" in (guide.abbreviation_rules or "").lower() and "not" in (guide.abbreviation_rules or "").lower():
                    advisories.append(CitationAdvisory(
                        paragraph_index=idx,
                        rule="ibid_usage",
                        message="This style guide discourages 'ibid.' — use a shortened citation instead.",
                        severity="info",
                    ))

            if _OP_CIT_RE.search(text):
                advisories.append(CitationAdvisory(
                    paragraph_index=idx,
                    rule="op_cit_usage",
                    message="'op. cit.' is deprecated in most modern style guides — use a shortened citation.",
                    severity="info",
                ))

            if _LOC_CIT_RE.search(text):
                advisories.append(CitationAdvisory(
                    paragraph_index=idx,
                    rule="loc_cit_usage",
                    message="'loc. cit.' is deprecated in most modern style guides.",
                    severity="info",
                ))

    return advisories

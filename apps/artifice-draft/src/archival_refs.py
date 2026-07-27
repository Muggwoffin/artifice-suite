"""Archival citation format validation."""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.style_guides import load_guide

# Patterns for common archival citation elements
_ARCHIVE_RE = re.compile(
    r"\b(archive|archives|repository|fonds|collection|group|series)\b",
    re.IGNORECASE,
)

_BOX_FOLDER_RE = re.compile(
    r"\b(Box|Folders?|File|Item|Folder)\s+[\d\w]",
    re.IGNORECASE,
)

_DATE_PATTERN_RE = re.compile(
    r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+\d{4}\b",
    re.IGNORECASE,
)

# Patterns suggesting an incomplete archival reference
_INCOMPLETE_RE = re.compile(
    r"(?:Box|Folders?|File)\s+\d+",
    re.IGNORECASE,
)

_REPOSITORY_ABBREVS = re.compile(
    r"\b(NARA|TNA|PRO|LC|LOC|Yale|Harvard|Princeton|Columbia)\b"
)


@dataclass
class ArchivalAdvisory:
    """A single archival reference advisory."""

    paragraph_index: int
    rule: str
    message: str
    severity: str  # "warning" | "info"
    suggested_fix: str | None = None


def check_archival_refs(
    paragraphs: list[dict],
    guide_name: str = "",
) -> list[ArchivalAdvisory]:
    """Check archival citation formatting.

    Validates that archival references include the essential components:
    repository name, collection/fonds, box/folder, and date.

    Args:
        paragraphs: Parsed paragraph dicts from doc_parser.
        guide_name: Name of the active style guide.

    Returns:
        List of ArchivalAdvisory objects.
    """
    advisories: list[ArchivalAdvisory] = []

    for para in paragraphs:
        idx = para["paragraph_index"]
        text = para["text"]

        has_box_folder = bool(_BOX_FOLDER_RE.search(text))
        has_date = bool(_DATE_PATTERN_RE.search(text))
        has_archive_word = bool(_ARCHIVE_RE.search(text))
        has_repository = bool(_REPOSITORY_ABBREVS.search(text))

        # If a box/folder reference exists but no date
        if has_box_folder and not has_date:
            advisories.append(ArchivalAdvisory(
                paragraph_index=idx,
                rule="archival_missing_date",
                message="Archival reference includes box/folder but no date — add the date range of the materials.",
                severity="warning",
            ))

        # If archival language is used but no repository name
        if has_archive_word and not has_repository and not has_box_folder:
            advisories.append(ArchivalAdvisory(
                paragraph_index=idx,
                rule="archival_missing_repository",
                message="Reference mentions archives but does not identify the repository — add the full repository name.",
                severity="info",
            ))

        # If box/folder is referenced without a collection name
        if has_box_folder and not has_archive_word and not has_repository:
            # Check if there's context that looks like a collection name nearby
            box_match = _INCOMPLETE_RE.search(text)
            if box_match:
                advisories.append(ArchivalAdvisory(
                    paragraph_index=idx,
                    rule="archival_incomplete_reference",
                    message=(
                        f"Archival reference near '{box_match.group()}' may be incomplete — "
                        f"include repository name, collection name, and date."
                    ),
                    severity="info",
                ))

    return advisories

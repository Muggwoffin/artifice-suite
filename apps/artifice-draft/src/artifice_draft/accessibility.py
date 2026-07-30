# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

"""Accessibility and structural document hierarchy checker."""

from __future__ import annotations

from typing import TypedDict


class AccessibilityIssue(TypedDict):
    paragraph_index: int
    issue_type: str
    message: str


def check_accessibility(paragraphs: list[dict]) -> list[AccessibilityIssue]:
    """Check heading hierarchy (no skipped levels like Heading 1 to Heading 3)

    and verify images have descriptions/alt text where applicable.
    """
    issues: list[AccessibilityIssue] = []
    last_heading_level = 0

    for entry in paragraphs:
        idx = entry.get("paragraph_index", 0)
        style_name = entry.get("style_name", "")
        images = entry.get("images", [])

        # Check heading hierarchy
        if style_name.startswith("Heading "):
            try:
                level = int(style_name.replace("Heading ", ""))
                if last_heading_level > 0 and level > last_heading_level + 1:
                    issues.append({
                        "paragraph_index": idx,
                        "issue_type": "heading_hierarchy",
                        "message": f"Skipped heading level: Heading {level} follows Heading {last_heading_level}.",
                    })
                last_heading_level = level
            except ValueError:
                pass

        # Check images for alt text / descriptions
        if images:
            for img in images:
                if not img.get("description"):
                    issues.append({
                        "paragraph_index": idx,
                        "issue_type": "missing_alt_text",
                        "message": f"Embedded image '{img.get('filename', 'unknown')}' lacks descriptive alt text for accessibility.",
                    })

    return issues

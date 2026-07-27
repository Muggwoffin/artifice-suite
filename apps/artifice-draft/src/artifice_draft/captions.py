"""Figure and table caption normalization and validation module."""

from __future__ import annotations

import re
from typing import TypedDict


class CaptionIssue(TypedDict):
    paragraph_index: int
    caption_type: str
    message: str


def check_captions(paragraphs: list[dict]) -> list[CaptionIssue]:
    """Validate figure and table captions for consistent numbering and style."""
    issues: list[CaptionIssue] = []

    fig_pattern = re.compile(r'^(Figure|Fig\.?)\s+(\d+)', re.IGNORECASE)
    table_pattern = re.compile(r'^(Table|Tab\.?)\s+(\d+)', re.IGNORECASE)

    fig_numbers: list[int] = []
    table_numbers: list[int] = []

    for entry in paragraphs:
        text = entry.get("text", "").strip()
        idx = entry.get("paragraph_index", 0)

        f_match = fig_pattern.match(text)
        if f_match:
            num = int(f_match.group(2))
            fig_numbers.append(num)
            # Check style prefix
            prefix = f_match.group(1)
            if prefix.lower() == "fig" and not prefix.endswith("."):
                issues.append({
                    "paragraph_index": idx,
                    "caption_type": "figure",
                    "message": f"Abbreviated figure prefix '{prefix}' should include a period ('Fig.') or be spelled out ('Figure').",
                })

        t_match = table_pattern.match(text)
        if t_match:
            num = int(t_match.group(2))
            table_numbers.append(num)

    # Check for sequential numbering
    for i in range(1, len(fig_numbers)):
        if fig_numbers[i] != fig_numbers[i - 1] + 1:
            issues.append({
                "paragraph_index": -1,
                "caption_type": "figure",
                "message": f"Figure numbers are not strictly sequential: found {fig_numbers[i-1]} followed by {fig_numbers[i]}.",
            })

    for i in range(1, len(table_numbers)):
        if table_numbers[i] != table_numbers[i - 1] + 1:
            issues.append({
                "paragraph_index": -1,
                "caption_type": "table",
                "message": f"Table numbers are not strictly sequential: found {table_numbers[i-1]} followed by {table_numbers[i]}.",
            })

    return issues

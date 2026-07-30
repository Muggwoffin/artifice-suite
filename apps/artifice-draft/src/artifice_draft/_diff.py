# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

"""Word-level diff ranges between an original and an edited paragraph.

Used by the web review screen to highlight what an LLM edit actually changed,
the same way a track-changes view would, without waiting for Word to open the
file. Built on the standard library's ``difflib`` — no new dependency.
"""

from __future__ import annotations

import difflib
import re

_WORD_RE = re.compile(r"\S+|\s+")


def _tokenize(text: str) -> list[str]:
    """Split into words and whitespace runs, so ranges land on word boundaries."""
    return _WORD_RE.findall(text)


def diff_ranges(original: str, edited: str) -> tuple[list[tuple[int, int, str]], list[tuple[int, int, str]]]:
    """Return (original_ranges, edited_ranges), each a list of (start, end, tag)
    character offsets into the respective string. ``tag`` is one of
    "delete_" (present in original, removed), "insert_" (present in edited,
    added), or "replace_" (changed on both sides) — matching the CSS class
    names the review screen's ``mark.hl-*`` rules key off.
    """
    orig_tokens = _tokenize(original)
    edit_tokens = _tokenize(edited)
    matcher = difflib.SequenceMatcher(a=orig_tokens, b=edit_tokens, autojunk=False)

    orig_ranges: list[tuple[int, int, str]] = []
    edit_ranges: list[tuple[int, int, str]] = []
    orig_pos = 0
    edit_pos = 0

    for op, a0, a1, b0, b1 in matcher.get_opcodes():
        orig_span = sum(len(t) for t in orig_tokens[a0:a1])
        edit_span = sum(len(t) for t in edit_tokens[b0:b1])

        if op == "equal":
            pass
        elif op == "delete":
            orig_ranges.append((orig_pos, orig_pos + orig_span, "delete_"))
        elif op == "insert":
            edit_ranges.append((edit_pos, edit_pos + edit_span, "insert_"))
        elif op == "replace":
            orig_ranges.append((orig_pos, orig_pos + orig_span, "replace_"))
            edit_ranges.append((edit_pos, edit_pos + edit_span, "replace_"))

        orig_pos += orig_span
        edit_pos += edit_span

    return orig_ranges, edit_ranges

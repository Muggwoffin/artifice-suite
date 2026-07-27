"""Human-in-the-loop review module for approving or rejecting edits.

Provides a CLI-based review interface and data structures for the GUI review.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field

from artifice_draft.llm_client import LLMEdit
from artifice_draft.models import ReviewDecision

logger = logging.getLogger(__name__)


def create_review_items(
    edits: list[LLMEdit], paragraphs: list[dict]
) -> list[dict]:
    """Create review items from LLM edits, pairing originals with suggestions.

    Returns a list of dicts suitable for both CLI and GUI review:
        { paragraph_index, original_text, edited_text, status, approved }
    """
    items: list[dict] = []
    for edit in edits:
        para = next(
            (p for p in paragraphs if p["paragraph_index"] == edit.paragraph_index),
            None,
        )
        if para is None:
            continue

        items.append({
            "paragraph_index": edit.paragraph_index,
            "original_text": para["text"],
            "edited_text": edit.edited_text,
            "status": edit.status,
            "approved": edit.is_changed(),  # auto-approve changes by default
        })

    return items


def apply_decisions(
    edits: list[LLMEdit], decisions: list[ReviewDecision]
) -> dict[int, str | None]:
    """Apply user review decisions to produce a final edits dict.

    Args:
        edits: Original LLM edits.
        decisions: User review decisions.

    Returns a dict mapping paragraph_index → edited text or None.
    """
    decision_map = {d.paragraph_index: d for d in decisions}
    result: dict[int, str | None] = {}

    for edit in edits:
        idx = edit.paragraph_index
        decision = decision_map.get(idx)

        if decision is None:
            result[idx] = edit.edited_text
        elif decision.approved:
            result[idx] = decision.replacement_text or edit.edited_text
        else:
            result[idx] = None

    return result


def cli_review(edit_items: list[dict]) -> list[ReviewDecision]:
    """Interactive CLI review loop.

    Displays each change and asks the user to approve (a), reject (r),
    or edit (e) the replacement text.

    Returns a list of ReviewDecision objects.
    """
    decisions: list[ReviewDecision] = []

    changed_items = [item for item in edit_items if item["edited_text"] and item["edited_text"] != item["original_text"]]

    if not changed_items:
        print("No changes detected — nothing to review.")
        return decisions

    print(f"\n{'='*60}")
    print(f"REVIEW: {len(changed_items)} changes detected")
    print(f"{'='*60}")
    print("Commands: (a)pprove  (r)eject  (e)dit  (q)uit reviewing")
    print(f"{'='*60}\n")

    for i, item in enumerate(changed_items, 1):
        idx = item["paragraph_index"]
        orig = item["original_text"]
        edited = item["edited_text"]

        print(f"--- Change {i}/{len(changed_items)} (paragraph {idx}) ---")
        print(f"  ORIGINAL:  {orig[:120]}{'...' if len(orig) > 120 else ''}")
        print(f"  SUGGESTED: {edited[:120]}{'...' if len(edited) > 120 else ''}")
        print()

        while True:
            choice = input("  [a/r/e/q]: ").strip().lower()
            if choice in ("a", "approve"):
                decisions.append(ReviewDecision(
                    paragraph_index=idx, approved=True,
                ))
                print("  -> Approved\n")
                break
            elif choice in ("r", "reject"):
                decisions.append(ReviewDecision(
                    paragraph_index=idx, approved=False,
                ))
                print("  -> Rejected\n")
                break
            elif choice in ("e", "edit"):
                new_text = input("  Enter replacement text: ").strip()
                decisions.append(ReviewDecision(
                    paragraph_index=idx, approved=True,
                    replacement_text=new_text if new_text else edited,
                ))
                print("  -> Custom text saved\n")
                break
            elif choice in ("q", "quit"):
                print("  Stopping review early.")
                return decisions
            else:
                print("  Unknown command. Use a/r/e/q.")

    approved = sum(1 for d in decisions if d.approved)
    rejected = sum(1 for d in decisions if not d.approved)
    print(f"Review complete: {approved} approved, {rejected} rejected")
    return decisions

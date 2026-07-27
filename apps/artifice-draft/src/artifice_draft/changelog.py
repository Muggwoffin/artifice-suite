"""Generate a summary of changes made during editing."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from artifice_draft.llm_client import LLMEdit

logger = logging.getLogger(__name__)


@dataclass
class ChangeSummary:
    """Aggregate statistics about the editing session."""

    total_paragraphs: int = 0
    paragraphs_edited: int = 0
    paragraphs_unchanged: int = 0
    total_characters_removed: int = 0
    total_characters_added: int = 0
    estimated_words_removed: int = 0
    estimated_words_added: int = 0
    word_count_before: int = 0
    word_count_after: int = 0
    character_count: int = 0
    estimated_pages: float = 0.0
    entries: list[dict] = field(default_factory=list)
    advisories: list[dict] = field(default_factory=list)

    @property
    def edit_rate(self) -> float:
        if self.total_paragraphs == 0:
            return 0.0
        return self.paragraphs_edited / self.total_paragraphs * 100


def classify_change(original: str, edited: str) -> str:
    """Classify the type of change between original and edited text."""
    orig_lower = original.lower()
    edit_lower = edited.lower()

    orig_words = set(re.findall(r"\b\w+\b", orig_lower))
    edit_words = set(re.findall(r"\b\w+\b", edit_lower))

    if len(orig_words) != len(edit_words):
        orig_len = len(original.split())
        edit_len = len(edited.split())
        if abs(orig_len - edit_len) / max(orig_len, 1) > 0.3:
            return "clarity"

    if orig_lower == edit_lower:
        return "spelling"

    added = edit_words - orig_words
    removed = orig_words - edit_words
    if not added and not removed:
        return "style"

    return "grammar"


def generate_change_summary(
    edits: list[LLMEdit],
    paragraphs: list[dict],
    advisories: list[dict] | None = None,
) -> ChangeSummary:
    """Generate a comprehensive summary of all changes made."""
    summary = ChangeSummary(total_paragraphs=len(paragraphs))

    # Word count and character count
    all_original_text = " ".join(p["text"] for p in paragraphs)
    summary.word_count_before = len(all_original_text.split())
    summary.character_count = len(all_original_text)

    para_map = {p["paragraph_index"]: p for p in paragraphs}

    for edit in edits:
        idx = edit.paragraph_index
        para = para_map.get(idx)
        if para is None:
            continue

        if edit.is_changed():
            summary.paragraphs_edited += 1
            orig = para["text"]
            edited = edit.edited_text or ""

            orig_words = len(orig.split())
            edit_words = len(edited.split())
            summary.total_characters_removed += max(0, len(orig) - len(edited))
            summary.total_characters_added += max(0, len(edited) - len(orig))
            summary.estimated_words_removed += max(0, orig_words - edit_words)
            summary.estimated_words_added += max(0, edit_words - orig_words)

            change_type = classify_change(orig, edited)
            summary.entries.append({
                "paragraph_index": idx,
                "original": orig,
                "edited": edited,
                "change_type": change_type,
            })
        else:
            summary.paragraphs_unchanged += 1

    # Compute post-edit word count
    edited_texts = []
    for edit in edits:
        if edit.is_changed() and edit.edited_text:
            edited_texts.append(edit.edited_text)
        else:
            para = para_map.get(edit.paragraph_index)
            if para:
                edited_texts.append(para["text"])
    summary.word_count_after = len(" ".join(edited_texts).split())
    summary.estimated_pages = summary.word_count_after / 250.0

    if advisories:
        summary.advisories = advisories

    logger.info(
        "Change summary: %d/%d paragraphs edited (%.1f%%), ~%d words, ~%.1f pages",
        summary.paragraphs_edited,
        summary.total_paragraphs,
        summary.edit_rate,
        summary.word_count_after,
        summary.estimated_pages,
    )
    return summary


def format_change_log(summary: ChangeSummary) -> str:
    """Format the change summary as a human-readable string."""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("PERSONAEEDIT — CHANGE SUMMARY")
    lines.append("=" * 60)
    lines.append(f"Total paragraphs:    {summary.total_paragraphs}")
    lines.append(f"Paragraphs edited:   {summary.paragraphs_edited}")
    lines.append(f"Paragraphs unchanged: {summary.paragraphs_unchanged}")
    lines.append(f"Edit rate:           {summary.edit_rate:.1f}%")
    lines.append(f"Words removed:       {summary.estimated_words_removed}")
    lines.append(f"Words added:         {summary.estimated_words_added}")
    lines.append(f"Word count:          {summary.word_count_before} → {summary.word_count_after}")
    lines.append(f"Est. pages:          {summary.estimated_pages:.1f}")
    lines.append("")

    if summary.entries:
        lines.append("--- Changes by Type ---")
        type_counts: dict[str, int] = {}
        for e in summary.entries:
            ct = e["change_type"]
            type_counts[ct] = type_counts.get(ct, 0) + 1

        for ct, count in sorted(type_counts.items()):
            lines.append(f"  {ct}: {count}")

        lines.append("")
        lines.append("--- Detailed Changes ---")
        for e in summary.entries:
            orig_preview = e["original"][:80] + ("..." if len(e["original"]) > 80 else "")
            edit_preview = e["edited"][:80] + ("..." if len(e["edited"]) > 80 else "")
            lines.append(f"  [{e['paragraph_index']}] ({e['change_type']})")
            lines.append(f"    - {orig_preview}")
            lines.append(f"    + {edit_preview}")
    else:
        lines.append("No changes were made.")

    if summary.advisories:
        lines.append("")
        lines.append("--- Style Advisories ---")
        severity_counts: dict[str, int] = {}
        for a in summary.advisories:
            sev = a.get("severity", "info")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        for sev, count in sorted(severity_counts.items()):
            lines.append(f"  {sev}: {count}")

        lines.append("")
        for a in summary.advisories:
            lines.append(f"  [{a.get('paragraph_index', '?')}] ({a.get('rule', 'unknown')})")
            lines.append(f"    {a.get('message', '')}")

    lines.append("=" * 60)
    return "\n".join(lines)

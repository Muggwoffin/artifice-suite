"""Apply tracked insertions/deletions to a .docx using docx-revisions.

Uses the document-level API from ``docx_revisions``: each edit is applied via
``RevisionDocument.find_and_replace_tracked``, which produces real
<w:ins>/<w:del> revision elements and persists them when the file is saved.

Each paragraph's edit is applied as a separate call so that different edits
can target different paragraphs independently, while still producing a single
revision document with all changes tracked under one author.
"""

from __future__ import annotations

import logging
import os
import tempfile

from docx_revisions import RevisionDocument

from src.write_utils import write_plain_docx

logger = logging.getLogger(__name__)


def apply_track_changes_to_docx(
    input_path: str | None,
    paragraphs: list[dict],
    changes: dict[int, str],
    output_path: str,
    author: str = "AI Copy Editor",
) -> None:
    """Apply tracked changes to a .docx file using docx-revisions.

    Args:
        input_path: path to the original .docx (loaded for find_and_replace_tracked).
                    If ``None``, reconstructs from paragraph data via a temp file.
        paragraphs: List of paragraph dicts from doc_parser.parse_docx().
        changes: Dict mapping paragraph index to the replacement text.
        output_path: path for the resulting .docx
        author: author name shown in tracked changes (default: "AI Copy Editor").
    """
    if not changes:
        return

    tmp_path = None
    try:
        if input_path:
            logger.debug("Loading original document: %s", input_path)
            rdoc = RevisionDocument(input_path)
        else:
            tmp_path = tempfile.mktemp(suffix=".docx")
            logger.debug("No input_path; writing temp plain docx to %s", tmp_path)
            write_plain_docx(paragraphs, tmp_path)
            rdoc = RevisionDocument(tmp_path)

        for i, entry in enumerate(paragraphs):
            original = entry["text"]
            edited_text = changes.get(i)

            if edited_text is not None:
                logger.debug("Replacing paragraph %d: %r → %r", i, original[:50], edited_text[:50])
                rdoc.find_and_replace_tracked(
                    search_text=original,
                    replace_text=edited_text,
                    author=author,
                )

        rdoc.save(output_path)
        logger.info("Saved tracked-changes document to %s", output_path)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
            logger.debug("Cleaned up temp file: %s", tmp_path)


if __name__ == "__main__":
    print("Track changes module — used internally by doc_writer.py")

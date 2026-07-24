"""Apply LLM edits to a .docx as track changes using docx-revisions.

Also supports exporting to Markdown, HTML, and plain text formats.
Generates a change log summary for the editing session.
"""

from __future__ import annotations

import logging
import os

from src.models import ExportFormat

logger = logging.getLogger(__name__)


def apply_edits_to_docx(
    input_path: str | None,
    paragraphs: list[dict],
    edits: dict[int, str | None],
    output_path: str,
    author: str = "PersonaeEdit",
) -> None:
    """Write a new .docx with tracked insertions/deletions for each edited paragraph.

    Uses ``docx_revisions``'s document-level API so Word shows proper red/blue
    change marks (Track Changes). Falls back to a plain copy if there are no real edits.
    """
    from src._track_changes import apply_track_changes_to_docx
    from src.write_utils import write_plain_docx

    if not edits or all(v is None for v in edits.values()):
        logger.info("No edits to apply; writing plain copy to %s", output_path)
        write_plain_docx(paragraphs, output_path)
        return

    changes: dict[int, str] = {}
    for i, entry in enumerate(paragraphs):
        edited_text = edits.get(i)
        if edited_text is None:
            continue
        if edited_text == entry["text"]:
            continue
        changes[i] = edited_text

    if not changes:
        logger.info("All edits matched original text; writing plain copy to %s", output_path)
        write_plain_docx(paragraphs, output_path)
        return

    logger.info("Applying %d tracked changes to %s", len(changes), output_path)
    apply_track_changes_to_docx(input_path, paragraphs, changes, output_path, author=author)


def apply_edits(
    input_path: str | None,
    paragraphs: list[dict],
    edits: dict[int, str | None],
    output_path: str,
    export_format: ExportFormat = ExportFormat.DOCX_TRACK_CHANGES,
    author: str = "PersonaeEdit",
) -> str:
    """Apply edits and export to the requested format.

    Args:
        input_path: path to the original .docx file (for track changes).
        paragraphs: parsed paragraph data.
        edits: dict mapping paragraph_index → edited text or None.
        output_path: desired output path.
        export_format: target output format.
        author: author name for tracked changes.

    Returns the actual output file path.
    """
    if export_format == ExportFormat.DOCX_TRACK_CHANGES:
        apply_edits_to_docx(input_path, paragraphs, edits, output_path, author=author)
        return output_path

    elif export_format == ExportFormat.DOCX_PLAIN:
        from src.write_utils import write_plain_docx
        write_plain_docx(paragraphs, output_path)
        return output_path

    else:
        from src.exporters import export
        fmt_map = {
            ExportFormat.MARKDOWN: "markdown",
            ExportFormat.HTML: "html",
            ExportFormat.PLAIN_TEXT: "plain_text",
        }
        return export(paragraphs, edits, output_path, fmt_map[export_format])


if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 3:
        print("Usage: python -m src.doc_writer <paragraphs.json> <output.docx>")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        data = json.load(f)

    paragraphs = data["paragraphs"]
    edits = data.get("edits", {})

    apply_edits_to_docx(None, paragraphs, edits, sys.argv[2])
    print(f"Saved to '{sys.argv[2]}'")

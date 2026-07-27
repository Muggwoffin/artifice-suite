"""Apply tracked insertions/deletions to a .docx using docx-revisions.

Uses the document-level API from ``docx_revisions``: each edit is applied via
``RevisionDocument.find_and_replace_tracked``, producing real
<w:ins>/<w:del> revision elements and persisting them when the file is saved.

Each paragraph's edit is applied as a separate call so that different edits
can target different paragraphs independently, while still producing a single
revision document with all changes tracked under one author.

Paragraphs containing inline images (<w:drawing>) are handled by temporarily
removing drawings before the text replacement and re-injecting them into the
resulting <w:ins> element so that images survive the edit.
"""

from __future__ import annotations

import logging
import os
import tempfile

from docx_revisions import RevisionDocument

from artifice_draft.write_utils import write_plain_docx

logger = logging.getLogger(__name__)

NSMAP = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
}


def _paragraph_has_drawing(para_elem) -> bool:
    return len(para_elem.findall(".//w:drawing", NSMAP)) > 0


def _remove_drawings(para_elem):
    """Remove all <w:drawing> elements from a paragraph XML element.

    Returns the list of extracted drawing LXML elements so they can be
    re-injected later.
    """
    drawings = para_elem.findall(".//w:drawing", NSMAP)
    clones = []
    for d in drawings:
        parent = d.getparent()
        if parent is not None:
            clones.append(d)
            parent.remove(d)
    return clones


def _reinject_drawings_into_ins(para_elem, clones) -> None:
    """Re-inject drawing elements into the first <w:ins><w:r> found."""
    if not clones:
        return
    ins_elements = para_elem.findall(".//w:ins", NSMAP)
    for ins in ins_elements:
        runs = ins.findall("w:r", NSMAP)
        if runs:
            target_run = runs[0]
            for clone in clones:
                target_run.append(clone)
            return


def _apply_edit_preserving_images(
    rdoc,
    original: str,
    edited_text: str,
    author: str,
) -> None:
    """Replace text in a paragraph while preserving inline drawings."""
    for para in rdoc._iter_all_paragraphs():
        if para.text.strip() != original:
            continue

        para_elem = para._element
        if not _paragraph_has_drawing(para_elem):
            rdoc.find_and_replace_tracked(
                search_text=original,
                replace_text=edited_text,
                author=author,
            )
            return

        clones = _remove_drawings(para_elem)
        rdoc.find_and_replace_tracked(
            search_text=original,
            replace_text=edited_text,
            author=author,
        )
        _reinject_drawings_into_ins(para_elem, clones)
        return


def apply_track_changes_to_docx(
    input_path: str | None,
    paragraphs: list[dict],
    changes: dict[int, str],
    output_path: str,
    author: str = "ArtificeDraft",
) -> None:
    """Apply tracked changes to a .docx file using docx-revisions.

    Args:
        input_path: path to the original .docx (loaded for find_and_replace_tracked).
                    If ``None``, reconstructs from paragraph data via a temp file.
        paragraphs: List of paragraph dicts from doc_parser.parse_docx().
        changes: Dict mapping paragraph index to the replacement text.
        output_path: path for the resulting .docx
        author: author name shown in tracked changes (default: "ArtificeDraft").
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
                has_imgs = bool(entry.get("images"))
                if has_imgs and input_path:
                    logger.debug(
                        "Applying edit with image preservation on paragraph %d", i
                    )
                    _apply_edit_preserving_images(
                        rdoc, original, edited_text, author,
                    )
                else:
                    logger.debug(
                        "Replacing paragraph %d: %r → %r",
                        i,
                        original[:50],
                        edited_text[:50],
                    )
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

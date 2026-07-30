# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

"""Parse a Word document into paragraphs with rich metadata."""

from __future__ import annotations

import logging
import os
import zipfile

from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from lxml import etree

logger = logging.getLogger(__name__)

NSMAP = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
}


def _extract_images_from_paragraph(paragraph, docx_path: str) -> list[dict]:
    """Extract inline images from a paragraph's XML.

    Returns a list of dicts with keys: rid, content_type, blob, description.
    """
    images: list[dict] = []
    drawing_elements = paragraph._element.findall(".//w:drawing", NSMAP)
    if not drawing_elements:
        return images

    try:
        zf = zipfile.ZipFile(docx_path)
    except Exception:
        return images

    rels_path = "word/_rels/document.xml.rels"
    rels_xml = None
    try:
        rels_xml = zf.read(rels_path)
    except KeyError:
        zf.close()
        return images

    rels_root = etree.fromstring(rels_xml)
    rid_map: dict[str, str] = {}
    for rel in rels_root:
        rid = rel.get("Id")
        target = rel.get("Target")
        if rid and target:
            rid_map[rid] = target

    blip_map: dict[str, str] = {}
    for drawing in drawing_elements:
        blip = drawing.find(".//a:blip", NSMAP)
        if blip is None:
            continue
        embed_rid = blip.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
        if not embed_rid or embed_rid in blip_map:
            continue
        img_path = rid_map.get(embed_rid, "")
        if not img_path:
            continue
        media_path = "word/" + img_path.lstrip("/")
        try:
            blob = zf.read(media_path)
        except KeyError:
            continue
        content_type = ""
        for rel in rels_root:
            if rel.get("Id") == embed_rid:
                content_type = rel.get("Type", "")
                break
        ext = os.path.splitext(img_path)[1] or ".png"
        cid = f"image_{len(images) + 1}{ext}"
        blip_map[embed_rid] = cid
        images.append({
            "rid": embed_rid,
            "content_type": content_type,
            "blob": blob,
            "filename": cid,
        })

    zf.close()
    return images


def parse_docx(path: str) -> list[dict]:
    """Read a .docx file and return a list of paragraph dicts with rich metadata.

    Each dict contains:
        - paragraph_index: position in the document
        - text: the paragraph's full text content
        - style_name: the paragraph style (Heading 1, Normal, etc.)
        - is_bold, is_italic, is_underline: run-level formatting flags
        - indent_level: approximate indent level based on left margin
        - font_size: point size of the first run (or None)
        - font_name: font family of the first run (or None)
        - alignment: paragraph alignment (left, center, right, justify, or None)
        - space_before, space_after: paragraph spacing in points (or None)
        - line_spacing: line spacing multiplier (or None)
        - is_list_item: whether the paragraph is a list item
        - list_level: nesting depth of the list item
        - language: language tag if set on any run, else None
        - images: list of inline image dicts (rid, blob, filename, content_type)

    Raises ValueError if the file cannot be read.
    """
    logger.info("Parsing document: %s", path)
    try:
        doc = Document(path)
    except Exception as exc:
        raise ValueError(f"Could not open document '{path}': {exc}") from exc

    paragraphs = []
    for i, p in enumerate(doc.paragraphs):
        text = (p.text or "").strip()
        if not text:
            continue

        runs = list(p.runs)

        is_bold = any(run.bold for run in runs) or any("Bold" in run.style.name for run in runs)
        is_italic = any(run.italic for run in runs) or any("Italic" in run.style.name for run in runs)
        is_underline = any(run.underline for run in runs)

        left = p.paragraph_format.left_indent or 0
        indent_level = int(left / 72 * 14) if left else 0

        font_size = None
        font_name = None
        if runs:
            first_run = runs[0]
            if first_run.font.size:
                font_size = first_run.font.size.pt
            if first_run.font.name:
                font_name = first_run.font.name

        alignment = None
        if p.paragraph_format.alignment is not None:
            alignment = str(p.paragraph_format.alignment).split(".")[-1].lower()

        space_before = None
        if p.paragraph_format.space_before is not None:
            space_before = p.paragraph_format.space_before.pt

        space_after = None
        if p.paragraph_format.space_after is not None:
            space_after = p.paragraph_format.space_after.pt

        line_spacing = None
        if p.paragraph_format.line_spacing is not None:
            line_spacing = p.paragraph_format.line_spacing

        style_name = p.style.name
        is_list_item = "List" in style_name or style_name.startswith("list")
        list_level = 0
        if is_list_item:
            for lvl in range(1, 10):
                if f"Level {lvl}" in style_name:
                    list_level = lvl
                    break

        language = None
        for run in runs:
            rpr = run._element.find(
                "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}rPr"
            )
            if rpr is not None:
                lang_el = rpr.find(
                    "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}lang"
                )
                if lang_el is not None:
                    language = lang_el.get(
                        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val",
                        None,
                    )
                    if language:
                        break

        images = _extract_images_from_paragraph(p, path)

        paragraphs.append({
            "paragraph_index": i,
            "text": text,
            "style_name": style_name,
            "is_bold": is_bold,
            "is_italic": is_italic,
            "is_underline": is_underline,
            "indent_level": indent_level,
            "font_size": font_size,
            "font_name": font_name,
            "alignment": alignment,
            "space_before": space_before,
            "space_after": space_after,
            "line_spacing": line_spacing,
            "is_list_item": is_list_item,
            "list_level": list_level,
            "language": language,
            "images": images,
        })

    logger.info("Parsed %d paragraphs from '%s'", len(paragraphs), path)
    return paragraphs


def write_docx(paragraphs: list[dict], path: str) -> None:
    """Write a list of paragraph dicts back to a .docx file.

    Preserves the original formatting metadata (bold, italic, style name).
    Does NOT apply track changes — use doc_writer.py for that instead.
    """
    from artifice_draft.write_utils import write_plain_docx

    write_plain_docx(paragraphs, path)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python -m artifice_draft.doc_parser <input.docx> [output.docx]")
        sys.exit(1)

    inp = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else None

    paragraphs = parse_docx(inp)
    print(f"Parsed {len(paragraphs)} paragraphs from '{inp}'")

    if out:
        write_docx(paragraphs, out)
        print(f"Saved plain .docx to '{out}'")

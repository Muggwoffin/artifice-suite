# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

"""Export edited paragraphs to various formats (Markdown, HTML, plain text)."""

from __future__ import annotations

import html
import logging
import os

logger = logging.getLogger(__name__)


def export_markdown(paragraphs: list[dict], edits: dict[int, str | None], path: str) -> None:
    """Write edited paragraphs as a Markdown file."""
    logger.info("Exporting Markdown to %s", path)
    lines: list[str] = []

    for entry in paragraphs:
        idx = entry["paragraph_index"]
        text = edits.get(idx) if edits.get(idx) is not None else entry["text"]
        style = entry.get("style_name", "Normal")

        if style.startswith("Heading 1"):
            lines.append(f"# {text}")
        elif style.startswith("Heading 2"):
            lines.append(f"## {text}")
        elif style.startswith("Heading 3"):
            lines.append(f"### {text}")
        elif entry.get("is_list_item"):
            level = entry.get("list_level", 0)
            indent = "  " * level
            lines.append(f"{indent}- {text}")
        else:
            formatted = text
            if entry.get("is_bold"):
                formatted = f"**{formatted}**"
            if entry.get("is_italic"):
                formatted = f"*{formatted}*"
            lines.append(formatted)

        lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info("Markdown export complete: %d paragraphs", len(paragraphs))


def export_html(paragraphs: list[dict], edits: dict[int, str | None], path: str) -> None:
    """Write edited paragraphs as an HTML file."""
    logger.info("Exporting HTML to %s", path)
    parts: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        "<title>Edited Document</title>",
        "<style>",
        "body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 800px; margin: 0 auto; padding: 2rem; line-height: 1.6; }",
        "h1 { border-bottom: 2px solid #333; padding-bottom: 0.3rem; }",
        "h2 { border-bottom: 1px solid #666; padding-bottom: 0.2rem; }",
        ".bold { font-weight: bold; }",
        ".italic { font-style: italic; }",
        ".underline { text-decoration: underline; }",
        ".list-item { margin-left: 1.5em; }",
        "</style>",
        "</head>",
        "<body>",
    ]

    for entry in paragraphs:
        idx = entry["paragraph_index"]
        text = edits.get(idx) if edits.get(idx) is not None else entry["text"]
        safe_text = html.escape(text)
        style = entry.get("style_name", "Normal")

        if style.startswith("Heading 1"):
            parts.append(f"<h1>{safe_text}</h1>")
        elif style.startswith("Heading 2"):
            parts.append(f"<h2>{safe_text}</h2>")
        elif style.startswith("Heading 3"):
            parts.append(f"<h3>{safe_text}</h3>")
        elif entry.get("is_list_item"):
            level = entry.get("list_level", 0)
            cls = ' class="list-item"' if level > 0 else ""
            parts.append(f"<p{cls}>{safe_text}</p>")
        else:
            cls_parts: list[str] = []
            if entry.get("is_bold"):
                cls_parts.append("bold")
            if entry.get("is_italic"):
                cls_parts.append("italic")
            if entry.get("is_underline"):
                cls_parts.append("underline")
            cls_attr = f' class="{" ".join(cls_parts)}"' if cls_parts else ""
            parts.append(f"<p{cls_attr}>{safe_text}</p>")

    parts.extend(["</body>", "</html>"])

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))

    logger.info("HTML export complete: %d paragraphs", len(paragraphs))


def export_plain_text(paragraphs: list[dict], edits: dict[int, str | None], path: str) -> None:
    """Write edited paragraphs as a plain text file."""
    logger.info("Exporting plain text to %s", path)
    lines: list[str] = []

    for entry in paragraphs:
        idx = entry["paragraph_index"]
        text = edits.get(idx) if edits.get(idx) is not None else entry["text"]
        lines.append(text)
        lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info("Plain text export complete: %d paragraphs", len(paragraphs))


def export(
    paragraphs: list[dict],
    edits: dict[int, str | None],
    output_path: str,
    format_ext: str,
) -> str:
    """Export to the specified format, returning the actual output path.

    Args:
        paragraphs: List of paragraph dicts.
        edits: Dict mapping paragraph index to edited text (or None).
        output_path: Desired output path (extension may be overridden).
        format_ext: One of 'markdown', 'html', 'plain_text', 'docx_plain'.

    Returns the path the file was written to.
    """
    base, _ = os.path.splitext(output_path)

    if format_ext == "markdown" or format_ext == ".md":
        md_path = base + ".md"
        export_markdown(paragraphs, edits, md_path)
        return md_path
    elif format_ext == "html" or format_ext == ".html":
        html_path = base + ".html"
        export_html(paragraphs, edits, html_path)
        return html_path
    elif format_ext == "plain_text" or format_ext == ".txt":
        txt_path = base + ".txt"
        export_plain_text(paragraphs, edits, txt_path)
        return txt_path
    else:
        raise ValueError(f"Unsupported export format: {format_ext}")

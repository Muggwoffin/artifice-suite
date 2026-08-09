# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tropy note round-trip for ArtificeDraft.

Provides library functions to:

1. **Pull** notes from a Tropy JSON-LD export file and return them as
   a list of plain dicts suitable for copy-editing.
2. **Push** edited notes back as a JSON-LD file that can be re-imported
   into Tropy via File → Import Items… (or the local HTTP API).

This is a library module — no FastAPI imports. The routes that call it
live in ``web/server.py``.
"""

import copy
import json
import logging
from html import escape
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

TROPY_CONTEXT = {
    "@version": "1.1",
    "@vocab": "https://tropy.org/v1/tropy#",
    "template": {"@type": "@id"},
    "photo": {"@id": "tropy:photo", "@container": "@list"},
    "note": {"@id": "tropy:note", "@container": "@list"},
    "selection": {"@id": "tropy:selection", "@container": "@list"},
}

TITLE_PROPERTY = "http://purl.org/dc/elements/1.1/title"
MAX_FILE_BYTES = 64 * 1024 * 1024  # 64 MB


class NoteImportError(ValueError):
    """User-facing parse/validation failure."""


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _canonical_json(node: dict) -> bytes:
    return json.dumps(
        node, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _note_html(text: str) -> str:
    """Build HTML note content from plain text."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines:
        paras = "".join(f"<p>{escape(line)}</p>" for line in lines)
    else:
        paras = f"<p>{escape(text.strip())}</p>"
    return paras


def _generator_string() -> str:
    try:
        from importlib.metadata import version
        return f"artifice-draft {version('artifice-draft')}"
    except Exception:
        return "artifice-draft"


# --------------------------------------------------------------------------- #
# pull: extract notes from a Tropy JSON-LD export
# --------------------------------------------------------------------------- #


def extract_notes(path: str | Path) -> list[dict[str, str]]:
    """Extract notes from a Tropy JSON-LD export file.

    Each returned dict has the shape::

        {
            "item_title": "<Tropy item title>",
            "photo_path": "<relative path>",
            "note_text": "<plain text>",
            "note_html": "<HTML>",
        }

    Only photos that actually carry a ``note`` field are returned.
    Photos without notes are skipped silently.
    """
    p = Path(path).expanduser().resolve(strict=False)
    if not p.is_file():
        raise NoteImportError(f"File not found: {p.name}")
    if p.stat().st_size > MAX_FILE_BYTES:
        raise NoteImportError(
            f"File '{p.name}' is too large ({p.stat().st_size} bytes; max {MAX_FILE_BYTES})"
        )

    try:
        data = json.loads(p.read_bytes())
    except (json.JSONDecodeError, OSError) as exc:
        raise NoteImportError(f"Cannot parse JSON-LD: {exc}") from exc

    graph: list[dict] = []
    if isinstance(data, dict):
        graph = _as_list(data.get("@graph", [data]))
    elif isinstance(data, list):
        graph = data
    else:
        raise NoteImportError("JSON-LD root must be an object or array")

    notes: list[dict[str, str]] = []

    for node in graph:
        if not isinstance(node, dict):
            continue
        ntype = _as_list(node.get("@type", []))
        is_item = "Item" in ntype or any(
            isinstance(t, str) and t.endswith("#Item") for t in ntype
        )
        if not is_item:
            continue

        # Extract title
        title = None
        for key in (
            TITLE_PROPERTY,
            "title",
            "dc:title",
            "http://purl.org/dc/terms/title",
        ):
            if key in node:
                val = node[key]
                if isinstance(val, list):
                    val = val[0] if val else None
                if isinstance(val, dict) and "@value" in val:
                    val = val["@value"]
                if isinstance(val, str) and val.strip():
                    title = val.strip()
                    break
        if title is None:
            title = "Untitled item"

        raw_photos = node.get("photo", [])
        if isinstance(raw_photos, dict):
            raw_photos = [raw_photos]
        elif not isinstance(raw_photos, list):
            raw_photos = []

        for pnode in raw_photos:
            if not isinstance(pnode, dict):
                continue
            raw_notes = pnode.get("note", [])
            if isinstance(raw_notes, dict):
                raw_notes = [raw_notes]
            elif not isinstance(raw_notes, list):
                continue

            for note_node in raw_notes:
                if not isinstance(note_node, dict):
                    continue
                note_text = note_node.get("text", "")
                note_html = note_node.get("html", "")
                if not note_text and not note_html:
                    continue
                if not note_text:
                    note_text = ""
                if not note_html:
                    note_html = _note_html(note_text)

                notes.append(
                    {
                        "item_title": title,
                        "photo_path": pnode.get("path", ""),
                        "note_text": str(note_text),
                        "note_html": str(note_html),
                    }
                )

    log.info("Extracted %d notes from Tropy export", len(notes))
    return notes


# --------------------------------------------------------------------------- #
# push: build a JSON-LD file with edited notes
# --------------------------------------------------------------------------- #


def build_note_export(
    original_path: str | Path,
    edited_notes: list[dict[str, Any]],
) -> str:
    """Build a Tropy JSON-LD export with edited notes.

    Parameters
    ----------
    original_path : str or Path
        Path to the original Tropy JSON-LD export file.  Item envelopes
        are deep-copied from this file so the round-trip preserves all
        fields Tropy sent.
    edited_notes : list[dict]
        Notes to write back. Each dict should have::

            {
                "item_title": "<str>",
                "photo_path": "<str>",
                "note_text": "<plain text>",
                "note_html": "<HTML>",
            }

    Returns
    -------
    str
        The JSON-LD content as a formatted string, ready to write to
        disk or POST to Tropy's import API.
    """
    p = Path(original_path).expanduser().resolve(strict=False)
    if not p.is_file():
        raise NoteImportError(f"Original export not found: {p.name}")

    try:
        data = json.loads(p.read_bytes())
    except (json.JSONDecodeError, OSError) as exc:
        raise NoteImportError(f"Cannot parse original export: {exc}") from exc

    graph: list[dict] = []
    if isinstance(data, dict):
        graph = _as_list(data.get("@graph", [data]))
    elif isinstance(data, list):
        graph = data

    # Build a lookup by (item_title, photo_path)
    lookup: dict[tuple[str, str], dict[str, str]] = {}
    for en in edited_notes:
        key = (en.get("item_title", ""), en.get("photo_path", ""))
        lookup[key] = en

    output_graph: list[dict] = []

    for node in graph:
        if not isinstance(node, dict):
            continue
        ntype = _as_list(node.get("@type", []))
        is_item = "Item" in ntype or any(
            isinstance(t, str) and t.endswith("#Item") for t in ntype
        )
        if not is_item:
            output_graph.append(node)  # preserve non-item nodes
            continue

        item = copy.deepcopy(node)

        # Extract title
        title = None
        for key in (
            TITLE_PROPERTY,
            "title",
            "dc:title",
            "http://purl.org/dc/terms/title",
        ):
            if key in item:
                val = item[key]
                if isinstance(val, list):
                    val = val[0] if val else None
                if isinstance(val, dict) and "@value" in val:
                    val = val["@value"]
                if isinstance(val, str) and val.strip():
                    title = val.strip()
                    break
        if title is None:
            title = "Untitled item"

        raw_photos = item.get("photo", [])
        if isinstance(raw_photos, dict):
            raw_photos = [raw_photos]
        elif not isinstance(raw_photos, list):
            output_graph.append(item)
            continue

        updated_photos: list[dict] = []
        for pnode in raw_photos:
            if not isinstance(pnode, dict):
                updated_photos.append(pnode)
                continue
            photo_path = pnode.get("path", "")
            edit_key = (title, photo_path)
            edited = lookup.get(edit_key)

            if edited is None:
                # No edit for this photo — keep as-is (including its
                # original notes)
                updated_photos.append(pnode)
                continue

            # Replace notes with the edited ones
            photo = copy.deepcopy(pnode)
            note_text = edited.get("note_text", "")
            note_html = edited.get("note_html", "") or _note_html(note_text)
            photo["note"] = [
                {
                    "@type": "Note",
                    "text": note_text,
                    "html": note_html,
                }
            ]
            updated_photos.append(photo)

        item["photo"] = updated_photos
        output_graph.append(item)

    result = {
        "@context": TROPY_CONTEXT,
        "@graph": output_graph,
        "generator": _generator_string(),
    }
    return json.dumps(result, indent=2, ensure_ascii=False)

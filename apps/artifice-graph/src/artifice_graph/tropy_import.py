# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tropy manifest consumption for ArtificeGraph.

Reads a ``tropy_manifest.json`` file (as written by artifice-ocr's
:func:`~artifice_ocr.tropy_jsonld.write_manifest`) and creates graph
nodes carrying provenance metadata.

This is a library module — no FastAPI imports. The route that calls it
lives in ``web/server.py``.
"""

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

MANIFEST_SCHEMA_VERSION = "1.0"


class ManifestError(ValueError):
    """A manifest is structurally valid JSON but does not conform to the
    documented contract.  The message is suitable for returning to the user."""


def load_manifest(path: str | Path) -> dict[str, Any]:
    """Read and validate a tropy_manifest.json file.

    Returns the parsed manifest dict. Raises :class:`ManifestError` if the
    schema version is unrecognised or the structure is invalid.
    """
    p = Path(path).expanduser().resolve(strict=False)
    if not p.is_file():
        raise ManifestError(f"Manifest not found: {p}")

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ManifestError(f"Cannot parse manifest: {exc}") from exc

    if not isinstance(data, dict):
        raise ManifestError("Manifest root must be a JSON object")

    version = data.get("schema_version")
    if version != MANIFEST_SCHEMA_VERSION:
        raise ManifestError(
            f"Unsupported manifest schema version {version!r} "
            f"(expected {MANIFEST_SCHEMA_VERSION!r})"
        )

    pages = data.get("pages")
    if not isinstance(pages, dict):
        raise ManifestError("Manifest is missing 'pages' key or is not a dict")

    return data


def manifest_to_graph_nodes(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert a validated manifest into a list of graph-node dicts.

    Each node represents one page and carries a ``provenance`` dict with
    the fields that trace back to the original Tropy item and photo::

        {
            "id": "<output_stem>",
            "label": "<item_title>/<filename>",
            "type": "ocr_page",
            "provenance": {
                "source": "tropy-manifest",
                "schema_version": "1.0",
                "item_title": "<Tropy item title>",
                "tropy_group": "<hash:idx>",
                "source_path": "<absolute path>",
                "orientation": 1,
                "checksum": "<hex>",
            },
        }
    """
    pages = manifest.get("pages", {})
    nodes: list[dict[str, Any]] = []

    for stem, info in pages.items():
        if not isinstance(info, dict):
            continue
        item_title = info.get("item_title", stem)
        tropy_group = info.get("tropy_group") or ""
        source_path = info.get("source_path") or ""
        orientation = info.get("orientation", 1)
        checksum = info.get("checksum") or ""
        filename = info.get("filename") or Path(source_path).name

        has_provenance = bool(tropy_group or source_path)
        if not has_provenance:
            # Pages without Tropy provenance are still valid — they
            # represent ad-hoc imports that don't trace back to Tropy.
            nodes.append(
                {
                    "id": stem,
                    "label": f"{item_title}/{filename}",
                    "type": "ocr_page",
                    "provenance": None,
                }
            )
            continue

        nodes.append(
            {
                "id": stem,
                "label": f"{item_title}/{filename}",
                "type": "ocr_page",
                "provenance": {
                    "source": "tropy-manifest",
                    "schema_version": manifest.get("schema_version", "1.0"),
                    "item_title": item_title,
                    "tropy_group": tropy_group,
                    "source_path": source_path,
                    "orientation": orientation,
                    "checksum": checksum,
                },
            }
        )

    log.info(
        "Built %d graph nodes from manifest (%d with provenance)",
        len(nodes),
        sum(1 for n in nodes if n.get("provenance")),
    )
    return nodes

"""Serialization helpers — shared across SSE events, REST responses, and preview.

Extracted from runtime.py so that both the routes (server/routers) and the
state module (runtime) can use them without circular imports.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any

from .._diff import confidence_tier, diff_ranges, marker_ranges
from ..jobs import JobItem


def _item_key(item: JobItem) -> str:
    return str(id(item))


def serialize_item(item: JobItem) -> dict[str, Any]:
    return {
        "id": _item_key(item),
        "name": item.name,
        "path": item.path,
        "state": item.state.value,
        "confidence": item.confidence,
        "language": item.language,
        "error": item.error,
        "elapsed": round(item.elapsed, 1),
        "guard_rejected": item.guard_rejected,
        "stages": {
            name: {
                "state": status.state.value,
                "chars": status.chars,
                "elapsed": round(status.elapsed, 1),
                "error": status.error,
            }
            for name, status in item.stages.items()
        },
    }


def serialize_event(event) -> dict[str, Any]:
    return {
        "kind": event.kind,
        "stage": event.stage,
        "message": event.message,
        "tag": event.tag,
        "payload": event.payload,
        "item": serialize_item(event.item) if event.item is not None else None,
        "timestamp": event.timestamp,
    }


def _diff_payload(raw: str, cleaned: str, translated: str) -> dict[str, Any]:
    raw_ranges, clean_ranges = ([], [])
    if raw and cleaned:
        raw_ranges, clean_ranges = diff_ranges(raw, cleaned)
    return {
        "raw_ranges": raw_ranges,
        "cleaned_ranges": clean_ranges + (marker_ranges(cleaned) if cleaned else []),
        "translated_ranges": marker_ranges(translated) if translated else [],
    }


def serialize_item_preview(item: JobItem) -> dict[str, Any]:
    results = item.results or {}
    raw = (results.get("raw") or {}).get("extracted_text", "") or ""
    cleaned = (results.get("cleaned") or {}).get("cleaned_text", "") or ""
    translated = (results.get("translated") or {}).get("translated_text", "") or ""

    return {
        "id": _item_key(item),
        "title": item.name,
        "path": item.path,
        "raw": raw,
        "original_raw": (results.get("raw") or {}).get("original_extracted_text", "") or "",
        "cleaned": cleaned,
        "original_cleaned": (results.get("cleaned") or {}).get("original_cleaned_text", "") or "",
        "translated": translated,
        "original_translated": (results.get("translated") or {}).get("original_translated_text", "") or "",
        "confidence": item.confidence,
        "confidence_tier": confidence_tier(item.confidence),
        "language": item.language,
        "diff": _diff_payload(raw, cleaned, translated),
    }


def serialize_history_run(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "run_id": row["run_id"],
        "started": row["started"],
        "finished": row["finished"],
        "stages": row["stages"],
        "output_dir": row["output_dir"],
        "total": row["total"],
        "succeeded": row["succeeded"],
        "failed": row["failed"],
        "elapsed": row["elapsed"],
    }


def serialize_history_item(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "item_id": row["item_id"],
        "name": row["name"],
        "state": row["state"],
        "language": row["language"],
        "confidence": row["confidence"],
    }


def serialize_history_item_detail(row: sqlite3.Row) -> dict[str, Any]:
    raw = row["raw_text"] or ""
    cleaned = row["cleaned_text"] or ""
    translated = row["translated_text"] or ""
    return {
        "item_id": row["item_id"],
        "name": row["name"],
        "source_file": row["source_file"],
        "page": row["page"],
        "state": row["state"],
        "language": row["language"],
        "confidence": row["confidence"],
        "confidence_tier": confidence_tier(row["confidence"]),
        "error": row["error"],
        "raw": raw,
        "original_raw": row["original_raw_text"] or "",
        "cleaned": cleaned,
        "original_cleaned": row["original_cleaned_text"] or "",
        "translated": translated,
        "original_translated": row["original_translated_text"] or "",
        "diff": _diff_payload(raw, cleaned, translated),
    }

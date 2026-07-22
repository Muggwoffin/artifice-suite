"""Server-side state for the web frontend.

This plays the same role `gui/app.py` plays for the tkinter build: it owns the
queue of :class:`~ocr_pipeline.jobs.JobItem` objects and the current
:class:`~ocr_pipeline.jobs.JobRunner`, and turns runner events into something a
client can consume. Nothing in `jobs.py` changed to make this possible — the
runner already published progress on a plain `queue.Queue` with no tkinter
import, specifically so a second frontend could drain it differently.

Items are addressed by `id(item)` the same way `gui/widgets/queue_table.py`
addresses treeview rows — a stable string key that survives across SSE
messages without the client needing to understand JobItem internals.
"""

import json
import queue
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .. import config
from .._diff import confidence_tier, diff_ranges, marker_ranges
from ..history import HistoryStore
from ..jobs import STAGES, JobItem, JobRunner, State

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".pdf"}

# Higher than OCR's own 200 dpi — this pane exists specifically so a user can
# zoom in past what machine OCR needs, to check an individual word by eye.
IMAGE_DPI = 300
IMAGE_MAX_LONG_EDGE = 3000


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
    }


def _diff_payload(raw: str, cleaned: str, translated: str) -> dict[str, Any]:
    """Same highlight ranges `compare_view.py` computes, as JSON.

    Kept server-side rather than reimplemented in JS so the two frontends
    can never quietly disagree about what counts as a changed word.
    """
    raw_ranges, clean_ranges = ([], [])
    if raw and cleaned:
        raw_ranges, clean_ranges = diff_ranges(raw, cleaned)
    return {
        "raw_ranges": raw_ranges,
        "cleaned_ranges": clean_ranges + (marker_ranges(cleaned) if cleaned else []),
        "translated_ranges": marker_ranges(translated) if translated else [],
    }


def serialize_item_preview(item: JobItem) -> dict[str, Any]:
    """Full text + diff/marker ranges for the Preview tab, in-memory only.

    Nothing here touches disk — it reads whatever `item.results` the runner
    already holds, exactly like `App.preview_item` does for the tk build.
    """
    results = item.results or {}
    raw = (results.get("raw") or {}).get("extracted_text", "") or ""
    cleaned = (results.get("cleaned") or {}).get("cleaned_text", "") or ""
    translated = (results.get("translated") or {}).get("translated_text", "") or ""

    return {
        "id": _item_key(item),
        "title": item.name,
        "path": item.path,
        "raw": raw,
        "cleaned": cleaned,
        "translated": translated,
        "confidence": item.confidence,
        "confidence_tier": confidence_tier(item.confidence),
        "language": item.language,
        "diff": _diff_payload(raw, cleaned, translated),
    }


def render_page_image(item: JobItem) -> bytes:
    """PNG bytes for a TIFF source, or the single PDF page `item.page` points
    at — never the whole document (a 275-page Tropy item would make that a
    real waste, exactly what `_pdf_single_page_image`'s docstring warns
    against). JPEG/PNG need no conversion — browsers render them natively —
    and are served directly by the route instead of coming through here.

    PDF render DPI is capped by long edge rather than left uncapped, so an
    oversized scan doesn't produce an unreasonably large PNG; TIFF is
    converted at its native resolution, same as the jpg/png passthrough
    case leaves those files at whatever resolution they already are.
    """
    import fitz  # PyMuPDF

    path = Path(item.path)
    suffix = path.suffix.lower()

    if suffix in (".tif", ".tiff"):
        return fitz.Pixmap(str(path)).tobytes("png")

    if suffix == ".pdf":
        doc = fitz.open(str(path))
        try:
            page = doc[item.page or 0]
            dpi = IMAGE_DPI
            long_edge_pt = max(page.rect.width, page.rect.height)
            long_edge_px = long_edge_pt / 72 * dpi
            if long_edge_px > IMAGE_MAX_LONG_EDGE:
                dpi = dpi * IMAGE_MAX_LONG_EDGE / long_edge_px
            return page.get_pixmap(dpi=max(int(dpi), 1)).tobytes("png")
        finally:
            doc.close()

    raise ValueError(f"No image renderer for {suffix} files")


def save_raw_text(item: JobItem, text: str) -> dict[str, Any]:
    """Persist a manual correction to an item's raw OCR text.

    Always updates the in-memory copy first — that's what a later
    cleanup/translate run or a Tropy write-back reads from (`jobs.py`'s
    `_phase_cleanup` reads `item.results["raw"]`). Also overwrites the
    on-disk `raw_ocr/text/<stem>.txt` and `raw_ocr/json/<stem>.json` *if a
    prior OCR run already produced them* for this stem; an item only added
    to the queue but never run has nothing on disk yet, which isn't an
    error, just nothing to persist beyond memory yet.

    Only `extracted_text` (+ new `edited`/`edited_at`) changes in the JSON —
    `engine`/`model`/`ocr_prompt`/`timestamp` keep recording what the
    *original* OCR pass actually did. Rewriting those to look like the model
    produced the corrected text would be dishonest provenance, the same
    principle `_guard.py` argues for automated corrections.
    """
    item.results.setdefault("raw", {})["extracted_text"] = text

    output_dir = state.runner.output_dir if state.runner else config.get("output_dir")
    text_path = Path(output_dir) / "raw_ocr" / "text" / f"{item.stem}.txt"
    if text_path.exists():
        text_path.write_text(text, encoding="utf-8")

        json_path = Path(output_dir) / "raw_ocr" / "json" / f"{item.stem}.json"
        if json_path.exists():
            data = json.loads(json_path.read_text(encoding="utf-8"))
            data["extracted_text"] = text
            data["edited"] = True
            data["edited_at"] = datetime.now(timezone.utc).isoformat()
            json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    return serialize_item_preview(item)


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
        "state": row["state"],
        "language": row["language"],
        "confidence": row["confidence"],
        "confidence_tier": confidence_tier(row["confidence"]),
        "error": row["error"],
        "raw": raw,
        "cleaned": cleaned,
        "translated": translated,
        "diff": _diff_payload(raw, cleaned, translated),
    }


class RunState:
    """Everything about the batch currently queued or in flight.

    One instance per server process. A real multi-user deployment would key
    this per session; a local tool run by one person on their own machine
    does not need that complexity.
    """

    def __init__(self):
        config.load_config()
        config.apply_overrides(config.load_user_settings())

        self.items: list[JobItem] = []
        self._by_id: dict[str, JobItem] = {}
        self.runner: JobRunner | None = None
        self.run_id: int | None = None
        self._history: HistoryStore | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------- history
    @property
    def history(self) -> HistoryStore:
        if self._history is None:
            self._history = HistoryStore(config.get("history_db"))
        return self._history

    # ----------------------------------------------------------------- queue
    def add_paths(self, paths: list[str]) -> list[JobItem]:
        """Resolve files and folders into queue items, skipping duplicates.

        Mirrors `QueueTable.add_paths`: identity is (path, stem) rather than
        just path, because a Tropy page shares its path with every other page
        of the same PDF.
        """
        resolved: list[str] = []
        for raw in paths:
            p = Path(raw)
            if p.is_dir():
                resolved.extend(
                    str(f) for f in sorted(p.rglob("*"))
                    if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
                )
            elif p.suffix.lower() in SUPPORTED_EXTENSIONS:
                resolved.append(str(p))

        known = {(i.path, i.stem) for i in self.items}
        added: list[JobItem] = []
        with self._lock:
            for path in resolved:
                item = JobItem(path=path)
                if (item.path, item.stem) in known:
                    continue
                known.add((item.path, item.stem))
                self.items.append(item)
                self._by_id[_item_key(item)] = item
                added.append(item)
        return added

    def add_items(self, items: list[JobItem]) -> list[JobItem]:
        """Add pre-built items (e.g. from a Tropy selection)."""
        known = {(i.path, i.stem) for i in self.items}
        added: list[JobItem] = []
        with self._lock:
            for item in items:
                if (item.path, item.stem) in known:
                    continue
                known.add((item.path, item.stem))
                self.items.append(item)
                self._by_id[_item_key(item)] = item
                added.append(item)
        return added

    def remove(self, ids: list[str]) -> int:
        with self._lock:
            targets = [self._by_id[i] for i in ids if i in self._by_id]
            for item in targets:
                self.items.remove(item)
                del self._by_id[_item_key(item)]
            return len(targets)

    def clear(self) -> None:
        with self._lock:
            self.items.clear()
            self._by_id.clear()

    def get(self, item_id: str) -> JobItem | None:
        return self._by_id.get(item_id)

    def queue_snapshot(self) -> list[dict]:
        return [serialize_item(i) for i in self.items]

    def tropy_eligible_items(self, item_ids: list[str] | None) -> list[JobItem]:
        """Queue items that came from Tropy (carry a photo_id), for send-back.

        `item_ids=None` means "everything eligible currently in the queue" —
        the same default the desktop dialog uses when nothing is selected.
        """
        pool = (
            [self.get(i) for i in item_ids] if item_ids is not None
            else list(self.items)
        )
        return [i for i in pool if i is not None and (i.source or {}).get("photo_id")]

    # --------------------------------------------------------------- running
    def start_run(self, *, stages: set[str], output_dir: str,
                 force: bool) -> queue.Queue:
        if self.runner is not None and self.runner.is_running:
            raise RuntimeError("A run is already in progress")
        if not self.items:
            raise ValueError("Queue is empty")
        if not stages:
            raise ValueError("No stages selected")

        config.apply_overrides({"output_dir": output_dir})
        config.save_user_settings({"output_dir": output_dir})

        self.run_id = self.history.start_run(
            stages=[s for s in STAGES if s in stages],
            output_dir=output_dir, total=len(self.items),
        )

        events: queue.Queue = queue.Queue()
        self.runner = JobRunner(self.items, output_dir, stages=stages,
                                force=force, events=events)
        self.runner.start()
        return events

    def record_finished_items(self) -> None:
        """Persist finished items to history. Called as run_finished arrives."""
        if self.run_id is None:
            return
        for item in self.items:
            if item.state in (State.DONE, State.FAILED):
                try:
                    self.history.record_item(self.run_id, item)
                except Exception:
                    pass  # history must never break a run

    def finish_run(self, payload: dict) -> None:
        if self.run_id is not None:
            self.history.finish_run(
                self.run_id,
                succeeded=payload.get("done", 0),
                failed=payload.get("failed", 0),
                elapsed=payload.get("elapsed", 0.0),
            )
        self.run_id = None

    def pause(self) -> None:
        if self.runner:
            self.runner.pause()

    def resume(self) -> None:
        if self.runner:
            self.runner.unpause()

    def cancel(self) -> None:
        if self.runner:
            self.runner.cancel()

    def skip(self, item_id: str) -> bool:
        item = self.get(item_id)
        if item is None or self.runner is None:
            return False
        self.runner.skip(item)
        return True

    def status(self) -> dict:
        return {
            "running": bool(self.runner and self.runner.is_running),
            "paused": bool(self.runner and self.runner.is_paused),
            "total": len(self.items),
        }


# One instance for the process. A web app with multiple simultaneous users
# would need this scoped per-session; this tool is run by one person on their
# own machine, so a module-level singleton is the honest amount of state.
state = RunState()

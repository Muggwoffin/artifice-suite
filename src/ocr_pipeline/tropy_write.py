"""Write OCR results back into a Tropy project.

Deliberately separate from :mod:`tropy`, which stays provably read-only: the
read path never imports this module, so browsing an archive cannot modify it.

Everything here is built around not damaging an irreplaceable research
archive:

* Tropy must be closed. Writing underneath a running Tropy means its in-memory
  state diverges from the database and can overwrite what we just wrote.
* A timestamped copy of ``project.tpy`` is taken before the first write.
* :meth:`TropyWriter.preview` reports exactly what would change, and nothing is
  written until :meth:`TropyWriter.write` is called explicitly.
* Re-running is safe: an entry whose text already exists for that photo is
  reported as a duplicate and skipped rather than added twice.

Two targets are supported:

``notes``
    One note per photo, exactly as Tropy's own note editor would store it —
    plain text plus a ProseMirror document in ``state``. Visible in the normal
    note pane, easy to read and easy to delete.

``transcriptions``
    Rows in Tropy's native (here unused) ``transcriptions`` table, which its
    transcription UI reads. Marked with ``config.generator = "ocr_pipeline"``
    so ours are always identifiable.

Both tables carry AFTER INSERT triggers that maintain the full-text search
index, so inserts alone keep search working.
"""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

from ._logging import get_logger
from .tropy import _resolve_project_paths

log = get_logger("tropy_write")

TARGET_NOTES = "notes"
TARGET_TRANSCRIPTIONS = "transcriptions"
VALID_TARGETS = (TARGET_NOTES, TARGET_TRANSCRIPTIONS)

GENERATOR = "ocr_pipeline"


@dataclass
class WriteEntry:
    """One page of text destined for one Tropy photo."""

    photo_id: int
    text: str
    label: str = ""
    language: str = "de"
    stage: str = "raw_ocr"

    def clean_language(self) -> str:
        # notes.language has CHECK (language = trim(lower(language)) AND != '')
        lang = (self.language or "en").strip().lower()
        return lang or "en"


@dataclass
class EntryPlan:
    entry: WriteEntry
    target: str
    action: str  # "insert" | "duplicate" | "missing-photo" | "empty"
    reason: str = ""


@dataclass
class Preview:
    plans: list[EntryPlan] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    @property
    def insertable(self) -> list[EntryPlan]:
        return [p for p in self.plans if p.action == "insert"]

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for plan in self.plans:
            key = f"{plan.target}:{plan.action}"
            out[key] = out.get(key, 0) + 1
        return out

    def summary(self) -> str:
        if self.blockers:
            return "cannot write: " + "; ".join(self.blockers)
        counts = self.counts()
        if not counts:
            return "nothing to write"
        return "  ".join(f"{k} = {v}" for k, v in sorted(counts.items()))


@dataclass
class WriteReport:
    written: int = 0
    skipped: int = 0
    backup: Path | None = None
    errors: list[str] = field(default_factory=list)


def _tropy_is_running() -> bool:
    """Best-effort check for a live Tropy process."""
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq Tropy.exe", "/NH"],
                capture_output=True, text=True, timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return "Tropy.exe" in result.stdout
        result = subprocess.run(["pgrep", "-i", "tropy"],
                                capture_output=True, text=True, timeout=15)
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False  # can't tell; the lock check below is the backstop


def _prosemirror_state(text: str) -> str:
    """Build the ProseMirror document Tropy stores alongside a note's text.

    Matches the shape of existing notes in the project: a doc of left-aligned
    paragraphs, one per line, with empty lines dropped (ProseMirror rejects a
    text node with an empty string).
    """
    paragraphs = []
    for line in text.splitlines():
        node: dict = {"type": "paragraph", "attrs": {"align": "left"}}
        if line.strip():
            node["content"] = [{"type": "text", "text": line}]
        paragraphs.append(node)
    if not paragraphs:
        paragraphs = [{"type": "paragraph", "attrs": {"align": "left"},
                       "content": [{"type": "text", "text": text}]}]
    return json.dumps({"doc": {"type": "doc", "content": paragraphs}},
                      ensure_ascii=False)


class TropyWriter:
    """Read-write handle on a Tropy project. Opens lazily and safely."""

    def __init__(self, project_path: str | Path):
        self.bundle_dir, self.db_path = _resolve_project_paths(project_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"No Tropy database at {self.db_path}")
        self._con: sqlite3.Connection | None = None

    # ------------------------------------------------------------- lifecycle
    def _connect(self, write: bool = False) -> sqlite3.Connection:
        if self._con is None:
            uri = f"file:{self.db_path.as_posix()}" + ("" if write else "?mode=ro")
            self._con = sqlite3.connect(uri, uri=True, isolation_level=None)
            self._con.row_factory = sqlite3.Row
        return self._con

    def close(self) -> None:
        if self._con is not None:
            self._con.close()
            self._con = None

    def __enter__(self) -> "TropyWriter":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -------------------------------------------------------------- preflight
    def blockers(self) -> list[str]:
        """Reasons a write must not proceed right now."""
        problems: list[str] = []

        if _tropy_is_running():
            problems.append(
                "Tropy is running — close it before writing, or it will "
                "overwrite these changes from its in-memory state")

        if not os.access(self.db_path, os.W_OK):
            problems.append(f"{self.db_path} is not writable")

        # A held write lock means something else is mid-transaction.
        try:
            probe = sqlite3.connect(str(self.db_path), timeout=1.0,
                                    isolation_level=None)
            try:
                probe.execute("BEGIN IMMEDIATE")
                probe.execute("ROLLBACK")
            finally:
                probe.close()
        except sqlite3.OperationalError as exc:
            problems.append(f"database is locked by another process ({exc})")

        return problems

    def backup(self) -> Path:
        """Timestamped copy of the database (and its WAL sidecars)."""
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = self.db_path.with_name(f"{self.db_path.stem}.{stamp}.backup.tpy")
        shutil.copy2(self.db_path, target)
        for suffix in ("-wal", "-shm"):
            side = Path(str(self.db_path) + suffix)
            if side.exists():
                shutil.copy2(side, Path(str(target) + suffix))
        log.info("Backed up Tropy database to %s", target)
        return target

    # --------------------------------------------------------------- preview
    def preview(self, entries: Iterable[WriteEntry],
                targets: Iterable[str]) -> Preview:
        """Work out what would be written, without writing anything."""
        targets = [t for t in targets if t in VALID_TARGETS]
        result = Preview(blockers=self.blockers())
        if not targets:
            result.blockers.append("no write target selected")
            return result

        con = self._connect(write=False)
        known_photos = {r["id"] for r in con.execute("SELECT id FROM photos")}

        for entry in entries:
            text = (entry.text or "").strip()
            for target in targets:
                if not text:
                    result.plans.append(EntryPlan(
                        entry, target, "empty", "no text for this page"))
                    continue
                if entry.photo_id not in known_photos:
                    result.plans.append(EntryPlan(
                        entry, target, "missing-photo",
                        f"photo {entry.photo_id} is not in this project"))
                    continue
                if self._already_present(con, target, entry.photo_id, text):
                    result.plans.append(EntryPlan(
                        entry, target, "duplicate",
                        "identical text already attached to this photo"))
                    continue
                result.plans.append(EntryPlan(entry, target, "insert"))

        return result

    def _already_present(self, con: sqlite3.Connection, target: str,
                         photo_id: int, text: str) -> bool:
        table = "notes" if target == TARGET_NOTES else "transcriptions"
        row = con.execute(
            f"SELECT 1 FROM {table} WHERE id = ? AND text = ? "
            f"AND deleted IS NULL LIMIT 1",
            (photo_id, text),
        ).fetchone()
        return row is not None

    # ----------------------------------------------------------------- write
    def write(self, preview: Preview, *, make_backup: bool = True) -> WriteReport:
        """Apply an approved preview. Refuses to run if there are blockers."""
        report = WriteReport()
        if preview.blockers:
            report.errors.extend(preview.blockers)
            return report

        plans = preview.insertable
        report.skipped = len(preview.plans) - len(plans)
        if not plans:
            return report

        if make_backup:
            report.backup = self.backup()

        self.close()  # reopen read-write
        con = self._connect(write=True)

        try:
            con.execute("BEGIN IMMEDIATE")
            for plan in plans:
                entry = plan.entry
                text = entry.text.strip()
                if plan.target == TARGET_NOTES:
                    con.execute(
                        "INSERT INTO notes (id, text, state, language) "
                        "VALUES (?, ?, ?, ?)",
                        (entry.photo_id, text, _prosemirror_state(text),
                         entry.clean_language()),
                    )
                else:
                    config = json.dumps({
                        "generator": GENERATOR,
                        "stage": entry.stage,
                        "created": datetime.now().isoformat(timespec="seconds"),
                    }, ensure_ascii=False)
                    con.execute(
                        "INSERT INTO transcriptions (id, text, config, data, status) "
                        "VALUES (?, ?, ?, ?, 0)",
                        (entry.photo_id, text, config, None),
                    )
                report.written += 1
            con.execute("COMMIT")
            log.info("Wrote %d row(s) into %s", report.written, self.db_path)
        except Exception as exc:
            con.execute("ROLLBACK")
            report.errors.append(f"{type(exc).__name__}: {exc}")
            report.written = 0
            log.error("Tropy write rolled back: %s", exc)

        return report


def entries_from_items(items, *, stage: str = "cleaned") -> list[WriteEntry]:
    """Build write entries from finished :class:`jobs.JobItem` objects.

    Only items that came from Tropy carry a `photo_id`, so anything else is
    ignored. `stage` picks which text to send: "raw_ocr", "cleaned" or
    "translated", falling back to whatever the item actually produced.
    """
    key_map = {
        "raw_ocr": ("raw", "extracted_text"),
        "cleaned": ("cleaned", "cleaned_text"),
        "translated": ("translated", "translated_text"),
    }
    order = [stage] + [s for s in ("cleaned", "raw_ocr", "translated") if s != stage]

    entries: list[WriteEntry] = []
    for item in items:
        photo_id = (item.source or {}).get("photo_id")
        if photo_id is None:
            continue
        for candidate in order:
            bucket, field_name = key_map[candidate]
            text = (item.results.get(bucket) or {}).get(field_name)
            if text and text.strip():
                entries.append(WriteEntry(
                    photo_id=int(photo_id),
                    text=text,
                    label=item.name,
                    language=_language_code(item),
                    stage=candidate,
                ))
                break
    return entries


def _language_code(item) -> str:
    """Best available ISO code for the note, defaulting to German."""
    translated = item.results.get("translated") or {}
    code = translated.get("source_language")
    if code and isinstance(code, str) and code.isalpha() and len(code) <= 3:
        return code.lower()
    return "de"

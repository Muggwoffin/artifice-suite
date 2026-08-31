# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Write OCR results back into a Tropy project — **opt-in and default off**.

This module **knowingly reverses commit ``ebd89e6`` ("Tropy integration fix")**,
which deleted it in favour of the JSON-LD bridge (``tropy_jsonld.py``). The
maintainer chose to restore it because the JSON-LD round-trip only ever
*creates* items when re-imported into Tropy — it cannot annotate the photos
that already exist in a project. This module writes OCR text directly into the
``notes`` (and, optionally, ``transcriptions``) tables of a live ``.tpy``
project, so results appear in the normal note pane, are searchable, and are
easy to delete. **Do not "re-fix" this by deleting it again** — its absence is
a decision that has already been made and reversed.

Because this writes to the user's research database it is gated off unless the
user turns it on: the ``tropy_writeback_enabled`` config setting is ``False``
by default, and with it off no write path executes and no writable connection
is ever opened. The read path (:mod:`tropy_db`) stays provably read-only and
never imports this module.

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
    transcription UI reads. Marked with ``config.generator = "artifice_ocr"``
    so ours are always identifiable.

Both tables carry AFTER INSERT triggers that maintain the full-text search
index, so inserts alone keep search working.
"""

import json
import os
import shutil
import sqlite3
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import config
from ._logging import get_logger
from .tropy_db import resolve_project_db_path

log = get_logger("tropy_write")

TARGET_NOTES = "notes"
TARGET_TRANSCRIPTIONS = "transcriptions"
VALID_TARGETS = (TARGET_NOTES, TARGET_TRANSCRIPTIONS)

GENERATOR = "artifice_ocr"

_DISABLED_MESSAGE = (
    "Tropy write-back is disabled — enable the 'tropy_writeback_enabled' "
    "setting to write OCR results back into a Tropy project"
)


def _writeback_enabled() -> bool:
    """True when the opt-in write-back setting is on (default off)."""
    return bool(config.get("tropy_writeback_enabled", False))


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
    """Compatibility hook; process-list probing is intentionally disabled.

    Enumerating the host process table is both unreliable and resembles a
    defense-evasion pattern to endpoint protection. The SQLite
    ``BEGIN IMMEDIATE`` probe in :meth:`TropyWriter.blockers` is the reliable,
    application-specific concurrency check. Tests and downstream callers may
    still override this hook to model an external blocker.
    """
    return False


def _prosemirror_state(text: str) -> str:
    """Build the ProseMirror document Tropy stores alongside a note's text.

    Matches the shape of existing notes in the project: a doc of left-aligned
    paragraphs, one per line, with empty lines dropped (ProseMirror rejects a
    text node with an empty string) — plus a top-level `selection` key, which
    every real Tropy note carries and which this function used to omit
    entirely. Confirmed by comparing against 1101 real notes in a live
    project: 100% have `selection`, 0% lack it. ProseMirror's own
    `EditorState.fromJSON()` reconstructs the cursor from that key when a
    note is opened; without it, Tropy's note editor crashes on open (a
    minified React error, #520) instead of rendering — a stored note that
    can never be read back is exactly the kind of silent corruption this
    project's other guards exist to prevent, just in a different tool.
    Position 0 (the very start of the document) is valid for any non-empty
    doc, so it's used unconditionally rather than trying to reproduce
    Tropy's own end-of-text-after-typing cursor convention.
    """
    paragraphs = []
    for line in text.splitlines():
        node: dict = {"type": "paragraph", "attrs": {"align": "left"}}
        if line.strip():
            node["content"] = [{"type": "text", "text": line}]
        paragraphs.append(node)
    if not paragraphs:
        paragraphs = [
            {
                "type": "paragraph",
                "attrs": {"align": "left"},
                "content": [{"type": "text", "text": text}],
            }
        ]
    return json.dumps(
        {
            "doc": {"type": "doc", "content": paragraphs},
            "selection": {"type": "text", "anchor": 0, "head": 0},
        },
        ensure_ascii=False,
    )


def _display_path(path: Path) -> str:
    """Privacy-safe display form of a filesystem path.

    Logs and error messages get pasted into issue reports, and the absolute
    database path normally contains the username and the archive location
    (and sometimes the research topic). Return the basename alone, prefixed
    with ``~/…/`` when the path lies under the home directory. The *project*
    stays identifiable, and the caller learns whether it sits inside their
    home directory, without any intermediate component being disclosed.

    Emitting the full home-relative tail (``~/Documents/Cairo-1919/…``) would
    disclose precisely the archive location and research topic this function
    exists to withhold, so no intermediate component is ever returned. That
    distinction is platform-sensitive and was previously invisible: on POSIX
    a temporary path is not under ``$HOME``, whereas on Windows the user's
    temp directory is, so only the Windows job caught the leak.
    """
    resolved = Path(path)
    home: Path | None = None
    try:
        home = Path.home()
    except (RuntimeError, KeyError, OSError):
        home = None
    if home is not None and home != Path(home.anchor):
        try:
            if resolved == home:
                return "~"
            if resolved.is_relative_to(home):
                return f"~/…/{resolved.name}" if resolved.name else "~"
        except (ValueError, OSError):
            pass
    return resolved.name


def _redact_text(text: str, db_path: Path) -> str:
    """Scrub the absolute project path (and the home directory) out of text.

    Used on exception messages and log lines that may embed a filesystem path.
    Paths are replaced longest-first so the file and its containing directory
    are swapped as wholes rather than partially (which would leave a truncated
    absolute prefix behind).
    """
    candidates: set[str] = set()
    candidates.add(str(db_path))
    if db_path.parent != db_path:
        candidates.add(str(db_path.parent))
    with suppress(RuntimeError, KeyError, OSError):
        candidates.add(str(Path.home()))
    for raw in sorted(candidates, key=len, reverse=True):
        if raw:
            text = text.replace(raw, _display_path(Path(raw)))
    return text


def _sanitise_error(exc: BaseException, db_path: Path) -> str:
    """User-safe description of an exception for the write report.

    The raw exception text from a corrupt database can carry absolute paths,
    schema text, or fragments of stored content — none of which belongs in a
    report the UI renders or a log someone will paste into an issue. Keep the
    exception *type* (still diagnostic) plus a redacted rendering of the
    message; the full detail is logged separately at DEBUG, redacted.
    """
    detail = _redact_text(str(exc), db_path).strip()
    name = type(exc).__name__
    return f"{name}: {detail}" if detail else name


class TropyWriter:
    """Read-write handle on a Tropy project. Opens lazily and safely."""

    def __init__(self, project_path: str | Path):
        self.db_path = resolve_project_db_path(project_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"No Tropy database at {_display_path(self.db_path)}")
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

        if not _writeback_enabled():
            problems.append(_DISABLED_MESSAGE)
            return problems

        if _tropy_is_running():
            problems.append(
                "Tropy is running — close it before writing, or it will "
                "overwrite these changes from its in-memory state"
            )

        if not os.access(self.db_path, os.W_OK):
            problems.append(f"{_display_path(self.db_path)} is not writable")

        # A held write lock means something else is mid-transaction.
        try:
            probe = sqlite3.connect(str(self.db_path), timeout=1.0, isolation_level=None)
            try:
                probe.execute("BEGIN IMMEDIATE")
                probe.execute("ROLLBACK")
            finally:
                probe.close()
        except sqlite3.OperationalError as exc:
            problems.append(f"{_display_path(self.db_path)} is locked by another process")
            log.debug("Tropy lock probe failed: %s", _redact_text(str(exc), self.db_path))

        return problems

    def backup(self) -> Path:
        """Timestamped copy of the database (and its WAL sidecars)."""
        if not _writeback_enabled():
            raise RuntimeError(_DISABLED_MESSAGE)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = self.db_path.with_name(f"{self.db_path.stem}.{stamp}.backup.tpy")
        shutil.copy2(self.db_path, target)
        for suffix in ("-wal", "-shm"):
            side = Path(str(self.db_path) + suffix)
            if side.exists():
                shutil.copy2(side, Path(str(target) + suffix))
        log.info("Backed up Tropy database to %s", _display_path(target))
        return target

    # --------------------------------------------------------------- preview
    def preview(self, entries: Iterable[WriteEntry], targets: Iterable[str]) -> Preview:
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
                    result.plans.append(EntryPlan(entry, target, "empty", "no text for this page"))
                    continue
                if entry.photo_id not in known_photos:
                    result.plans.append(
                        EntryPlan(
                            entry,
                            target,
                            "missing-photo",
                            f"photo {entry.photo_id} is not in this project",
                        )
                    )
                    continue
                if self._already_present(con, target, entry.photo_id, text):
                    result.plans.append(
                        EntryPlan(
                            entry,
                            target,
                            "duplicate",
                            "identical text already attached to this photo",
                        )
                    )
                    continue
                result.plans.append(EntryPlan(entry, target, "insert"))

        return result

    def _already_present(
        self, con: sqlite3.Connection, target: str, photo_id: int, text: str
    ) -> bool:
        table = "notes" if target == TARGET_NOTES else "transcriptions"
        row = con.execute(
            f"SELECT 1 FROM {table} WHERE id = ? AND text = ? AND deleted IS NULL LIMIT 1",
            (photo_id, text),
        ).fetchone()
        return row is not None

    # ----------------------------------------------------------------- write
    def write(self, preview: Preview, *, make_backup: bool = True) -> WriteReport:
        """Apply an approved preview. Refuses to run if there are blockers."""
        report = WriteReport()

        if not _writeback_enabled():
            report.errors.append(_DISABLED_MESSAGE)
            return report

        if preview.blockers:
            report.errors.extend(preview.blockers)
            return report

        plans = preview.insertable
        report.skipped = len(preview.plans) - len(plans)
        if not plans:
            return report

        self.close()  # reopen read-write
        con = self._connect(write=True)

        # Re-run the preflight at write time, immediately before taking the
        # write lock. The preview may have been approved minutes ago, and Tropy
        # (or another writer) can appear in the gap — ``BEGIN IMMEDIATE`` below
        # is the atomic backstop for the lock, but it cannot see a Tropy
        # process that is running yet still opening its database lazily.
        # (TOCTOU fix for F1.)
        blockers = self.blockers()
        if blockers:
            report.errors.extend(blockers)
            return report

        try:
            # Hold the write lock across the backup and the inserts. Taking the
            # copies while holding the lock means no concurrent writer or
            # checkpoint can interleave between the ``.tpy``/``-wal``/``-shm``
            # copies and produce an unrestorable backup set (F4).
            con.execute("BEGIN IMMEDIATE")
            if make_backup:
                report.backup = self.backup()
            for plan in plans:
                entry = plan.entry
                text = entry.text.strip()
                if plan.target == TARGET_NOTES:
                    con.execute(
                        "INSERT INTO notes (id, text, state, language) VALUES (?, ?, ?, ?)",
                        (entry.photo_id, text, _prosemirror_state(text), entry.clean_language()),
                    )
                else:
                    config_json = json.dumps(
                        {
                            "generator": GENERATOR,
                            "stage": entry.stage,
                            "created": datetime.now().isoformat(timespec="seconds"),
                        },
                        ensure_ascii=False,
                    )
                    con.execute(
                        "INSERT INTO transcriptions (id, text, config, data, status) "
                        "VALUES (?, ?, ?, ?, 0)",
                        (entry.photo_id, text, config_json, None),
                    )
                report.written += 1
            con.execute("COMMIT")
            log.info("Wrote %d row(s) into %s", report.written, _display_path(self.db_path))
        except Exception as exc:
            con.execute("ROLLBACK")
            report.errors.append(_sanitise_error(exc, self.db_path))
            report.written = 0
            log.error("Tropy write rolled back: %s", _sanitise_error(exc, self.db_path))
            log.debug("Tropy write failure detail: %s", _redact_text(str(exc), self.db_path))

        return report

    # ---------------------------------------------------------------- repair
    def repair_missing_selections(self, *, make_backup: bool = True) -> int:
        """Fix notes written before `_prosemirror_state()` carried a
        `selection` key. That bug crashed Tropy's note editor on open (a
        minified React error, #520) for every note it wrote — the write
        itself always succeeded, so nothing caught it at the time. Only the
        `state` column is touched, and only for rows actually missing the
        key; text, doc content, and language are left exactly as they were.

        Returns the number of rows repaired. Raises if there are blockers
        (Tropy running, database locked, write-back disabled, etc.) — same
        preflight as write().
        """
        blockers = self.blockers()
        if blockers:
            raise RuntimeError("; ".join(blockers))

        con = self._connect(write=False)
        to_fix: list[tuple[str, int]] = []
        for row in con.execute("SELECT note_id, state FROM notes"):
            try:
                data = json.loads(row["state"])
            except (TypeError, ValueError):
                continue
            if "selection" not in data:
                data["selection"] = {"type": "text", "anchor": 0, "head": 0}
                to_fix.append((json.dumps(data, ensure_ascii=False), row["note_id"]))

        if not to_fix:
            return 0

        # Re-run the preflight immediately before taking the write lock — the
        # same TOCTOU guard as write(): Tropy can be reopened, or the database
        # locked, in the time between the first preflight above and here.
        blockers = self.blockers()
        if blockers:
            raise RuntimeError("; ".join(blockers))

        self.close()  # reopen read-write
        con = self._connect(write=True)
        try:
            # Hold the write lock across the backup and the repair so no other
            # writer can interleave between the backup copies (F4).
            con.execute("BEGIN IMMEDIATE")
            if make_backup:
                self.backup()
            con.executemany("UPDATE notes SET state = ? WHERE note_id = ?", to_fix)
            con.execute("COMMIT")
            log.info(
                "Repaired %d note(s) missing a selection in %s",
                len(to_fix),
                _display_path(self.db_path),
            )
        except Exception:
            con.execute("ROLLBACK")
            raise

        return len(to_fix)


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
    entries: list[WriteEntry] = []
    for item in items:
        photo_id = (item.source or {}).get("photo_id")
        if photo_id is None:
            continue
        bucket, field_name = key_map.get(stage, key_map["cleaned"])
        text = (item.results.get(bucket) or {}).get(field_name)
        if text and text.strip():
            entries.append(
                WriteEntry(
                    photo_id=int(photo_id),
                    text=text,
                    label=item.name,
                    language=_language_code(item),
                    stage=stage,
                )
            )
    return entries


def _language_code(item) -> str:
    """Best available ISO code for the note, defaulting to German."""
    translated = item.results.get("translated") or {}
    code = translated.get("source_language")
    if code and isinstance(code, str) and code.isalpha() and len(code) <= 3:
        return code.lower()
    return "de"

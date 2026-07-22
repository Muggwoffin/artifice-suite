"""Read-only reader for Tropy projects.

This module never writes to a Tropy project. The connection is opened with
``mode=ro`` so the tool cannot modify a project even if Tropy is running with
an open write-ahead log. (``immutable=1`` would be wrong here: it makes SQLite
ignore the WAL, so edits made in a running Tropy would be invisible.)

A `.tropy` "managed" project is a directory, not a file::

    ISK Project Primary Sources.tropy/
      project.tpy      SQLite database
      assets/          content-addressed originals, <checksum>.pdf / .jpg

Photos in Tropy are *pages*, not files: a 275-page item is 275 rows in
``photos`` that all share one ``assets/<checksum>.pdf`` path and differ by the
``page`` column. That is why each page gets its own output key.
"""

import json
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ._logging import get_logger

log = get_logger("tropy")

TITLE_PROPERTY = "http://purl.org/dc/elements/1.1/title"

PROJECT_SUFFIX = ".tropy"
PROJECT_DB_NAME = "project.tpy"

# Characters Windows forbids in a path segment, plus the separators.
_UNSAFE = '<>:"/\\|?*'


def _safe_name(name: str, fallback: str = "untitled") -> str:
    """Make a string usable as a single path segment."""
    cleaned = "".join("_" if c in _UNSAFE else c for c in (name or "")).strip(" .")
    cleaned = " ".join(cleaned.split())
    return cleaned[:120] or fallback


# --------------------------------------------------------------------------- #
# value objects
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class TropyList:
    list_id: int
    name: str
    parent_id: int | None
    depth: int
    item_count: int

    @property
    def label(self) -> str:
        return f"{'    ' * self.depth}{self.name}  ({self.item_count})"


@dataclass(frozen=True)
class TropyItem:
    item_id: int
    title: str
    photo_count: int

    @property
    def label(self) -> str:
        return f"{self.title}  —  {self.photo_count} page(s)"


@dataclass(frozen=True)
class TropyPage:
    """One OCR-able page: a Tropy photo row resolved to a real file."""

    photo_id: int
    item_id: int
    item_title: str
    filename: str          # original name, e.g. KV-2-2339_01.pdf
    path: Path             # resolved absolute path into assets/
    page: int              # 0-based index within the file
    mimetype: str
    output_stem: str = ""  # "<Item Title>/<file>_p0002", set by TropyProject
    orientation: int = 1   # Tropy's photos.orientation column, EXIF 1-8 (1 = normal)

    @property
    def is_pdf(self) -> bool:
        return self.mimetype == "application/pdf" or self.path.suffix.lower() == ".pdf"

    @property
    def page_number(self) -> int:
        """1-based page number, for display."""
        return self.page + 1

    @property
    def label(self) -> str:
        if self.is_pdf:
            return f"{self.filename}  p.{self.page_number}"
        return self.filename

    def provenance(self) -> dict:
        """The record written into the run manifest."""
        return {
            "photo_id": self.photo_id,
            "item_id": self.item_id,
            "item_title": self.item_title,
            "filename": self.filename,
            "page": self.page,
            "page_number": self.page_number,
            "source_path": str(self.path),
            "mimetype": self.mimetype,
            "orientation": self.orientation,
        }


# --------------------------------------------------------------------------- #
# project
# --------------------------------------------------------------------------- #

class TropyProject:
    """Read-only handle on a Tropy project."""

    def __init__(self, path: str | Path):
        self.bundle_dir, self.db_path = _resolve_project_paths(path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"No Tropy database at {self.db_path}")

        uri = f"file:{self.db_path.as_posix()}?mode=ro"
        try:
            self._con = sqlite3.connect(uri, uri=True)
        except sqlite3.OperationalError as exc:
            raise RuntimeError(
                f"Could not open {self.db_path} read-only ({exc}). "
                "If Tropy is running, try closing it."
            ) from exc
        self._con.row_factory = sqlite3.Row

        row = self._con.execute("SELECT * FROM project").fetchone()
        self.name = row["name"] if row else self.bundle_dir.stem
        self.base = row["base"] if row else None
        self.store = (row["store"] if row else None) or "assets"

    # ------------------------------------------------------------- lifecycle
    def close(self) -> None:
        self._con.close()

    def __enter__(self) -> "TropyProject":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------ navigation
    def lists(self) -> list[TropyList]:
        """All lists as a flattened tree, ROOT excluded, in display order."""
        rows = self._con.execute(
            "SELECT list_id, name, parent_list_id, position FROM lists"
        ).fetchall()
        by_parent: dict[int | None, list[sqlite3.Row]] = {}
        for row in rows:
            by_parent.setdefault(row["parent_list_id"], []).append(row)
        for children in by_parent.values():
            children.sort(key=lambda r: (r["position"] if r["position"] is not None else 0,
                                         r["name"] or ""))

        out: list[TropyList] = []

        def walk(parent_id: int, depth: int) -> None:
            for row in by_parent.get(parent_id, []):
                out.append(TropyList(
                    list_id=row["list_id"],
                    name=row["name"] or "(unnamed)",
                    parent_id=row["parent_list_id"],
                    depth=depth,
                    item_count=len(self.item_ids_in_list(row["list_id"])),
                ))
                walk(row["list_id"], depth + 1)

        walk(0, 0)  # list_id 0 is Tropy's ROOT
        return out

    def tags(self) -> list[tuple[str, int]]:
        """Tag names with the number of items carrying them."""
        rows = self._con.execute(
            """SELECT t.name AS name, COUNT(g.id) AS n
               FROM tags t
               LEFT JOIN taggings g ON g.tag_id = t.tag_id
               LEFT JOIN items i ON i.id = g.id
               GROUP BY t.tag_id ORDER BY t.name COLLATE NOCASE"""
        ).fetchall()
        return [(r["name"], r["n"]) for r in rows]

    def item_ids_in_list(self, list_id: int) -> list[int]:
        """Items in a list *and all of its sub-lists*.

        Tropy lists nest (KV Files sits under National Archives UK), and
        picking a parent list should mean "everything underneath it".
        """
        rows = self._con.execute(
            """WITH RECURSIVE sub(list_id) AS (
                   SELECT ?
                   UNION ALL
                   SELECT l.list_id FROM lists l JOIN sub ON l.parent_list_id = sub.list_id
               )
               SELECT DISTINCT li.id AS id
               FROM list_items li
               JOIN sub ON sub.list_id = li.list_id
               JOIN items i ON i.id = li.id
               WHERE li.deleted IS NULL
                 AND li.id NOT IN (SELECT id FROM trash)""",
            (list_id,),
        ).fetchall()
        return [r["id"] for r in rows]

    def item_ids_with_tag(self, tag_name: str) -> list[int]:
        rows = self._con.execute(
            """SELECT DISTINCT g.id AS id
               FROM taggings g
               JOIN tags t ON t.tag_id = g.tag_id
               JOIN items i ON i.id = g.id
               WHERE t.name = ? AND g.id NOT IN (SELECT id FROM trash)""",
            (tag_name,),
        ).fetchall()
        return [r["id"] for r in rows]

    def items(self, item_ids: list[int] | None = None) -> list[TropyItem]:
        """Items with titles and page counts. All non-trashed items if None."""
        sql = f"""
            SELECT i.id AS id,
                   mv.text AS title,
                   (SELECT COUNT(*) FROM photos p WHERE p.item_id = i.id) AS n
            FROM items i
            LEFT JOIN metadata m ON m.id = i.id AND m.property = ?
            LEFT JOIN metadata_values mv ON mv.value_id = m.value_id
            WHERE i.id NOT IN (SELECT id FROM trash)
        """
        params: list = [TITLE_PROPERTY]
        if item_ids is not None:
            if not item_ids:
                return []
            sql += f" AND i.id IN ({','.join('?' * len(item_ids))})"
            params.extend(item_ids)
        sql += " ORDER BY mv.text COLLATE NOCASE, i.id"

        return [
            TropyItem(
                item_id=r["id"],
                title=r["title"] or f"Item {r['id']}",
                photo_count=r["n"],
            )
            for r in self._con.execute(sql, params).fetchall()
        ]

    # ----------------------------------------------------------------- pages
    def pages(self, item_ids: list[int] | None = None) -> list[TropyPage]:
        """Every page of the given items, resolved to real files."""
        titles = {i.item_id: i.title for i in self.items(item_ids)}
        if not titles:
            return []

        ids = list(titles)
        rows = self._con.execute(
            f"""SELECT p.id, p.item_id, p.path, p.page, p.filename, p.mimetype, p.orientation
                FROM photos p
                WHERE p.item_id IN ({','.join('?' * len(ids))})
                  AND p.id NOT IN (SELECT id FROM trash)
                ORDER BY p.item_id, p.filename, p.page, p.id""",
            ids,
        ).fetchall()

        pages: list[TropyPage] = []
        seen: set[str] = set()
        for row in rows:
            item_title = titles.get(row["item_id"], f"Item {row['item_id']}")
            filename = row["filename"] or Path(row["path"]).name
            resolved = self.resolve_path(row["path"])

            stem = _page_stem(item_title, filename, row["page"], row["mimetype"],
                              resolved)
            if stem in seen:  # duplicate filenames inside one item
                stem = f"{stem}_{row['id']}"
            seen.add(stem)

            pages.append(TropyPage(
                photo_id=row["id"],
                item_id=row["item_id"],
                item_title=item_title,
                filename=filename,
                path=resolved,
                page=row["page"] or 0,
                mimetype=row["mimetype"] or "",
                output_stem=stem,
                orientation=row["orientation"] or 1,
            ))
        return pages

    def resolve_path(self, stored: str) -> Path:
        """Turn a stored photo path into an absolute path.

        Tropy writes both separators — this project has 868 rows using
        backslashes and the rest forward slashes — so normalise before
        resolving.
        """
        normalised = (stored or "").replace("\\", "/")
        candidate = Path(normalised)
        if candidate.is_absolute():
            return candidate
        return (self.bundle_dir / candidate).resolve()

    def missing_assets(self, pages: list[TropyPage]) -> list[TropyPage]:
        """Pages whose backing file is not on disk (iCloud placeholders etc.)."""
        checked: dict[Path, bool] = {}
        missing = []
        for page in pages:
            if page.path not in checked:
                checked[page.path] = page.path.exists()
            if not checked[page.path]:
                missing.append(page)
        return missing


def _page_stem(item_title: str, filename: str, page: int | None,
               mimetype: str, resolved: Path) -> str:
    """Output key for one page: ``<Item Title>/<file>_p0002``.

    The subdirectory groups an item's pages together; the page suffix is what
    stops every page of a PDF from colliding on the checksum stem.
    """
    is_pdf = mimetype == "application/pdf" or resolved.suffix.lower() == ".pdf"
    base = _safe_name(Path(filename).stem, fallback="page")
    folder = _safe_name(item_title, fallback="untitled")
    if is_pdf:
        return f"{folder}/{base}_p{(page or 0) + 1:04d}"
    return f"{folder}/{base}"


def _resolve_project_paths(path: str | Path) -> tuple[Path, Path]:
    """Accept a .tropy bundle, a project.tpy, or a directory containing one."""
    p = Path(path).expanduser()
    if p.is_file() and p.suffix == ".tpy":
        return p.parent, p
    if p.is_dir():
        db = p / PROJECT_DB_NAME
        if db.exists():
            return p, db
        matches = sorted(p.glob("*.tpy"))
        if matches:
            return p, matches[0]
    # Unmanaged single-file project
    if p.suffix == ".tpy":
        return p.parent, p
    return p, p / PROJECT_DB_NAME


# --------------------------------------------------------------------------- #
# discovery
# --------------------------------------------------------------------------- #

def tropy_config_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming")
        return Path(base) / "Tropy"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Tropy"
    return Path(
        os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    ) / "Tropy"


def recent_projects() -> list[Path]:
    """Projects Tropy has opened recently, newest first. Missing ones dropped."""
    state = tropy_config_dir() / "state.json"
    if not state.exists():
        return []
    try:
        with open(state, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    out: list[Path] = []
    for entry in data.get("recent") or []:
        p = Path(entry)
        if p.exists():
            out.append(p)
    return out


def pages_to_job_items(pages: list[TropyPage]) -> list:
    """Turn Tropy pages into queue items the existing runner understands."""
    from .jobs import JobItem

    return [
        JobItem(
            path=str(page.path),
            page=page.page if page.is_pdf else None,
            output_stem=page.output_stem,
            label=page.label,
            source=page.provenance(),
        )
        for page in pages
    ]


# --------------------------------------------------------------------------- #
# manifest
# --------------------------------------------------------------------------- #

def write_manifest(
    output_dir: str | Path,
    project: TropyProject,
    pages: list[TropyPage],
    *,
    filename: str = "tropy_manifest.json",
) -> Path:
    """Record which output belongs to which Tropy photo.

    Without this the mapping from ``output/.../KV-2-2339_01_p0002.txt`` back to
    photo 1473 of item 1 exists only in someone's head.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / filename

    existing: dict = {}
    if target.exists():
        try:
            with open(target, encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = {}

    entries = existing.get("pages") or {}
    for page in pages:
        entries[page.output_stem] = page.provenance()

    payload = {
        "project": {
            "name": project.name,
            "database": str(project.db_path),
            "bundle": str(project.bundle_dir),
        },
        "output_layout": "<stage>/text/<item title>/<file>_p<page>.txt",
        "pages": entries,
    }
    with open(target, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    log.info("Wrote manifest for %d page(s) to %s", len(pages), target)
    return target

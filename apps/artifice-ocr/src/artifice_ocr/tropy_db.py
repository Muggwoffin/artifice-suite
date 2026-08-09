# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Read-only Tropy .tpy SQLite database browser.

Opens Tropy project databases in immutable mode for browsing projects,
lists, tags, items, and photos without modifying database state. Never
writes — all connections use ``file:<path>?mode=ro`` URI form with
short-lived per-query connections.

A running Tropy instance holds a write lock on the .tpy file; our read-only
connection may get SQLITE_BUSY. We handle this by opening a fresh
short-lived connection per query and catching SQLITE_BUSY with a clean
error message advising the user to close Tropy and retry.

Schema is the real Tropy ``.tpy`` schema:
  - ``subjects`` — shared id space for items, photos, and selections
  - ``items`` — REFERENCES subjects(id), no title column
  - ``metadata`` / ``metadata_values`` — normalised title storage
  - ``photos`` — base-relative paths resolved against ``project.base``
  - ``trash`` — soft-delete filter
  - ``taggings`` — REFERENCES subjects(id) not items(id)
"""

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from ._logging import get_logger
from ._tropy_pathcheck import PhotoPathResult, validate_absolute_photo

log = get_logger("tropy_db")

# --------------------------------------------------------------------------- #
# errors & data classes
# --------------------------------------------------------------------------- #


class TropyDBError(Exception):
    """User-facing error from the Tropy database browser."""


@dataclass(frozen=True)
class TropyPhoto:
    """One photo from a Tropy item."""

    photo_id: int
    path: str
    item_id: int
    page: int | None
    mimetype: str
    checksum: str
    orientation: int
    missing: bool


@dataclass(frozen=True)
class TropyItem:
    """One item from a Tropy project."""

    item_id: int
    title: str
    photos: list  # list[TropyPhoto]


# --------------------------------------------------------------------------- #
# connection
# --------------------------------------------------------------------------- #


def _connect(db_path: Path) -> sqlite3.Connection:
    """Open a short-lived read-only connection to the .tpy file.

    Raises :class:`TropyDBError` on SQLITE_BUSY or other connection failures.
    """
    if not db_path.exists():
        raise TropyDBError(f"Database file not found: {db_path.name}")
    uri = f"file:{db_path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=1.0)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.OperationalError as exc:
        msg = str(exc).lower()
        if "locked" in msg or "busy" in msg:
            raise TropyDBError(
                "Tropy database is locked — close Tropy and try again"
            ) from exc
        raise TropyDBError(f"Could not open database: {db_path.name}") from exc


# --------------------------------------------------------------------------- #
# project base resolution
# --------------------------------------------------------------------------- #


def _get_project_base(conn: sqlite3.Connection) -> str | None:
    """Read the ``project`` table and return the ``base`` value.

    Returns ``None`` if the table is missing or empty.
    """
    try:
        row = conn.execute("SELECT base FROM project LIMIT 1").fetchone()
        if row:
            return row["base"]
    except sqlite3.OperationalError as exc:
        log.warning("Could not read project table: %s", exc)
    return None


def _resolve_photo_path(
    photo_path: str, db_path: Path, base: str | None,
) -> Path:
    """Resolve a base-relative photo path to an absolute :class:`Path`.

    ``base`` values:
    - ``'project'`` — resolve relative to the folder containing the .tpy file
    - ``'home'`` — resolve relative to ``Path.home()``
    - ``None`` — resolve relative to the DB folder (same as ``'project'``)
    - An absolute path string — use as the base directory
    - Any other string — resolve relative to the DB folder
    """
    if not base:
        return (db_path.parent / photo_path).resolve()
    if base == "project":
        return (db_path.parent / photo_path).resolve()
    if base == "home":
        return (Path.home() / photo_path).resolve()
    if Path(base).is_absolute():
        return (Path(base) / photo_path).resolve()
    # Relative base string — resolve relative to DB folder
    return (db_path.parent / base / photo_path).resolve()


# --------------------------------------------------------------------------- #
# title extraction via metadata join
# --------------------------------------------------------------------------- #


_TITLE_PROPERTIES = (
    "http://purl.org/dc/elements/1.1/title",
    "http://purl.org/dc/terms/title",
)

_TITLE_QUERY = (
    "SELECT mv.text FROM metadata m "
    "JOIN metadata_values mv ON m.value_id = mv.value_id "
    "WHERE m.id = ? AND m.property IN ("
    "'http://purl.org/dc/elements/1.1/title', "
    "'http://purl.org/dc/terms/title') "
    "LIMIT 1"
)


def _get_item_title(conn: sqlite3.Connection, item_id: int) -> str:
    """Get a display title for an item.

    1. Query ``metadata`` → ``metadata_values`` join for a Dublin Core title.
    2. Fall back to the first photo's ``filename`` column.
    3. Ultimate fallback: ``"Item {item_id}"``.
    """
    # 1. Metadata join
    try:
        row = conn.execute(_TITLE_QUERY, (item_id,)).fetchone()
        if row and row[0] and str(row[0]).strip():
            return str(row[0]).strip()
    except sqlite3.OperationalError as exc:
        log.warning(
            "Could not read metadata for item %d: %s", item_id, exc,
        )

    # 2. Fall back to first photo filename
    try:
        photo_row = conn.execute(
            "SELECT filename FROM photos "
            "WHERE item_id = ? ORDER BY position, id LIMIT 1",
            (item_id,),
        ).fetchone()
        if photo_row and photo_row[0] and str(photo_row[0]).strip():
            return str(photo_row[0]).strip()
    except sqlite3.OperationalError as exc:
        log.warning(
            "Could not read photos for item %d title: %s", item_id, exc,
        )

    # 3. Ultimate fallback
    return f"Item {item_id}"


# --------------------------------------------------------------------------- #
# photo reading with path resolution
# --------------------------------------------------------------------------- #


def _read_photos(
    conn: sqlite3.Connection,
    item_id: int,
    db_path: Path,
    base: str | None,
) -> list[TropyPhoto]:
    """Read all photos for one item, resolve base-relative paths, and validate."""
    photos: list[TropyPhoto] = []
    try:
        rows = conn.execute(
            "SELECT * FROM photos WHERE item_id = ? ORDER BY id",
            (item_id,),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        log.warning("Could not read photos for item %d: %s", item_id, exc)
        return photos

    for row in rows:
        photo_id = row["id"]
        raw_path = row["path"]
        orientation = row["orientation"] if row["orientation"] is not None else 1
        mimetype = row["mimetype"] or ""
        checksum = row["checksum"] or ""
        page_raw = row["page"]
        page = int(page_raw) if page_raw is not None else None

        # Resolve the base-relative path to absolute.
        try:
            absolute = _resolve_photo_path(raw_path, db_path, base)
        except Exception as exc:
            log.warning(
                "Photo %d (item %d) path resolution failed: %s — marking missing",
                photo_id, item_id, exc,
            )
            photos.append(
                TropyPhoto(
                    photo_id=photo_id,
                    path=raw_path,
                    item_id=item_id,
                    page=page,
                    mimetype=mimetype,
                    checksum=checksum,
                    orientation=orientation,
                    missing=True,
                )
            )
            continue

        # Validate the resolved absolute photo path.
        missing = False
        try:
            result: PhotoPathResult = validate_absolute_photo(str(absolute))
            resolved_path = str(result.resolved)
            missing = result.missing
        except ValueError as exc:
            log.warning(
                "Photo %d (item %d) path rejected: %s — marking missing",
                photo_id, item_id, exc,
            )
            resolved_path = str(absolute)
            missing = True

        photos.append(
            TropyPhoto(
                photo_id=photo_id,
                path=resolved_path,
                item_id=item_id,
                page=page,
                mimetype=mimetype,
                checksum=checksum,
                orientation=orientation,
                missing=missing,
            )
        )
    return photos


# --------------------------------------------------------------------------- #
# public query functions
# --------------------------------------------------------------------------- #


def list_projects(db_path: str | Path) -> list[dict]:
    """Read the single ``project`` row.

    Returns a list of dicts for API compatibility.  In a valid Tropy database
    there is exactly one row.
    """
    p = Path(db_path)
    conn = _connect(p)
    try:
        rows = conn.execute("SELECT * FROM project").fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError as exc:
        log.warning("Could not read project table: %s", exc)
        return []
    finally:
        conn.close()


def list_lists(db_path: str | Path) -> list[dict]:
    """List all lists, excluding the ROOT row (list_id=0)."""
    p = Path(db_path)
    conn = _connect(p)
    try:
        rows = conn.execute(
            "SELECT * FROM lists WHERE list_id != 0 ORDER BY list_id",
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError as exc:
        log.warning("Could not read lists table: %s", exc)
        return []
    finally:
        conn.close()


def list_tags(db_path: str | Path) -> list[dict]:
    """List all tags in the database."""
    p = Path(db_path)
    conn = _connect(p)
    try:
        rows = conn.execute("SELECT * FROM tags ORDER BY tag_id").fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError as exc:
        log.warning("Could not read tags table: %s", exc)
        return []
    finally:
        conn.close()


# ---- item queries ----------------------------------------------------------


def list_items(
    db_path: str | Path,
    *,
    list_id: int | None = None,
    tag: str | None = None,
) -> list[TropyItem]:
    """List items, optionally filtered by list ID or tag name.

    For each item, fetch its title via the metadata join and its photos
    (with base-relative paths resolved against ``project.base``).
    Soft-deleted items (in the ``trash`` table) are excluded.
    """
    p = Path(db_path)
    conn = _connect(p)

    # Read project base once.
    base = _get_project_base(conn)

    try:
        if list_id is not None:
            rows = conn.execute(
                """
                SELECT i.id FROM items i
                JOIN list_items li ON li.id = i.id
                LEFT JOIN trash t ON t.id = i.id
                WHERE li.list_id = ? AND li.deleted IS NULL
                  AND t.deleted IS NULL
                ORDER BY li.position, i.id
                """,
                (list_id,),
            ).fetchall()
        elif tag is not None:
            rows = conn.execute(
                """
                SELECT i.id FROM items i
                JOIN taggings tg ON tg.id = i.id
                JOIN tags t ON t.tag_id = tg.tag_id
                LEFT JOIN trash tr ON tr.id = i.id
                WHERE t.name = ? AND tr.deleted IS NULL
                ORDER BY i.id
                """,
                (tag,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT i.id FROM items i
                LEFT JOIN trash t ON t.id = i.id
                WHERE t.deleted IS NULL
                ORDER BY i.id
                """,
            ).fetchall()
    except sqlite3.OperationalError as exc:
        log.warning("Could not read items table: %s", exc)
        conn.close()
        return []

    items: list[TropyItem] = []
    for row in rows:
        item_id = row["id"]
        title = _get_item_title(conn, item_id)
        photos = _read_photos(conn, item_id, p, base)
        items.append(TropyItem(item_id=item_id, title=title, photos=photos))

    conn.close()
    return items


def get_item(db_path: str | Path, item_id: int) -> TropyItem | None:
    """Get a single item with its photos, or None if not found."""
    p = Path(db_path)
    conn = _connect(p)

    # Read project base once.
    base = _get_project_base(conn)

    try:
        row = conn.execute(
            "SELECT i.id FROM items i "
            "LEFT JOIN trash t ON t.id = i.id "
            "WHERE i.id = ? AND t.deleted IS NULL",
            (item_id,),
        ).fetchone()
    except sqlite3.OperationalError as exc:
        log.warning("Could not read item %d: %s", item_id, exc)
        conn.close()
        return None

    if row is None:
        conn.close()
        return None

    title = _get_item_title(conn, item_id)
    photos = _read_photos(conn, item_id, p, base)
    conn.close()
    return TropyItem(item_id=item_id, title=title, photos=photos)


# --------------------------------------------------------------------------- #
# TropyItem → JobItem mapping
# --------------------------------------------------------------------------- #


def items_to_job_items(
    items: list[TropyItem],
    *,
    output_dir: str,
) -> list:
    """Convert TropyItem objects to JobItem objects for the pipeline.

    Mirrors ``tropy_jsonld.photos_to_job_items`` but for live-read items.
    Uses the same ``page_stem`` naming and ``source`` dict shape so the
    pipeline treats them identically.

    ``TropyPhoto.path`` is the resolved absolute path from
    :func:`_resolve_photo_path`.
    """
    from .jobs import JobItem
    from .tropy_jsonld import page_stem

    result: list = []

    for item in items:
        for photo in item.photos:
            photo_name = Path(photo.path).name
            resolved = Path(photo.path)
            stem = page_stem(
                item.title,
                photo_name,
                photo.page,
                photo.mimetype,
                resolved,
            )
            is_pdf = (
                photo.mimetype == "application/pdf"
                or resolved.suffix.lower() == ".pdf"
            )
            parts = [photo_name]
            if is_pdf and photo.page is not None:
                parts.append(f"p.{photo.page + 1}")
            label = "  ".join(parts)

            result.append(
                JobItem(
                    path=str(photo.path),
                    page=photo.page if is_pdf else None,
                    output_stem=stem,
                    label=label,
                    source={
                        "origin": "tropy-live",
                        "tropy_item_id": item.item_id,
                        "item_title": item.title,
                        "photo_id": photo.photo_id,
                        "photo_path_rel": photo_name,
                        "checksum": photo.checksum,
                        "mimetype": photo.mimetype,
                        "orientation": photo.orientation,
                    },
                )
            )
    return result

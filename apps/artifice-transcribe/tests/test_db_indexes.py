# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Regression coverage for the five job_id/segment_id indexes added to
``db/models.py`` (TranscriptSegment.job_id, SpeakerMapping.job_id,
SpeakerEmbedding.job_id, SegmentEditVersion.segment_id,
SegmentEditVersion.job_id).

Nearly every read path filters by ``job_id`` (job detail, segment listing,
speaker mappings, exports, edit history); without an index these degrade to
full table scans as history grows. This module guards two things:

1. A freshly created database carries all five indexes, under the exact
   names SQLAlchemy's default ``ix_<table>_<column>`` convention assigns.
2. An *already existing* database file — one created before these indexes
   were declared, matching what a running deployment's SQLite file looks
   like today — gets the indexes retrofitted by the app's startup
   (``lifespan``) rather than silently staying un-indexed. This is not
   automatic: ``Base.metadata.create_all`` uses ``checkfirst=True``, which
   skips DDL entirely for a table that already exists on disk, so a newly
   declared ``index=True`` is never applied to that table by ``create_all``
   alone. Verified empirically (see PR description); ``lifespan`` now
   issues explicit ``CREATE INDEX IF NOT EXISTS`` statements after
   ``create_all`` to cover exactly this case.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from artifice_transcribe.db.models import Base
from sqlalchemy import ForeignKey, String
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# The five indexes this fix adds, named per SQLAlchemy's default
# ``ix_<table>_<column>`` convention — confirmed empirically against a
# freshly created database, not assumed.
_EXPECTED_INDEXES = {
    "ix_transcript_segments_job_id",
    "ix_speaker_mappings_job_id",
    "ix_speaker_embeddings_job_id",
    "ix_segment_edit_versions_segment_id",
    "ix_segment_edit_versions_job_id",
}


def _index_names(db_path: Path) -> set[str]:
    con = sqlite3.connect(str(db_path))
    try:
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    finally:
        con.close()
    return {row[0] for row in rows}


@pytest.mark.asyncio
async def test_fresh_database_has_all_five_indexes(tmp_path):
    """A brand-new database, built straight from ``Base.metadata``, carries
    all five indexes under the expected names."""
    db_path = tmp_path / "fresh.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()

    found = _index_names(db_path)
    missing = _EXPECTED_INDEXES - found
    assert not missing, f"missing indexes on a freshly created database: {missing}"


# ---------------------------------------------------------------------------
# Retrofit coverage: simulate a database created *before* these indexes were
# declared (an already-running deployment's SQLite file), then prove the
# app's startup path actually adds them.
# ---------------------------------------------------------------------------


class _OldBase(DeclarativeBase):
    """Mirrors the pre-fix schema: the same five tables/columns, but with no
    ``index=True`` on any of the columns this fix targets."""


class _OldJob(_OldBase):
    __tablename__ = "transcription_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)


class _OldSegment(_OldBase):
    __tablename__ = "transcript_segments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("transcription_jobs.id", ondelete="CASCADE"))


class _OldSpeakerMapping(_OldBase):
    __tablename__ = "speaker_mappings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("transcription_jobs.id", ondelete="CASCADE"))


class _OldSpeakerEmbedding(_OldBase):
    __tablename__ = "speaker_embeddings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(32))


class _OldSegmentEditVersion(_OldBase):
    __tablename__ = "segment_edit_versions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    segment_id: Mapped[str] = mapped_column(
        ForeignKey("transcript_segments.id", ondelete="CASCADE")
    )
    job_id: Mapped[str] = mapped_column(String(32))


@pytest.mark.asyncio
async def test_lifespan_retrofits_indexes_onto_pre_existing_database(tmp_path, monkeypatch):
    """A database created under the *old*, un-indexed schema gets the five
    indexes added when the app starts up, via ``lifespan``'s explicit
    ``CREATE INDEX IF NOT EXISTS`` statements — not just at ``create_all``
    time for brand-new tables."""
    db_path = tmp_path / "existing.db"

    # Phase 1: create the tables under the OLD (un-indexed) schema and
    # close the connection, simulating a database that predates this fix.
    old_engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    try:
        async with old_engine.begin() as conn:
            await conn.run_sync(_OldBase.metadata.create_all)
    finally:
        await old_engine.dispose()

    assert _index_names(db_path) == set(), "test setup should start with no indexes"

    # Phase 2: point the app's module-level engine at this pre-existing
    # database and run its startup lifespan, exactly as happens on a real
    # launch against an existing data directory.
    import artifice_transcribe.main as main_module

    new_engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setattr(main_module, "engine", new_engine)
    # ``settings.data_path`` is a read-only property returning this module
    # constant; patch the constant rather than the property itself.
    monkeypatch.setattr("artifice_transcribe.config._USER_DATA_PATH", tmp_path)

    try:
        async with main_module.lifespan(main_module.app):
            pass
    finally:
        await new_engine.dispose()

    found = _index_names(db_path)
    missing = _EXPECTED_INDEXES - found
    assert not missing, f"lifespan failed to retrofit indexes onto an existing database: {missing}"

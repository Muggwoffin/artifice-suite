from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class JobStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return uuid.uuid4().hex


class TranscriptionJob(Base):
    __tablename__ = "transcription_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    filename: Mapped[str] = mapped_column(String(512))
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.queued)
    progress_percentage: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    options: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string

    # Oral history metadata
    interviewee: Mapped[str | None] = mapped_column(String(256), nullable=True)
    interviewer: Mapped[str | None] = mapped_column(String(256), nullable=True)
    interview_date: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location: Mapped[str | None] = mapped_column(String(256), nullable=True)
    project_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    collection_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    access_restrictions: Mapped[str | None] = mapped_column(String(512), nullable=True)
    custom_vocabulary: Mapped[str | None] = mapped_column(Text, nullable=True)  # comma-separated

    segments: Mapped[list[TranscriptSegment]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    speakers: Mapped[list[SpeakerMapping]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(ForeignKey("transcription_jobs.id", ondelete="CASCADE"))
    speaker_label: Mapped[str] = mapped_column(String(32))
    start_time: Mapped[float] = mapped_column(Float)
    end_time: Mapped[float] = mapped_column(Float)
    text: Mapped[str] = mapped_column(Text)
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of tag strings

    job: Mapped[TranscriptionJob] = relationship(back_populates="segments")


class SpeakerMapping(Base):
    __tablename__ = "speaker_mappings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(ForeignKey("transcription_jobs.id", ondelete="CASCADE"))
    speaker_label: Mapped[str] = mapped_column(String(32))
    custom_name: Mapped[str] = mapped_column(String(128))

    job: Mapped[TranscriptionJob] = relationship(back_populates="speakers")


class PersistentDictionary(Base):
    """A single-row table holding a comma-separated global vocabulary list
    that is merged into every transcription job's hotwords."""

    __tablename__ = "persistent_dictionary"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    words: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class KnownSpeaker(Base):
    """An enrolled speaker whose voice embedding is stored for cross-session
    recognition."""

    __tablename__ = "known_speakers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(256))
    embedding: Mapped[bytes] = mapped_column(Text)  # numpy array pickled
    model_name: Mapped[str] = mapped_column(String(64), default="pyannote/embedding")
    dimension: Mapped[int] = mapped_column(default=512)
    sample_audio_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SpeakerEmbedding(Base):
    """Per-speaker centroid embedding for a specific job, used for cross-session
    speaker matching."""

    __tablename__ = "speaker_embeddings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String(32))
    speaker_label: Mapped[str] = mapped_column(String(32))
    embedding: Mapped[bytes] = mapped_column(Text)  # numpy array pickled
    model_name: Mapped[str] = mapped_column(String(64), default="pyannote/embedding")
    dimension: Mapped[int] = mapped_column(default=512)


class SegmentEditVersion(Base):
    __tablename__ = "segment_edit_versions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    segment_id: Mapped[str] = mapped_column(
        ForeignKey("transcript_segments.id", ondelete="CASCADE")
    )
    job_id: Mapped[str] = mapped_column(String(32))
    text_before: Mapped[str] = mapped_column(Text)
    text_after: Mapped[str] = mapped_column(Text)
    edited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class TranscriptionOptions(BaseModel):
    model_size: str = "base"
    language: str | None = None
    min_speakers: int | None = None
    max_speakers: int | None = None


class JobCreated(BaseModel):
    job_id: str
    status: JobStatus = JobStatus.queued
    message: str = "Transcription job accepted"


class JobStatusResponse(BaseModel):
    id: str
    filename: str
    status: JobStatus
    progress_percentage: float
    created_at: datetime
    completed_at: datetime | None = None
    error_message: str | None = None


class SegmentOut(BaseModel):
    speaker_label: str
    start_time: float
    end_time: float
    text: str


class TranscriptResponse(BaseModel):
    job_id: str
    segments: list[SegmentOut]


class SpeakerRename(BaseModel):
    speaker_label: str = Field(..., examples=["SPEAKER_00"])
    custom_name: str = Field(..., min_length=1, max_length=128, examples=["Dr. Smith"])


class SpeakerRenameRequest(BaseModel):
    speakers: list[SpeakerRename]


class SpeakerMappingOut(BaseModel):
    speaker_label: str
    custom_name: str


class SpeakerMapResponse(BaseModel):
    job_id: str
    speakers: list[SpeakerMappingOut]


class ExportFormat(str, Enum):
    json = "json"
    srt = "srt"
    vtt = "vtt"
    txt = "txt"

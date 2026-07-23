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
    interviewee: str | None = None
    interviewer: str | None = None
    interview_date: str | None = None
    location: str | None = None
    project_name: str | None = None
    collection_id: str | None = None
    access_restrictions: str | None = None
    custom_vocabulary: str | None = None


class SegmentOut(BaseModel):
    id: str
    speaker_label: str
    start_time: float
    end_time: float
    text: str
    tags: list[str] = []


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
    md = "md"
    pdf = "pdf"
    ohms = "ohms"
    tei = "tei"


class SegmentUpdate(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)


class SegmentUpdateRequest(BaseModel):
    updates: list[dict] = Field(..., examples=[[{"segment_id": "abc123", "text": "Hello world"}]])


class SegmentUpdateResponse(BaseModel):
    job_id: str
    updated_count: int


class JobMetadataUpdate(BaseModel):
    interviewee: str | None = None
    interviewer: str | None = None
    interview_date: str | None = None
    location: str | None = None
    project_name: str | None = None
    collection_id: str | None = None
    access_restrictions: str | None = None
    custom_vocabulary: str | None = None


class SegmentTagUpdate(BaseModel):
    tags: list[str]


class SearchQuery(BaseModel):
    q: str = Field(..., min_length=1, max_length=200)


class SearchMatch(BaseModel):
    job_id: str
    filename: str
    segment_id: str
    speaker_label: str
    text: str
    start_time: float
    end_time: float
    interviewee: str | None = None
    interviewer: str | None = None
    interview_date: str | None = None
    project_name: str | None = None


class SearchResults(BaseModel):
    results: list[SearchMatch]
    total: int


class EditVersionOut(BaseModel):
    id: str
    segment_id: str
    text_before: str
    text_after: str
    edited_at: datetime


class EditHistoryResponse(BaseModel):
    segment_id: str
    versions: list[EditVersionOut]


class SegmentSplitRequest(BaseModel):
    split_position: int = Field(..., ge=0, description="Character index to split at")


class SegmentSplitResponse(BaseModel):
    segments: list[SegmentOut]


class SegmentMergeResponse(BaseModel):
    segment: SegmentOut
    deleted_segment_id: str

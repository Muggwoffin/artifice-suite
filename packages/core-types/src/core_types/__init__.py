"""Shared data schemas for the Artifice Suite.

Each app currently defines its own job/progress types (e.g.
``artifice_draft``'s ``PipelineProgress``, ``artifice_transcribe``'s
``TranscriptionJob``). These schemas are a common starting point for
whichever of those an app chooses to adopt; nothing in the suite depends on
this package yet.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class ProcessingStatus(str, Enum):
    """Lifecycle of a long-running pipeline job, shared across apps."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class PipelineProgress(BaseModel):
    """A single progress update from a running pipeline stage."""

    status: ProcessingStatus = ProcessingStatus.RUNNING
    percentage: float
    message: str


__all__ = ["ProcessingStatus", "PipelineProgress"]

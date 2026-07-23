from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import JobStatus, SpeakerMapping, TranscriptionJob, TranscriptSegment
from app.db.session import async_session, get_db
from app.schemas.transcription import (
    ExportFormat,
    JobCreated,
    JobStatusResponse,
    SegmentOut,
    SpeakerMapResponse,
    SpeakerMappingOut,
    SpeakerRenameRequest,
    TranscriptResponse,
    TranscriptionOptions,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["transcription"])

# Module-level engine singleton (lazy init)
_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        from app.services.transcription import TranscriptionEngine

        _engine = TranscriptionEngine(
            model_size=settings.whisper_model,
            device=settings.device,
            hf_token=settings.hf_token,
        )
    return _engine


# ── Background worker ────────────────────────────────────────────────────────


async def _run_transcription(
    job_id: str,
    audio_path: str,
    options: TranscriptionOptions,
) -> None:
    """Background task: run transcription engine, update DB on completion/failure."""
    async with async_session() as db:
        try:
            # Mark processing
            job = await db.get(TranscriptionJob, job_id)
            if job is None:
                return
            job.status = JobStatus.processing
            job.progress_percentage = 5.0
            await db.commit()

            def _progress(pct: float) -> None:
                logger.debug("Job %s progress: %.0f%%", job_id, pct * 100)

            engine = _get_engine()
            segments = await asyncio.to_thread(
                engine.transcribe,
                audio_path,
                language=options.language,
                min_speakers=options.min_speakers,
                max_speakers=options.max_speakers,
                progress_callback=_progress,
            )

            # Persist segments
            from app.db.models import TranscriptSegment as TS

            db_segs = [
                TS(
                    job_id=job_id,
                    speaker_label=seg.speaker,
                    start_time=seg.start,
                    end_time=seg.end,
                    text=seg.text,
                )
                for seg in segments
            ]
            db.add_all(db_segs)

            # Build speaker mappings for any new speakers
            seen = []
            for seg in segments:
                if seg.speaker not in seen:
                    seen.append(seg.speaker)

            existing = (
                await db.execute(
                    select(SpeakerMapping).where(SpeakerMapping.job_id == job_id)
                )
            ).scalars().all()
            existing_labels = {m.speaker_label for m in existing}

            new_mappings = [
                SpeakerMapping(job_id=job_id, speaker_label=label, custom_name=label)
                for label in seen
                if label not in existing_labels
            ]
            db.add_all(new_mappings)

            # Finalize
            job.status = JobStatus.completed
            job.progress_percentage = 100.0
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
            logger.info("Job %s completed with %d segments", job_id, len(segments))

        except Exception as exc:
            logger.exception("Job %s failed", job_id)
            job = await db.get(TranscriptionJob, job_id)
            if job:
                job.status = JobStatus.failed
                job.error_message = str(exc)
                job.completed_at = datetime.now(timezone.utc)
                await db.commit()

        finally:
            # Free VRAM after every job
            engine = _get_engine()
            engine.unload()


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/transcribe", response_model=JobCreated, status_code=202)
async def create_transcription(
    file: UploadFile,
    model_size: str = "base",
    language: str | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
) -> JobCreated:
    # Validate file size
    contents = await file.read()
    if len(contents) > settings.max_upload_size:
        raise HTTPException(413, "File too large")

    # Persist upload
    job = TranscriptionJob(
        filename=file.filename or "unknown",
        status=JobStatus.queued,
        options=json.dumps(
            {
                "model_size": model_size,
                "language": language,
                "min_speakers": min_speakers,
                "max_speakers": max_speakers,
            }
        ),
    )
    db.add(job)
    await db.commit()

    # Save audio to disk
    audio_path = settings.upload_path / f"{job.id}_{file.filename}"
    audio_path.write_bytes(contents)

    # Enqueue background work
    opts = TranscriptionOptions(
        model_size=model_size,
        language=language,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
    )
    background_tasks.add_task(_run_transcription, job.id, str(audio_path), opts)

    return JobCreated(job_id=job.id)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str, db: AsyncSession = Depends(get_db)) -> TranscriptionJob:
    job = await db.get(TranscriptionJob, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job


@router.get("/jobs/{job_id}/transcript", response_model=TranscriptResponse)
async def get_transcript(job_id: str, db: AsyncSession = Depends(get_db)) -> TranscriptResponse:
    job = await db.get(TranscriptionJob, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.status != JobStatus.completed:
        raise HTTPException(409, f"Job is {job.status.value}, not completed")

    segs = (
        await db.execute(
            select(TranscriptSegment)
            .where(TranscriptSegment.job_id == job_id)
            .order_by(TranscriptSegment.start_time)
        )
    ).scalars().all()

    name_map_row = (
        await db.execute(
            select(SpeakerMapping).where(SpeakerMapping.job_id == job_id)
        )
    ).scalars().all()
    name_map = {m.speaker_label: m.custom_name for m in name_map_row}

    return TranscriptResponse(
        job_id=job_id,
        segments=[
            SegmentOut(
                speaker_label=name_map.get(s.speaker_label, s.speaker_label),
                start_time=s.start_time,
                end_time=s.end_time,
                text=s.text,
            )
            for s in segs
        ],
    )


@router.patch("/jobs/{job_id}/speakers", response_model=SpeakerMapResponse)
async def rename_speakers(
    job_id: str,
    body: SpeakerRenameRequest,
    db: AsyncSession = Depends(get_db),
) -> SpeakerMapResponse:
    job = await db.get(TranscriptionJob, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")

    for rename in body.speakers:
        result = await db.execute(
            select(SpeakerMapping).where(
                SpeakerMapping.job_id == job_id,
                SpeakerMapping.speaker_label == rename.speaker_label,
            )
        )
        mapping = result.scalar_one_or_none()
        if mapping:
            mapping.custom_name = rename.custom_name
        else:
            db.add(
                SpeakerMapping(
                    job_id=job_id,
                    speaker_label=rename.speaker_label,
                    custom_name=rename.custom_name,
                )
            )

    await db.commit()

    all_mappings = (
        await db.execute(
            select(SpeakerMapping).where(SpeakerMapping.job_id == job_id)
        )
    ).scalars().all()

    return SpeakerMapResponse(
        job_id=job_id,
        speakers=[
            SpeakerMappingOut(speaker_label=m.speaker_label, custom_name=m.custom_name)
            for m in all_mappings
        ],
    )


@router.get("/jobs/{job_id}/export")
async def export_transcript(
    job_id: str,
    format: ExportFormat = ExportFormat.json,
    db: AsyncSession = Depends(get_db),
) -> Response:
    job = await db.get(TranscriptionJob, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.status != JobStatus.completed:
        raise HTTPException(409, f"Job is {job.status.value}, not completed")

    from app.services import exports

    content_type_map = {
        ExportFormat.json: "application/json",
        ExportFormat.srt: "text/srt",
        ExportFormat.vtt: "text/vtt",
        ExportFormat.txt: "text/plain",
    }
    exporters = {
        ExportFormat.json: exports.export_json,
        ExportFormat.srt: exports.export_srt,
        ExportFormat.vtt: exports.export_vtt,
        ExportFormat.txt: exports.export_txt,
    }

    body = await exporters[format](db, job_id)
    return Response(
        content=body,
        media_type=content_type_map[format],
        headers={
            "Content-Disposition": f'attachment; filename="transcript_{job_id}.{format.value}"'
        },
    )


@router.delete("/jobs/{job_id}", status_code=204)
async def delete_job(job_id: str, db: AsyncSession = Depends(get_db)) -> None:
    job = await db.get(TranscriptionJob, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")

    # Remove audio file(s) from disk
    upload_dir = settings.upload_path
    for p in upload_dir.glob(f"{job_id}_*"):
        p.unlink(missing_ok=True)

    await db.delete(job)
    await db.commit()

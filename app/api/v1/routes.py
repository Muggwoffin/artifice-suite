from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import (
    JobStatus,
    SegmentEditVersion,
    SpeakerMapping,
    TranscriptionJob,
    TranscriptSegment,
)
from app.db.session import async_session, get_db
from app.schemas.transcription import (
    EditHistoryResponse,
    EditVersionOut,
    ExportFormat,
    JobCreated,
    JobMetadataUpdate,
    JobStatusResponse,
    SearchMatch,
    SearchResults,
    SegmentMergeResponse,
    SegmentOut,
    SegmentSplitRequest,
    SegmentSplitResponse,
    SegmentTagUpdate,
    SegmentUpdateRequest,
    SegmentUpdateResponse,
    SpeakerMappingOut,
    SpeakerMapResponse,
    SpeakerRenameRequest,
    TranscriptionOptions,
    TranscriptResponse,
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
            job = await db.get(TranscriptionJob, job_id)
            if job is None:
                return
            job.status = JobStatus.processing
            job.progress_percentage = 5.0
            await db.commit()

            def _progress(pct: float) -> None:
                logger.debug("Job %s progress: %.0f%%", job_id, pct * 100)

            engine = _get_engine()
            custom_vocab = None
            if job.custom_vocabulary:
                custom_vocab = job.custom_vocabulary
            segments = await asyncio.to_thread(
                engine.transcribe,
                audio_path,
                language=options.language,
                min_speakers=options.min_speakers,
                max_speakers=options.max_speakers,
                progress_callback=_progress,
                custom_vocabulary=custom_vocab,
            )

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

            seen = []
            for seg in segments:
                if seg.speaker not in seen:
                    seen.append(seg.speaker)

            existing = (
                (await db.execute(select(SpeakerMapping).where(SpeakerMapping.job_id == job_id)))
                .scalars()
                .all()
            )
            existing_labels = {m.speaker_label for m in existing}

            new_mappings = [
                SpeakerMapping(job_id=job_id, speaker_label=label, custom_name=label)
                for label in seen
                if label not in existing_labels
            ]
            db.add_all(new_mappings)

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
            engine = _get_engine()
            engine.unload()


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/config")
async def get_config():
    return {
        "whisper_model": settings.whisper_model,
        "device": settings.device,
    }


@router.get("/health/detailed")
async def health_detailed():
    """Full health check: model load state, GPU info, database connectivity."""
    engine = _get_engine()
    engine_status = engine.health_check()

    db_ok = True
    try:
        async with async_session() as db:
            await db.execute(select(TranscriptionJob).limit(1))
    except Exception:
        db_ok = False

    return {
        "status": "ok" if db_ok else "degraded",
        "engine": engine_status,
        "database": {"status": "ok" if db_ok else "error"},
    }


@router.post("/health/preload")
async def health_preload():
    """Load all models into memory. Returns success or error details."""
    engine = _get_engine()
    result = await asyncio.to_thread(engine.preload)
    return result


@router.post("/transcribe", response_model=JobCreated, status_code=202)
async def create_transcription(
    file: UploadFile,
    language: str | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
) -> JobCreated:
    contents = await file.read()
    if len(contents) > settings.max_upload_size:
        raise HTTPException(413, "File too large")

    job = TranscriptionJob(
        filename=file.filename or "unknown",
        status=JobStatus.queued,
        options=json.dumps(
            {
                "language": language,
                "min_speakers": min_speakers,
                "max_speakers": max_speakers,
            }
        ),
    )
    db.add(job)
    await db.commit()

    audio_path = settings.upload_path / f"{job.id}_{file.filename}"
    audio_path.write_bytes(contents)

    opts = TranscriptionOptions(
        language=language,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
    )
    background_tasks.add_task(_run_transcription, job.id, str(audio_path), opts)

    return JobCreated(job_id=job.id)


@router.post("/transcribe/batch", status_code=202)
async def create_batch_transcription(
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Upload multiple audio files for batch transcription."""

    upload_dir = settings.upload_path
    audio_exts = ("*.wav", "*.mp3", "*.m4a", "*.ogg", "*.flac", "*.mp4", "*.m4v")
    files = []
    for ext in audio_exts:
        files.extend(upload_dir.glob(ext))

    queued = 0
    for fp in files:
        job = TranscriptionJob(
            filename=fp.name,
            status=JobStatus.queued,
            options=json.dumps({"language": None, "min_speakers": None, "max_speakers": None}),
        )
        db.add(job)
        await db.commit()
        opts = TranscriptionOptions(language=None, min_speakers=None, max_speakers=None)
        background_tasks.add_task(_run_transcription, job.id, str(fp), opts)
        queued += 1

    return {"queued": queued, "message": f"Queued {queued} file(s) for transcription"}


@router.get("/jobs", response_model=list[JobStatusResponse])
async def list_jobs(db: AsyncSession = Depends(get_db)) -> list[TranscriptionJob]:
    jobs = (
        (await db.execute(select(TranscriptionJob).order_by(TranscriptionJob.created_at.desc())))
        .scalars()
        .all()
    )
    return list(jobs)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str, db: AsyncSession = Depends(get_db)) -> TranscriptionJob:
    job = await db.get(TranscriptionJob, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job


@router.get("/jobs/{job_id}/audio")
async def get_job_audio(job_id: str, db: AsyncSession = Depends(get_db)) -> FileResponse:
    job = await db.get(TranscriptionJob, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")

    matches = list(settings.upload_path.glob(f"{job_id}_*"))
    if not matches:
        raise HTTPException(404, "Audio file not found")

    return FileResponse(matches[0], filename=job.filename)


@router.get("/jobs/{job_id}/transcript", response_model=TranscriptResponse)
async def get_transcript(job_id: str, db: AsyncSession = Depends(get_db)) -> TranscriptResponse:
    job = await db.get(TranscriptionJob, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.status != JobStatus.completed:
        raise HTTPException(409, f"Job is {job.status.value}, not completed")

    segs = (
        (
            await db.execute(
                select(TranscriptSegment)
                .where(TranscriptSegment.job_id == job_id)
                .order_by(TranscriptSegment.start_time)
            )
        )
        .scalars()
        .all()
    )

    name_map_row = (
        (await db.execute(select(SpeakerMapping).where(SpeakerMapping.job_id == job_id)))
        .scalars()
        .all()
    )
    name_map = {m.speaker_label: m.custom_name for m in name_map_row}

    def _parse_tags(seg: TranscriptSegment) -> list[str]:
        if seg.tags:
            try:
                return json.loads(seg.tags)
            except (json.JSONDecodeError, TypeError):
                pass
        return []

    return TranscriptResponse(
        job_id=job_id,
        segments=[
            SegmentOut(
                id=s.id,
                speaker_label=name_map.get(s.speaker_label, s.speaker_label),
                start_time=s.start_time,
                end_time=s.end_time,
                text=s.text,
                tags=_parse_tags(s),
            )
            for s in segs
        ],
    )


@router.patch("/jobs/{job_id}/metadata", response_model=JobStatusResponse)
async def update_job_metadata(
    job_id: str,
    body: JobMetadataUpdate,
    db: AsyncSession = Depends(get_db),
) -> TranscriptionJob:
    job = await db.get(TranscriptionJob, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(job, field, value)

    await db.commit()
    return job


@router.patch("/jobs/{job_id}/segments", response_model=SegmentUpdateResponse)
async def update_segments(
    job_id: str,
    body: SegmentUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> SegmentUpdateResponse:
    job = await db.get(TranscriptionJob, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.status != JobStatus.completed:
        raise HTTPException(409, f"Job is {job.status.value}, not completed")

    from app.db.models import TranscriptSegment as TS

    updated = 0
    for item in body.updates:
        seg_id = item.get("segment_id")
        text = item.get("text")
        if not seg_id or text is None:
            continue
        seg = await db.get(TS, seg_id)
        if seg and seg.job_id == job_id and seg.text != text:
            db.add(
                SegmentEditVersion(
                    segment_id=seg.id,
                    job_id=job_id,
                    text_before=seg.text,
                    text_after=text,
                )
            )
            seg.text = text
            updated += 1

    await db.commit()
    return SegmentUpdateResponse(job_id=job_id, updated_count=updated)


@router.get("/jobs/{job_id}/segments/{segment_id}/history", response_model=EditHistoryResponse)
async def get_segment_history(
    job_id: str,
    segment_id: str,
    db: AsyncSession = Depends(get_db),
) -> EditHistoryResponse:
    seg = await db.get(TranscriptSegment, segment_id)
    if seg is None or seg.job_id != job_id:
        raise HTTPException(404, "Segment not found")

    versions = (
        (
            await db.execute(
                select(SegmentEditVersion)
                .where(SegmentEditVersion.segment_id == segment_id)
                .order_by(SegmentEditVersion.edited_at.desc())
            )
        )
        .scalars()
        .all()
    )

    return EditHistoryResponse(
        segment_id=segment_id,
        versions=[
            EditVersionOut(
                id=v.id,
                segment_id=v.segment_id,
                text_before=v.text_before,
                text_after=v.text_after,
                edited_at=v.edited_at,
            )
            for v in versions
        ],
    )


@router.patch("/jobs/{job_id}/segments/{segment_id}/tags")
async def update_segment_tags(
    job_id: str,
    segment_id: str,
    body: SegmentTagUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    seg = await db.get(TranscriptSegment, segment_id)
    if seg is None or seg.job_id != job_id:
        raise HTTPException(404, "Segment not found")

    seg.tags = json.dumps(body.tags)
    await db.commit()
    return {"tags": body.tags}


@router.post("/jobs/{job_id}/segments/{segment_id}/split", response_model=SegmentSplitResponse)
async def split_segment(
    job_id: str,
    segment_id: str,
    body: SegmentSplitRequest,
    db: AsyncSession = Depends(get_db),
) -> SegmentSplitResponse:
    seg = await db.get(TranscriptSegment, segment_id)
    if seg is None or seg.job_id != job_id:
        raise HTTPException(404, "Segment not found")

    text = seg.text
    pos = body.split_position
    if pos <= 0 or pos >= len(text):
        raise HTTPException(400, "Split position must be inside the text")

    first_text = text[:pos].strip()
    second_text = text[pos:].strip()
    if not first_text or not second_text:
        raise HTTPException(400, "Split would create an empty segment")

    split_ratio = pos / len(text)
    orig_duration = seg.end_time - seg.start_time
    mid_time = seg.start_time + orig_duration * split_ratio

    seg.text = first_text
    old_end = seg.end_time
    seg.end_time = mid_time

    new_seg = TranscriptSegment(
        job_id=job_id,
        speaker_label=seg.speaker_label,
        start_time=mid_time,
        end_time=old_end,
        text=second_text,
    )
    db.add(new_seg)
    await db.commit()

    segs = (
        (
            await db.execute(
                select(TranscriptSegment)
                .where(TranscriptSegment.job_id == job_id)
                .order_by(TranscriptSegment.start_time)
            )
        )
        .scalars()
        .all()
    )

    name_map_row = (
        (await db.execute(select(SpeakerMapping).where(SpeakerMapping.job_id == job_id)))
        .scalars()
        .all()
    )
    name_map = {m.speaker_label: m.custom_name for m in name_map_row}

    def _parse_tags(s: TranscriptSegment) -> list[str]:
        if s.tags:
            try:
                return json.loads(s.tags)
            except (json.JSONDecodeError, TypeError):
                pass
        return []

    return SegmentSplitResponse(
        segments=[
            SegmentOut(
                id=s.id,
                speaker_label=name_map.get(s.speaker_label, s.speaker_label),
                start_time=s.start_time,
                end_time=s.end_time,
                text=s.text,
                tags=_parse_tags(s),
            )
            for s in segs
        ],
    )


@router.post("/jobs/{job_id}/segments/{segment_id}/merge", response_model=SegmentMergeResponse)
async def merge_segments(
    job_id: str,
    segment_id: str,
    db: AsyncSession = Depends(get_db),
) -> SegmentMergeResponse:
    seg = await db.get(TranscriptSegment, segment_id)
    if seg is None or seg.job_id != job_id:
        raise HTTPException(404, "Segment not found")

    next_seg = (
        (
            await db.execute(
                select(TranscriptSegment)
                .where(
                    TranscriptSegment.job_id == job_id,
                    TranscriptSegment.start_time > seg.start_time,
                )
                .order_by(TranscriptSegment.start_time)
                .limit(1)
            )
        )
        .scalars()
        .first()
    )

    if next_seg is None:
        raise HTTPException(400, "No next segment to merge with")

    seg.text = seg.text.rstrip(" ") + " " + next_seg.text.lstrip(" ")
    seg.end_time = next_seg.end_time
    deleted_id = next_seg.id
    await db.delete(next_seg)
    await db.commit()

    name_map_row = (
        (await db.execute(select(SpeakerMapping).where(SpeakerMapping.job_id == job_id)))
        .scalars()
        .all()
    )
    name_map = {m.speaker_label: m.custom_name for m in name_map_row}

    def _parse_tags(s: TranscriptSegment) -> list[str]:
        if s.tags:
            try:
                return json.loads(s.tags)
            except (json.JSONDecodeError, TypeError):
                pass
        return []

    return SegmentMergeResponse(
        segment=SegmentOut(
            id=seg.id,
            speaker_label=name_map.get(seg.speaker_label, seg.speaker_label),
            start_time=seg.start_time,
            end_time=seg.end_time,
            text=seg.text,
            tags=_parse_tags(seg),
        ),
        deleted_segment_id=deleted_id,
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
        (await db.execute(select(SpeakerMapping).where(SpeakerMapping.job_id == job_id)))
        .scalars()
        .all()
    )

    return SpeakerMapResponse(
        job_id=job_id,
        speakers=[
            SpeakerMappingOut(speaker_label=m.speaker_label, custom_name=m.custom_name)
            for m in all_mappings
        ],
    )


@router.get("/search", response_model=SearchResults)
async def search_transcripts(
    q: str,
    db: AsyncSession = Depends(get_db),
) -> SearchResults:
    """Full-text search across all completed transcripts."""
    if not q.strip():
        return SearchResults(results=[], total=0)

    search_term = f"%{q.strip()}%"

    segs = (
        (
            await db.execute(
                select(TranscriptSegment)
                .join(TranscriptionJob)
                .where(
                    TranscriptionJob.status == JobStatus.completed,
                    TranscriptSegment.text.ilike(search_term),
                )
                .order_by(TranscriptSegment.start_time)
                .limit(100)
            )
        )
        .scalars()
        .all()
    )

    results = []
    for seg in segs:
        job = await db.get(TranscriptionJob, seg.job_id)
        if job is None:
            continue
        results.append(
            SearchMatch(
                job_id=seg.job_id,
                filename=job.filename,
                segment_id=seg.id,
                speaker_label=seg.speaker_label,
                text=seg.text,
                start_time=seg.start_time,
                end_time=seg.end_time,
                interviewee=job.interviewee,
                interviewer=job.interviewer,
                interview_date=job.interview_date,
                project_name=job.project_name,
            )
        )

    return SearchResults(results=results, total=len(results))


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
        ExportFormat.md: "text/markdown",
        ExportFormat.pdf: "application/pdf",
        ExportFormat.ohms: "application/xml",
        ExportFormat.tei: "application/xml",
    }
    exporters = {
        ExportFormat.json: exports.export_json,
        ExportFormat.srt: exports.export_srt,
        ExportFormat.vtt: exports.export_vtt,
        ExportFormat.txt: exports.export_txt,
        ExportFormat.md: exports.export_md,
        ExportFormat.pdf: exports.export_pdf,
        ExportFormat.ohms: exports.export_ohms,
        ExportFormat.tei: exports.export_tei,
    }

    body = await exporters[format](db, job_id)
    is_binary = format in (ExportFormat.pdf,)
    content = body if is_binary else body.encode("utf-8") if isinstance(body, str) else body
    return Response(
        content=content,
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

    upload_dir = settings.upload_path
    for p in upload_dir.glob(f"{job_id}_*"):
        p.unlink(missing_ok=True)

    await db.delete(job)
    await db.commit()

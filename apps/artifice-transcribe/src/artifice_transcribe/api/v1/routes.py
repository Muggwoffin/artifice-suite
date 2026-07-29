from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from artifice_transcribe.config import settings
from artifice_transcribe.db.models import (
    JobStatus,
    KnownSpeaker,
    LegacyEmbeddingError,
    PersistentDictionary,
    SegmentEditVersion,
    SpeakerEmbedding,
    SpeakerMapping,
    TranscriptionJob,
    TranscriptSegment,
    _is_legacy_pickle_blob,
    pack_embedding,
    unpack_embedding,
)
from artifice_transcribe.db.session import async_session, get_db
from artifice_transcribe.schemas.transcription import (
    DictionaryResponse,
    DictionaryUpdate,
    EditHistoryResponse,
    EditVersionOut,
    EnrollFromJobRequest,
    ExportFormat,
    InferenceConfigRequest,
    InferenceGenerateRequest,
    InferenceModelsRequest,
    InferenceTestRequest,
    JobCreated,
    JobMetadataUpdate,
    JobStatusResponse,
    KnownSpeakerList,
    KnownSpeakerOut,
    ModelConfigRequest,
    ModelConfigResponse,
    SearchMatch,
    SearchResults,
    SegmentMergeResponse,
    SegmentOut,
    SegmentSplitRequest,
    SegmentSplitResponse,
    SegmentTagUpdate,
    SegmentUpdateRequest,
    SegmentUpdateResponse,
    SpeakerEmbeddingOut,
    SpeakerEnrollResponse,
    SpeakerMappingOut,
    SpeakerMapResponse,
    SpeakerMatchResponse,
    SpeakerMatchResult,
    SpeakerRenameRequest,
    TranscriptionOptions,
    TranscriptResponse,
)
from artifice_transcribe.services.inference import (
    InferenceEngine,
    get_available_models,
)
from artifice_transcribe.services.inference import (
    test_connection as test_inf_conn,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["transcription"])

# ── Path safety ──────────────────────────────────────────────────────────────


def _sanitise_path_component(raw: str) -> str:
    """Return a safe single-component filename from *raw*.

    Rejects components that are empty, ``"."``, or ``".."`` after
    stripping — ``Path("..").name`` returns ``".."``, so ``.name``
    alone is not sufficient.
    
    Backslashes are treated as separators (Windows path support) so that
    ``..\\\\..\\\\windows\\\\system32`` collapses to ``system32`` even on
    POSIX where ``Path.name`` would return the whole string.
    """
    cleaned = Path(raw.replace("\\", "/")).name
    if cleaned in ("", ".", ".."):
        raise HTTPException(400, f"Invalid path component: {raw!r}")
    return cleaned


def _assert_contained(path: Path, container: Path) -> None:
    """Raise HTTP 400 if *path* resolves outside *container*."""
    resolved = path.resolve()
    base = container.resolve()
    if not (base in resolved.parents or resolved == base):
        raise HTTPException(400, "Path traversal detected")


# ── Model endpoints ──────────────────────────────────────────────────────────
#
# Deliberately NOT loopback-only.  Academics on a university network reach
# centrally-served models from a personal machine, so a private-network address
# is a first-class case rather than an escape hatch.  "Local-first" means the
# software never *requires* a remote service, not that it refuses one the user
# chose.
#
# Still enforced: http/https only; link-local refused outright, which is what
# keeps cloud metadata endpoints (169.254.169.254) unreachable; and public
# addresses gated behind an explicit opt-in so a mistyped or injected hostname
# cannot quietly ship prompts to the open internet.
#
# Kept deliberately identical to artifice-graph's copy.  Both should collapse
# into model_harness.EndpointPolicy in Phase 3 — this is the rule the harness
# exists to own, and duplicating it twice is the interim cost of the harness
# not being real yet.
_ALWAYS_ALLOWED_HOSTS: frozenset[str] = frozenset(
    h.lower()
    for h in [
        "localhost",
        "host.docker.internal",
        os.environ.get("WSL_HOST_IP", "172.21.176.1"),
    ]
    if h
)

_ALLOW_PUBLIC_MODELS = os.environ.get("ARTIFICE_ALLOW_PUBLIC_MODELS", "").strip().lower() in (
    "1",
    "true",
    "yes",
)


def _classify_host(host: str) -> tuple[bool, str]:
    """Return ``(permitted, reason)`` for a URL host.

    Every address a name resolves to is checked, because a name resolving to
    one permitted and one public address is not permitted.  Resolution here and
    connection later is a time-of-check gap; closing it needs the connection
    pinned to the validated address, which belongs in the harness.
    """
    if host in _ALWAYS_ALLOWED_HOSTS:
        return True, "explicitly allowed host"

    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False, f"host {host!r} could not be resolved"

    addresses = {ipaddress.ip_address(info[4][0]) for info in infos}
    if not addresses:
        return False, f"host {host!r} resolved to no addresses"

    for addr in sorted(addresses, key=str):
        if addr.is_link_local:
            return False, (
                f"host {host!r} resolves to the link-local address {addr}, "
                f"which is never permitted"
            )

    if all(addr.is_loopback or addr.is_private for addr in addresses):
        return True, "loopback or private-network address"

    if _ALLOW_PUBLIC_MODELS:
        return True, "public address, permitted by ARTIFICE_ALLOW_PUBLIC_MODELS"

    public = sorted(str(a) for a in addresses if not (a.is_loopback or a.is_private))
    return False, (
        f"host {host!r} resolves to the public address(es) {public}. "
        f"Set ARTIFICE_ALLOW_PUBLIC_MODELS=1 to permit endpoints outside your "
        f"own network."
    )


def _validate_base_url(raw: str, field_name: str) -> str:
    """Return *raw* after checking its scheme and host. Fails closed, loudly."""
    try:
        parsed = urlparse(raw)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name}: {raw!r} is not a valid URL",
        ) from None

    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=400,
            detail=f"{field_name}: scheme must be http or https, got {parsed.scheme!r}",
        )

    host = (parsed.hostname or "").lower()
    if not host:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name}: {raw!r} has no host",
        )

    permitted, reason = _classify_host(host)
    if not permitted:
        raise HTTPException(status_code=400, detail=f"{field_name}: {reason}")
    return raw


# ── Inference configuration persistence helper ───────────────────────────────
# Uses platformdirs to resolve a per-user data directory, so the config file
# survives frozen bundles (.exe/.dmg) where CWD can be anywhere.
_LEGACY_INFERENCE_CONFIG = Path("./data/inference_config.json").resolve()
_LEGACY_PT_INFERENCE_CONFIG = Path("./data/pt-inference-config.json").resolve()
_INFERENCE_CONFIG_FILE = settings.data_path / "inference_config.json"


def _migrate_legacy_inference_config() -> None:
    """Move legacy ``./data/inference_config.json`` to the platform data dir."""
    if _INFERENCE_CONFIG_FILE.exists():
        if _LEGACY_INFERENCE_CONFIG.exists():
            logger.info(
                "Legacy inference config found at %s but config already exists at %s. "
                "Using the existing config.",
                _LEGACY_INFERENCE_CONFIG, _INFERENCE_CONFIG_FILE,
            )
        return
    if _LEGACY_INFERENCE_CONFIG.exists():
        logger.info(
            "Migrating legacy inference config from %s to %s",
            _LEGACY_INFERENCE_CONFIG, _INFERENCE_CONFIG_FILE,
        )
        _INFERENCE_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.move(str(_LEGACY_INFERENCE_CONFIG), str(_INFERENCE_CONFIG_FILE))
        logger.info("Migration complete — inference config is now at %s", _INFERENCE_CONFIG_FILE)


def _load_inference_config() -> dict:
    _migrate_legacy_inference_config()
    if _INFERENCE_CONFIG_FILE.exists():
        try:
            return json.loads(_INFERENCE_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "base_url": "http://localhost:11434/v1",
        "api_key": "not-needed",
        "model_name": "",
        "vision_enabled": False,
    }


def _save_inference_config(cfg: dict) -> None:
    _INFERENCE_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Created 0600 rather than chmod'ed afterwards, so the file is never
    # world-readable even briefly.
    #
    # POSIX only. Windows ignores the mode argument and reports st_mode 0o666,
    # so on Windows this file — which holds an API key — is NOT protected.
    # Restricting it there needs an explicit ACL (icacls or pywin32). Recorded
    # in IMPLEMENTATION_PLAN.md; found by the cross-platform CI leg.
    fd = os.open(_INFERENCE_CONFIG_FILE, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


# Module-level engine singleton (lazy init)
_engine = None


async def _reload_engine_with_new_model(new_model: str):
    """Reload the transcription engine with a new Whisper model while preserving the settings."""
    global _engine
    logger.info("Reloading engine with new Whisper model: %s", new_model)

    old_engine = _engine
    if old_engine:
        old_engine.unload()

    from artifice_transcribe.services.transcription import TranscriptionEngine

    _engine = TranscriptionEngine(
        model_size=settings.whisper_model,
        device=settings.device,
        hf_token=settings.hf_token,
    )
    logger.info("Engine reloaded successfully with model: %s", new_model)


def _get_engine():
    global _engine
    if _engine is None:
        from artifice_transcribe.services.transcription import TranscriptionEngine

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

            # Merge global persistent dictionary with per-job vocabulary
            hotwords = None
            dict_row = (await db.execute(select(PersistentDictionary).limit(1))).scalars().first()
            if dict_row and dict_row.words:
                hotwords = dict_row.words
            custom_vocab = job.custom_vocabulary or None

            result = await asyncio.to_thread(
                engine.transcribe,
                audio_path,
                language=options.language,
                min_speakers=options.min_speakers,
                max_speakers=options.max_speakers,
                progress_callback=_progress,
                custom_vocabulary=custom_vocab,
                hotwords=hotwords,
            )
            segments = result.segments
            speaker_embeddings = result.speaker_embeddings

            from artifice_transcribe.db.models import TranscriptSegment as TS

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

            # Store speaker embeddings for cross-session matching
            if speaker_embeddings:
                db_embeddings = [
                    SpeakerEmbedding(
                        job_id=job_id,
                        speaker_label=label,
                        embedding=pack_embedding(emb),
                        model_name="pyannote/embedding",
                        dimension=len(emb),
                    )
                    for label, emb in speaker_embeddings.items()
                ]
                db.add_all(db_embeddings)

            job.status = JobStatus.completed
            job.progress_percentage = 100.0
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
            logger.info("Job %s completed with %d segments", job_id, len(segments))

            # Auto-match speakers against known speakers
            try:
                await _auto_match_speakers(job_id, db)
            except Exception:
                logger.exception("Auto-match failed for job %s", job_id)

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


async def _auto_match_speakers(job_id: str, db: AsyncSession) -> None:
    """Compare this job's speaker embeddings against known speakers and
    auto-rename mappings when a match exceeds the confidence threshold."""
    embeddings = (
        (await db.execute(select(SpeakerEmbedding).where(SpeakerEmbedding.job_id == job_id)))
        .scalars()
        .all()
    )
    if not embeddings:
        return

    known = (await db.execute(select(KnownSpeaker))).scalars().all()
    if not known:
        return

    import numpy as np

    def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
        denom = np.linalg.norm(a) * np.linalg.norm(b)
        if denom == 0:
            return 0.0
        return float(np.dot(a, b) / denom)

    THRESHOLD = 0.65

    for emb in embeddings:
        emb_vec = unpack_embedding(emb.embedding, emb.dimension)

        best_name = None
        best_score = -1.0

        for known_spk in known:
            try:
                known_vec = unpack_embedding(known_spk.embedding, known_spk.dimension)
            except LegacyEmbeddingError:
                logger.warning(
                    "Skipping known speaker '%s' (id=%s): embedding predates "
                    "format change, must be re-enrolled",
                    known_spk.name,
                    known_spk.id,
                )
                continue
            score = _cosine_sim(emb_vec, known_vec)
            if score > best_score:
                best_score = score
                best_name = known_spk.name

        if best_score >= THRESHOLD and best_name:
            mapping = (
                (
                    await db.execute(
                        select(SpeakerMapping).where(
                            SpeakerMapping.job_id == job_id,
                            SpeakerMapping.speaker_label == emb.speaker_label,
                        )
                    )
                )
                .scalars()
                .first()
            )
            if mapping:
                mapping.custom_name = best_name

    await db.commit()


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/config", response_model=ModelConfigResponse)
async def get_config():
    return {
        "whisper_model": settings.whisper_model,
        "device": settings.device,
        "hf_token": settings.hf_token,
        "diarization_provider": settings.diarization_provider,
        "diarization_model": settings.diarization_model,
        "enable_alignment_model_cache": settings.enable_alignment_model_cache,
    }


@router.patch("/config")
async def update_config(body: ModelConfigRequest):
    """Update model configuration dynamically (non-Swagger endpoint)."""
    updates = body.model_dump(exclude_unset=True)

    if "whisper_model" in updates:
        settings.whisper_model = updates["whisper_model"]
    if "device" in updates:
        settings.device = updates["device"]
    if "hf_token" in updates:
        settings.hf_token = updates["hf_token"]
    if "diarization_provider" in updates:
        settings.diarization_provider = updates["diarization_provider"]
    if "diarization_model" in updates:
        settings.diarization_model = updates["diarization_model"]
    if "enable_alignment_model_cache" in updates:
        settings.enable_alignment_model_cache = updates["enable_alignment_model_cache"]

    if "whisper_model" in updates:
        await _reload_engine_with_new_model(settings.whisper_model)

    return {"status": "updated", "changes": list(updates.keys())}


# Keys whose values must not be returned verbatim in API responses.
_REDACTED_INFERENCE_KEYS = frozenset({"api_key"})
_REDACTED_PLACEHOLDER = "*" * 12


def _redact_inference_config(cfg: dict) -> dict:
    """Return *cfg* with secret values replaced by a placeholder."""
    out = dict(cfg)
    for key in _REDACTED_INFERENCE_KEYS:
        if out.get(key):
            out[key] = _REDACTED_PLACEHOLDER
    return out


@router.get("/inference/config")
async def get_inference_config():
    return _redact_inference_config(_load_inference_config())


@router.post("/inference/config")
async def update_inference_config(body: InferenceConfigRequest):
    cfg = body.model_dump()
    if url := cfg.get("base_url"):
        _validate_base_url(url, "base_url")
    _save_inference_config(cfg)
    return {"status": "saved", "config": _redact_inference_config(cfg)}


@router.delete("/inference/config")
async def delete_inference_config():
    if _INFERENCE_CONFIG_FILE.exists():
        _INFERENCE_CONFIG_FILE.unlink()
    if _LEGACY_INFERENCE_CONFIG.exists():
        _LEGACY_INFERENCE_CONFIG.unlink()
    if _LEGACY_PT_INFERENCE_CONFIG.exists():
        _LEGACY_PT_INFERENCE_CONFIG.unlink()
    return {"status": "deleted"}


@router.post("/inference/models")
async def fetch_inference_models(body: InferenceModelsRequest):
    _validate_base_url(body.base_url, "base_url")
    try:
        models = await get_available_models(body.base_url, body.api_key)
        return {"models": models}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/inference/test")
async def test_inference_connection(body: InferenceTestRequest):
    _validate_base_url(body.base_url, "base_url")
    result = await test_inf_conn(body.base_url, body.api_key)
    return result


@router.post("/inference/generate")
async def inference_generate(body: InferenceGenerateRequest):
    cfg = _load_inference_config()
    engine = InferenceEngine(
        base_url=cfg.get("base_url", "http://localhost:11434/v1"),
        api_key=cfg.get("api_key", "not-needed"),
        model_name=cfg.get("model_name", ""),
        vision_enabled=cfg.get("vision_enabled", False),
    )
    if body.stream:

        async def stream_generator():
            gen = await engine.generate(
                prompt=body.prompt,
                image_base64=body.image_base64,
                stream=True,
                temperature=body.temperature,
                max_tokens=body.max_tokens,
            )
            async for chunk in gen:
                yield chunk

        return StreamingResponse(stream_generator(), media_type="text/event-stream")
    else:
        res = await engine.generate(
            prompt=body.prompt,
            image_base64=body.image_base64,
            stream=False,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
        )
        return {"response": res}


async def _build_transcript_prompt(job_id: str, db: AsyncSession, action: str) -> str:
    """Fetch segments for a job and build a prompt for the AI action."""
    segs = (
        (await db.execute(
            select(TranscriptSegment)
            .where(TranscriptSegment.job_id == job_id)
            .order_by(TranscriptSegment.start_time)
        ))
        .scalars()
        .all()
    )
    if not segs:
        return ""

    lines = []
    for s in segs:
        start = int(s.start_time // 60)
        end_sec = int(s.end_time % 60)
        start_sec = int(s.start_time % 60)
        lines.append(
            f"[{start}:{start_sec:02d}-{start}:{end_sec:02d}] "
            f"{s.speaker_label}: {s.text}"
        )

    transcript = "\n".join(lines)

    if action == "summarize":
        return (
            "Provide a clear, structured summary of the following transcript. "
            "Include: (1) a brief overview paragraph, "
            "(2) key topics discussed, "
            "(3) any notable quotes or decisions, "
            "and (4) a list of action items if any are mentioned. "
            "Preserve the meaning and speaker context.\n\n"
            f"TRANSCRIPT:\n{transcript}"
        )
    elif action == "cleanup":
        return (
            "Clean up the following transcript by removing verbal tics, "
            "disfluencies (um, ah, uh, like, you know), false starts, "
            "and stuttering. Preserve the exact speaker attribution, "
            "core meaning, key names, and proper nouns. "
            "Fix punctuation and capitalization where needed. "
            "Output the cleaned transcript in the same format.\n\n"
            f"TRANSCRIPT:\n{transcript}"
        )
    return transcript


@router.post("/jobs/{job_id}/summarize")
async def summarize_job(job_id: str, db: AsyncSession = Depends(get_db)):
    """Stream a summary of the transcript for the given job."""
    job = await db.get(TranscriptionJob, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.status != JobStatus.completed:
        raise HTTPException(409, f"Job is {job.status.value}, not completed")

    prompt = await _build_transcript_prompt(job_id, db, "summarize")
    if not prompt:
        raise HTTPException(400, "No transcript segments found for this job")

    cfg = _load_inference_config()
    engine = InferenceEngine(
        base_url=cfg.get("base_url", "http://localhost:11434/v1"),
        api_key=cfg.get("api_key", "not-needed"),
        model_name=cfg.get("model_name", ""),
        vision_enabled=cfg.get("vision_enabled", False),
    )

    async def stream_generator():
        try:
            gen = await engine.generate(
                prompt=prompt,
                stream=True,
                temperature=0.3,
                max_tokens=2048,
            )
            async for chunk in gen:
                yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'text': str(exc)})}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")


@router.post("/jobs/{job_id}/cleanup")
async def cleanup_job(job_id: str, db: AsyncSession = Depends(get_db)):
    """Stream a cleaned-up version of the transcript for the given job."""
    job = await db.get(TranscriptionJob, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.status != JobStatus.completed:
        raise HTTPException(409, f"Job is {job.status.value}, not completed")

    prompt = await _build_transcript_prompt(job_id, db, "cleanup")
    if not prompt:
        raise HTTPException(400, "No transcript segments found for this job")

    cfg = _load_inference_config()
    engine = InferenceEngine(
        base_url=cfg.get("base_url", "http://localhost:11434/v1"),
        api_key=cfg.get("api_key", "not-needed"),
        model_name=cfg.get("model_name", ""),
        vision_enabled=cfg.get("vision_enabled", False),
    )

    async def stream_generator():
        try:
            gen = await engine.generate(
                prompt=prompt,
                stream=True,
                temperature=0.2,
                max_tokens=4096,
            )
            async for chunk in gen:
                yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'text': str(exc)})}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")


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
    custom_vocabulary: str | None = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
) -> JobCreated:
    contents = await file.read()
    if len(contents) > settings.max_upload_size:
        raise HTTPException(413, "File too large")

    job = TranscriptionJob(
        filename=file.filename or "unknown",
        status=JobStatus.queued,
        custom_vocabulary=custom_vocabulary,
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

    safe_filename = _sanitise_path_component(file.filename or "unknown")
    audio_path = settings.upload_path / f"{job.id}_{safe_filename}"
    _assert_contained(audio_path, settings.upload_path)
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

    from artifice_transcribe.db.models import TranscriptSegment as TS

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


@router.get("/jobs/{job_id}/speakers", response_model=SpeakerMapResponse)
async def get_speakers(job_id: str, db: AsyncSession = Depends(get_db)) -> SpeakerMapResponse:
    job = await db.get(TranscriptionJob, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    mappings = (
        (await db.execute(select(SpeakerMapping).where(SpeakerMapping.job_id == job_id)))
        .scalars()
        .all()
    )
    return SpeakerMapResponse(
        job_id=job_id,
        speakers=[
            SpeakerMappingOut(speaker_label=m.speaker_label, custom_name=m.custom_name)
            for m in mappings
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

    from artifice_transcribe.services import exports

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


# ── Persistent Dictionary ──────────────────────────────────────────────


@router.get("/dictionary", response_model=DictionaryResponse | None)
async def get_dictionary(db: AsyncSession = Depends(get_db)) -> DictionaryResponse | None:
    row = (await db.execute(select(PersistentDictionary).limit(1))).scalars().first()
    if row is None:
        return None
    return DictionaryResponse(id=row.id, words=row.words, updated_at=row.updated_at)


@router.put("/dictionary", response_model=DictionaryResponse)
async def update_dictionary(
    body: DictionaryUpdate,
    db: AsyncSession = Depends(get_db),
) -> DictionaryResponse:
    row = (await db.execute(select(PersistentDictionary).limit(1))).scalars().first()
    if row is None:
        row = PersistentDictionary(words=body.words)
        db.add(row)
    else:
        row.words = body.words
        row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return DictionaryResponse(id=row.id, words=row.words, updated_at=row.updated_at)


# ── Speaker Enrollment & Recognition ───────────────────────────────────


@router.post("/speakers/enroll", response_model=SpeakerEnrollResponse)
async def enroll_speaker(
    name: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> SpeakerEnrollResponse:
    """Enroll a known speaker by uploading a short audio clip of their voice."""

    contents = await file.read()
    if len(contents) > settings.max_upload_size:
        raise HTTPException(413, "File too large")

    safe_name = _sanitise_path_component(name)
    safe_filename = _sanitise_path_component(file.filename or "unknown")
    audio_path = settings.upload_path / f"enroll_{safe_name}_{safe_filename}"
    _assert_contained(audio_path, settings.upload_path)
    audio_path.write_bytes(contents)

    engine = _get_engine()
    engine._ensure_models()

    # Extract embedding using the diarization pipeline's internal model
    embedder = engine._diarize_model.model._embedding
    from pyannote.audio import Inference  # type: ignore[import-untyped]

    inference = Inference(embedder, window="whole")
    embedding = inference(str(audio_path))

    emb_bytes = pack_embedding(embedding)
    spk = KnownSpeaker(
        name=name,
        embedding=emb_bytes,
        model_name="pyannote/embedding",
        dimension=len(embedding),
        sample_audio_path=str(audio_path),
    )
    db.add(spk)
    await db.commit()

    return SpeakerEnrollResponse(id=spk.id, name=spk.name)


@router.post("/speakers/enroll-from-job", response_model=SpeakerEnrollResponse)
async def enroll_speaker_from_job(
    body: EnrollFromJobRequest,
    db: AsyncSession = Depends(get_db),
) -> SpeakerEnrollResponse:
    """Enroll a known speaker from a completed job's existing embedding."""

    emb = (
        (
            await db.execute(
                select(SpeakerEmbedding).where(
                    SpeakerEmbedding.job_id == body.job_id,
                    SpeakerEmbedding.speaker_label == body.speaker_label,
                )
            )
        )
        .scalars()
        .first()
    )
    if emb is None:
        raise HTTPException(
            404, f"No embedding found for {body.speaker_label} in job {body.job_id}"
        )

    spk = KnownSpeaker(
        name=body.name,
        embedding=emb.embedding,
        model_name=emb.model_name,
        dimension=emb.dimension,
    )
    db.add(spk)
    await db.commit()

    return SpeakerEnrollResponse(id=spk.id, name=spk.name)


@router.get("/speakers/known", response_model=KnownSpeakerList)
async def list_known_speakers(db: AsyncSession = Depends(get_db)) -> KnownSpeakerList:
    speakers = (await db.execute(select(KnownSpeaker))).scalars().all()
    return KnownSpeakerList(
        speakers=[
            KnownSpeakerOut(
                id=s.id,
                name=s.name,
                model_name=s.model_name,
                dimension=s.dimension,
                created_at=s.created_at,
                legacy_embedding=_is_legacy_pickle_blob(s.embedding),
            )
            for s in speakers
        ]
    )


@router.delete("/speakers/known/{speaker_id}", status_code=204)
async def delete_known_speaker(
    speaker_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    spk = await db.get(KnownSpeaker, speaker_id)
    if spk is None:
        raise HTTPException(404, "Known speaker not found")
    await db.delete(spk)
    await db.commit()


@router.post("/jobs/{job_id}/match-speakers", response_model=SpeakerMatchResponse)
async def match_speakers(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> SpeakerMatchResponse:
    """Manually trigger speaker matching for a completed job."""
    job = await db.get(TranscriptionJob, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.status != JobStatus.completed:
        raise HTTPException(409, f"Job is {job.status.value}, not completed")

    await _auto_match_speakers(job_id, db)

    # Return the match results
    mappings = (
        (await db.execute(select(SpeakerMapping).where(SpeakerMapping.job_id == job_id)))
        .scalars()
        .all()
    )

    known_list = (await db.execute(select(KnownSpeaker))).scalars().all()
    known_names = {s.name for s in known_list}

    matches = []
    for m in mappings:
        if m.custom_name in known_names:
            matches.append(
                SpeakerMatchResult(
                    speaker_label=m.speaker_label,
                    matched_name=m.custom_name,
                    confidence=None,
                )
            )
        else:
            matches.append(SpeakerMatchResult(speaker_label=m.speaker_label))

    return SpeakerMatchResponse(job_id=job_id, matches=matches)


@router.get("/jobs/{job_id}/speaker-embeddings", response_model=list[SpeakerEmbeddingOut])
async def get_speaker_embeddings(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[SpeakerEmbeddingOut]:
    embeddings = (
        (await db.execute(select(SpeakerEmbedding).where(SpeakerEmbedding.job_id == job_id)))
        .scalars()
        .all()
    )
    return [
        SpeakerEmbeddingOut(
            speaker_label=e.speaker_label, dimension=e.dimension, model_name=e.model_name
        )
        for e in embeddings
    ]


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

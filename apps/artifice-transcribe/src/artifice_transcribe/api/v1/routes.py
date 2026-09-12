# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from model_harness.contract import EndpointRejected
from model_harness.endpoint_policy import EndpointPolicy
from shared_ui.path_validation import (
    PathValidationError,
    assert_contained,
    sanitise_path_component,
)
from shared_ui.uploads import UploadTooLarge, read_capped_to_tempfile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from artifice_transcribe.config import settings
from artifice_transcribe.db.models import (
    JobStatus,
    KnownSpeaker,
    LegacyEmbeddingError,
    PersistentDictionary,
    SpeakerEmbedding,
    SpeakerMapping,
    TranscriptionJob,
    TranscriptSegment,
    pack_embedding,
    unpack_embedding,
)
from artifice_transcribe.db.session import async_session, get_db
from artifice_transcribe.schemas.transcription import (
    JobCreated,
    TranscriptionOptions,
)
from artifice_transcribe.services.asr_backend import ASRBackend
from artifice_transcribe.services.inference import InferenceEngine
from artifice_transcribe.services.token_redaction import redact_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["transcription"])


# ── Model endpoints ──────────────────────────────────────────────────────────
#
# The allowlist policy lives in ``model_harness.endpoint_policy`` — this app
# only wraps it with FastAPI's exception type.  This is the rule the harness
# exists to own; the duplicate that lived here before Phase 3 has been
# collapsed into the harness.
#
# See :class:`model_harness.endpoint_policy.EndpointPolicy` for the full
# rationale and constraint set.

_endpoint_policy = EndpointPolicy()


def _classify_host(host: str) -> tuple[bool, str]:
    """Return ``(permitted, reason)`` for a URL host.
    Delegates to the harness policy."""
    return _endpoint_policy.classify_host(host)


def _validate_base_url(raw: str, field_name: str) -> str:
    """Return *raw* after checking its scheme and host. Fails closed, loudly."""
    try:
        return _endpoint_policy.validate_url(raw)
    except EndpointRejected as e:
        raise HTTPException(status_code=400, detail=f"{field_name}: {e}") from e


# ── Inference configuration persistence helper ───────────────────────────────
# Uses platformdirs to resolve a per-user data directory, so the config file
# survives frozen bundles (.exe/.dmg) where CWD can be anywhere.
_LEGACY_INFERENCE_CONFIG = Path("./data/inference_config.json").resolve()
_LEGACY_PT_INFERENCE_CONFIG = Path("./data/pt-inference-config.json").resolve()
_INFERENCE_CONFIG_FILE = settings.data_path / "inference_config.json"
_HF_TOKEN_FILE = settings.data_path / "hf_token.json"


def _load_hf_token() -> str:
    """Return the HF token, preferring the env var and falling back to
    the secure-io-protected file on disk.

    The token is never read from the plaintext ``.env`` file through
    ``Settings.hf_token`` alone — if the env var is unset the secure-io
    file is consulted.  This keeps the Zero Secrets Policy self-consistent.
    """
    token = settings.hf_token
    if token:
        return token
    if _HF_TOKEN_FILE.exists():
        from secure_io import ensure_restricted

        ensure_restricted(_HF_TOKEN_FILE)
        try:
            data = json.loads(_HF_TOKEN_FILE.read_text(encoding="utf-8"))
            return data.get("hf_token", "")
        except Exception as exc:
            logger.warning("Could not read %s — using defaults: %s", _HF_TOKEN_FILE, exc)
    return ""


def _save_hf_token(token: str) -> None:
    """Persist the HF token through ``secure_io.write_private_json``."""
    from secure_io import is_restricted, write_private_json

    _HF_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    write_private_json(_HF_TOKEN_FILE, {"hf_token": token})
    # Verify write-time security (mirrors _save_inference_config).
    if not is_restricted(_HF_TOKEN_FILE):
        write_private_json(_HF_TOKEN_FILE, {"hf_token": token})
        if not is_restricted(_HF_TOKEN_FILE):
            raise PermissionError(f"Failed to secure HF token file after retry: {_HF_TOKEN_FILE}")


def _migrate_legacy_inference_config() -> None:
    """Move legacy ``./data/inference_config.json`` to the platform data dir."""
    if _INFERENCE_CONFIG_FILE.exists():
        if _LEGACY_INFERENCE_CONFIG.exists():
            logger.info(
                "Legacy inference config found at %s but config already exists at %s. "
                "Using the existing config.",
                _LEGACY_INFERENCE_CONFIG,
                _INFERENCE_CONFIG_FILE,
            )
        return
    if _LEGACY_INFERENCE_CONFIG.exists():
        logger.info(
            "Migrating legacy inference config from %s to %s",
            _LEGACY_INFERENCE_CONFIG,
            _INFERENCE_CONFIG_FILE,
        )
        _INFERENCE_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        import shutil

        shutil.move(str(_LEGACY_INFERENCE_CONFIG), str(_INFERENCE_CONFIG_FILE))
        logger.info("Migration complete — inference config is now at %s", _INFERENCE_CONFIG_FILE)


def _load_inference_config() -> dict:
    _migrate_legacy_inference_config()
    if _INFERENCE_CONFIG_FILE.exists():
        from secure_io import ensure_restricted

        ensure_restricted(_INFERENCE_CONFIG_FILE)
        try:
            return json.loads(_INFERENCE_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not read %s — using defaults: %s", _INFERENCE_CONFIG_FILE, exc)
    return {
        "base_url": "http://localhost:11434/v1",
        "api_key": "not-needed",
        "model_name": "",
        "vision_enabled": False,
    }


def _save_inference_config(cfg: dict) -> None:
    from secure_io import is_restricted, write_private_json

    _INFERENCE_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    write_private_json(_INFERENCE_CONFIG_FILE, cfg)

    # Align write-time verification with the public is_restricted() contract
    # (see artifice-graph config_helper.save_user_config for rationale).
    if not is_restricted(_INFERENCE_CONFIG_FILE):
        write_private_json(_INFERENCE_CONFIG_FILE, cfg)
        if not is_restricted(_INFERENCE_CONFIG_FILE):
            raise PermissionError(
                f"Failed to secure inference config after retry: {_INFERENCE_CONFIG_FILE}"
            )


# Module-level engine singleton (lazy init)
_engine: ASRBackend | None = None

_INSTALL_HINT = "uv sync --extra asr"
_INSTALL_HINT_CUDA = "uv sync --extra asr-cuda"

# ASR backends selectable via settings.asr_backend. Kept in step with
# ModelConfigResponse.available_asr_backends (schemas/transcription.py).
_ASR_BACKENDS = frozenset({"whisperx", "parakeet"})


class AsrUnavailable(Exception):
    """Raised when the ASR stack (torch, whisperx, pyannote) is not installed.

    The ``public_message`` attribute is set from string literals — it is
    never derived from a wrapped third-party exception.  Catch sites should
    read ``public_message`` for the response body rather than calling
    ``str(e)``, which CodeQL's taint tracker treats as unsafe.
    """

    def __init__(self, extra: str = "asr") -> None:
        hint = _INSTALL_HINT_CUDA if extra == "asr-cuda" else _INSTALL_HINT
        self.public_message = (
            f"The transcription stack is not installed. "
            f"Run `{hint}` to install it, then restart the server."
        )
        super().__init__(self.public_message)


def _build_engine() -> ASRBackend:
    """Construct the ASR backend selected by ``settings.asr_backend``.

    This is the seam the :class:`ASRBackend` protocol was built for: both
    engines share ``device`` / ``hf_token`` / ``diarization_model``, and differ
    only in their model identifier.  The heavy imports happen here (and only
    here) so a base install can import this module; an absent stack surfaces as
    :class:`AsrUnavailable`, as it always has.
    """
    try:
        if settings.asr_backend == "parakeet":
            from artifice_transcribe.services.parakeet_engine import ParakeetEngine

            return ParakeetEngine(
                device=settings.device,
                hf_token=_load_hf_token(),
                diarization_model=settings.diarization_model,
                initial_prompt=settings.whisper_initial_prompt,
            )
        from artifice_transcribe.services.transcription import WhisperXEngine

        return WhisperXEngine(
            model_size=settings.whisper_model,
            device=settings.device,
            hf_token=_load_hf_token(),
            diarization_model=settings.diarization_model,
            initial_prompt=settings.whisper_initial_prompt,
        )
    except ImportError as exc:
        raise AsrUnavailable() from exc


async def _reload_engine():
    """Rebuild the engine in place, unloading the previous one first.

    Generalized from the old ``_reload_engine_with_new_model``, which took a
    WhisperX model-size string as an argument.  With two backends the engine
    identity is no longer a single model string, so the reload now reads
    ``settings.asr_backend`` (and ``settings.whisper_model``) directly and the
    call site simply checks *which* fields changed.
    """
    global _engine
    logger.info(
        "Reloading engine (backend=%s, whisper_model=%s)",
        settings.asr_backend,
        settings.whisper_model,
    )

    old_engine = _engine
    if old_engine:
        old_engine.unload()

    _engine = _build_engine()
    logger.info("Engine reloaded successfully")


def _get_engine():
    global _engine
    if _engine is None:
        _engine = _build_engine()
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
            job.completed_at = datetime.now(UTC)
            await db.commit()
            logger.info("Job %s completed with %d segments", job_id, len(segments))

            # Auto-match speakers against known speakers
            try:
                await _auto_match_speakers(job_id, db)
            except Exception:
                logger.exception("Auto-match failed for job %s", job_id)

        except Exception as exc:
            logger.error("Job %s failed: %s", job_id, redact_token(str(exc)))
            job = await db.get(TranscriptionJob, job_id)
            if job:
                job.status = JobStatus.failed
                job.error_message = redact_token(str(exc))
                job.completed_at = datetime.now(UTC)
                await db.commit()

        finally:
            try:
                engine = _get_engine()
                if engine is not None:
                    engine.unload()
            except AsrUnavailable:
                pass


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


async def _build_transcript_prompt(job_id: str, db: AsyncSession, action: str) -> str:
    """Fetch segments for a job and build a prompt for the AI action."""
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
    if not segs:
        return ""

    lines = []
    for s in segs:
        start = int(s.start_time // 60)
        end_sec = int(s.end_time % 60)
        start_sec = int(s.start_time % 60)
        lines.append(f"[{start}:{start_sec:02d}-{start}:{end_sec:02d}] {s.speaker_label}: {s.text}")

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
    _validate_base_url(cfg.get("base_url", "http://localhost:11434/v1"), "base_url")
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
            yield f"data: {json.dumps({'type': 'error', 'text': redact_token(str(exc))})}\n\n"
        finally:
            await engine.aclose()
        yield 'data: {"type": "done"}\n\n'

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
    _validate_base_url(cfg.get("base_url", "http://localhost:11434/v1"), "base_url")
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
            yield f"data: {json.dumps({'type': 'error', 'text': redact_token(str(exc))})}\n\n"
        finally:
            await engine.aclose()
        yield 'data: {"type": "done"}\n\n'

    return StreamingResponse(stream_generator(), media_type="text/event-stream")


@router.post("/transcribe", response_model=JobCreated, status_code=202)
async def create_transcription(
    file: UploadFile,
    language: str | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    custom_vocabulary: str | None = None,
    mode: str = "auto",
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
) -> JobCreated:
    if mode not in ("auto", "manual"):
        raise HTTPException(status_code=400, detail="mode must be 'auto' or 'manual'")

    try:
        spooled = await read_capped_to_tempfile(file, settings.max_upload_size)
    except UploadTooLarge as e:
        raise HTTPException(status_code=413, detail=e.public_message) from e

    job = TranscriptionJob(
        filename=file.filename or "unknown",
        status=JobStatus.queued,
        custom_vocabulary=custom_vocabulary,
        options=json.dumps(
            {
                "mode": mode,
                "language": language,
                "min_speakers": min_speakers,
                "max_speakers": max_speakers,
                "initial_prompt": settings.whisper_initial_prompt,
            }
        ),
    )
    db.add(job)
    await db.commit()

    try:
        safe_filename = sanitise_path_component(file.filename or "unknown")
    except PathValidationError as e:
        raise HTTPException(status_code=400, detail=e.public_message) from e
    audio_path = settings.upload_path / f"{job.id}_{safe_filename}"
    try:
        assert_contained(audio_path, settings.upload_path)
    except PathValidationError as e:
        raise HTTPException(status_code=400, detail=e.public_message) from e

    def _persist(spooled_file, dest_path):
        import shutil

        with spooled_file, open(dest_path, "wb") as out:
            shutil.copyfileobj(spooled_file, out)

    await asyncio.to_thread(_persist, spooled, audio_path)

    if mode == "manual":
        # Hand-transcription job: skip ASR entirely. The uploaded audio is
        # kept for the editor's audio player, but nothing is queued — the job
        # is already complete and seeded with one empty segment to type into.
        job.status = JobStatus.completed
        job.progress_percentage = 100.0
        job.completed_at = datetime.now(UTC)
        db.add(
            TranscriptSegment(
                job_id=job.id,
                speaker_label="SPEAKER_00",
                start_time=0.0,
                end_time=0.0,
                text="",
            )
        )
        await db.commit()
        return JobCreated(job_id=job.id, status=JobStatus.completed)

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

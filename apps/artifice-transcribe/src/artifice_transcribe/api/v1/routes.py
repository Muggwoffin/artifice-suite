# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from queue import Empty

import model_harness.registry as reg
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from model_harness.contract import EndpointRejected
from model_harness.endpoint_policy import EndpointPolicy
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
    ConsentRequest,
    ConsentResponse,
    DictionaryResponse,
    DictionaryUpdate,
    DownloadStartResponse,
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
    ModelDownloadInfo,
    ModelInfoResponse,
    ModelListResponse,
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
from artifice_transcribe.services.download import (
    find_registry_key,
    get_download_manager,
    hf_cache_dir,
    human_size,
    is_consented,
    record_consent,
    requires_token,
    resolve_transitive,
    revoke_consent,
    total_transitive_size,
)
from artifice_transcribe.services.inference import (
    InferenceEngine,
    get_available_models,
)
from artifice_transcribe.services.inference import (
    test_connection as test_inf_conn,
)
from artifice_transcribe.services.token_redaction import redact_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["transcription"])


async def _read_capped(upload: UploadFile, limit: int) -> bytes:
    """Read *upload* in bounded 64 KB chunks, raising HTTP 413 if *limit* is
    exceeded **during** the read so an oversized body is never fully resident.
    """
    chunks: list[bytes] = []
    total = 0
    while chunk := await upload.read(64 * 1024):
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds {limit // (1024 * 1024)} MB upload limit",
            )
        chunks.append(chunk)
    return b"".join(chunks)


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
        except Exception:
            pass
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
        except Exception:
            pass
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
_engine = None

_INSTALL_HINT = "uv sync --extra asr"
_INSTALL_HINT_CUDA = "uv sync --extra asr-cuda"


class AsrUnavailable(Exception):
    """Raised when the ASR stack (torch, whisperx, pyannote) is not installed."""

    def __init__(self, extra: str = "asr") -> None:
        hint = _INSTALL_HINT_CUDA if extra == "asr-cuda" else _INSTALL_HINT
        super().__init__(
            f"The transcription stack is not installed. "
            f"Run `{hint}` to install it, then restart the server."
        )


async def _reload_engine_with_new_model(new_model: str):
    """Reload the transcription engine with a new Whisper model while preserving the settings."""
    global _engine
    logger.info("Reloading engine with new Whisper model: %s", new_model)

    old_engine = _engine
    if old_engine:
        old_engine.unload()

    try:
        from artifice_transcribe.services.transcription import TranscriptionEngine
    except ImportError as exc:
        raise AsrUnavailable() from exc

    _engine = TranscriptionEngine(
        model_size=settings.whisper_model,
        device=settings.device,
        hf_token=_load_hf_token(),
    )
    logger.info("Engine reloaded successfully with model: %s", new_model)


def _get_engine():
    global _engine
    if _engine is None:
        try:
            from artifice_transcribe.services.transcription import TranscriptionEngine
        except ImportError as exc:
            raise AsrUnavailable() from exc

        _engine = TranscriptionEngine(
            model_size=settings.whisper_model,
            device=settings.device,
            hf_token=_load_hf_token(),
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


def _redact_model_config(key: str, value: str) -> str:
    """Return the placeholder if *key* holds a secret that is set."""
    if key in _REDACTED_MODEL_CONFIG_KEYS and value:
        return _REDACTED_PLACEHOLDER
    return value


@router.get("/config", response_model=ModelConfigResponse)
async def get_config():
    fields = {
        "whisper_model": settings.whisper_model,
        "device": settings.device,
        "hf_token": _load_hf_token(),
        "diarization_provider": settings.diarization_provider,
        "diarization_model": settings.diarization_model,
        "enable_alignment_model_cache": settings.enable_alignment_model_cache,
    }
    return {k: _redact_model_config(k, v) for k, v in fields.items()}


@router.patch("/config")
async def update_config(body: ModelConfigRequest):
    """Update model configuration dynamically (non-Swagger endpoint)."""
    updates = body.model_dump(exclude_unset=True)

    if "whisper_model" in updates:
        settings.whisper_model = updates["whisper_model"]
    if "device" in updates:
        settings.device = updates["device"]
    if "hf_token" in updates and updates["hf_token"] != _REDACTED_PLACEHOLDER:
        _save_hf_token(updates["hf_token"])
    if "diarization_provider" in updates:
        settings.diarization_provider = updates["diarization_provider"]
    if "diarization_model" in updates:
        settings.diarization_model = updates["diarization_model"]
    if "enable_alignment_model_cache" in updates:
        settings.enable_alignment_model_cache = updates["enable_alignment_model_cache"]

    if "whisper_model" in updates:
        try:
            await _reload_engine_with_new_model(settings.whisper_model)
        except AsrUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {"status": "updated", "changes": list(updates.keys())}


# Keys whose values must not be returned verbatim in API responses.
_REDACTED_INFERENCE_KEYS = frozenset({"api_key"})
_REDACTED_MODEL_CONFIG_KEYS = frozenset({"hf_token"})
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
    _validate_base_url(cfg.get("base_url", "http://localhost:11434/v1"), "base_url")
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
        yield 'data: {"type": "done"}\n\n'

    return StreamingResponse(stream_generator(), media_type="text/event-stream")


@router.get("/health/detailed")
async def health_detailed():
    """Full health check: model load state, GPU info, database connectivity."""
    try:
        engine = _get_engine()
        engine_status = engine.health_check()
    except AsrUnavailable:
        engine_status = {
            "available": False,
            "reason": str(AsrUnavailable()),
            "install_hint": _INSTALL_HINT,
        }

    db_ok = True
    try:
        async with async_session() as db:
            await db.execute(select(TranscriptionJob).limit(1))
    except Exception:
        db_ok = False

    engine_ok = engine_status.get("available") is not False

    return {
        "status": "ok" if (db_ok and engine_ok) else "degraded",
        "engine": engine_status,
        "database": {"status": "ok" if db_ok else "error"},
    }


@router.post("/health/preload")
async def health_preload():
    """Load all models into memory. Returns success or error details."""
    try:
        engine = _get_engine()
        result = await asyncio.to_thread(engine.preload)
        return result
    except AsrUnavailable as exc:
        return {"ok": False, "error": str(exc), "install_hint": _INSTALL_HINT}


@router.get("/capabilities")
async def capabilities():
    """Report which optional features are available — never imports the ASR
    stack to answer, so this is safe and fast on a base install.

    Checks for the packages actually required by the transcription engine
    rather than using ``torch`` alone as a proxy.  A partial install where
    torch is present but whisperx (or its diarization dependency,
    pyannote.audio) is missing correctly reports unavailable.
    """
    _required = ("whisperx", "torch", "torchaudio", "torchvision", "torchcodec")
    asr_available = all(importlib.util.find_spec(pkg) is not None for pkg in _required)
    if asr_available:
        asr_info = {"available": True}
    else:
        asr_info = {
            "available": False,
            "reason": "The transcription stack is not installed.",
            "install_hint": _INSTALL_HINT,
        }
    return {"asr": asr_info}


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
    contents = await _read_capped(file, settings.max_upload_size)

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
    content = body if is_binary or not isinstance(body, str) else body.encode("utf-8")
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
        row.updated_at = datetime.now(UTC)
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

    contents = await _read_capped(file, settings.max_upload_size)

    safe_name = _sanitise_path_component(name)
    safe_filename = _sanitise_path_component(file.filename or "unknown")
    audio_path = settings.upload_path / f"enroll_{safe_name}_{safe_filename}"
    _assert_contained(audio_path, settings.upload_path)
    audio_path.write_bytes(contents)

    try:
        engine = _get_engine()
    except AsrUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

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


# ── ASR Model Download ───────────────────────────────────────────────────────
#
# These endpoints support the consent-and-download flow for multi-gigabyte ASR
# model weights.  The dialog itself is rendered by the UI layer; these endpoints
# provide the data it needs: model inventory, transitive size disclosure,
# on-disk destination, consent persistence, and real-time progress via SSE.
#
# No endpoint imports ``torch`` at module scope — the lightweight install
# (no ``--extra asr``) serves the model-list and consent endpoints so a user
# can discover what is available before installing anything.


def _model_info_response(key: str) -> ModelInfoResponse:
    """Build a :class:`ModelInfoResponse` from the registry."""
    models = resolve_transitive(key)
    total = total_transitive_size(key)
    need_token = requires_token(key)

    # Build the list with the registry key for each entry.
    model_list: list[ModelDownloadInfo] = []
    for m in models:
        m_key = find_registry_key(m)
        model_list.append(
            ModelDownloadInfo(
                key=m_key,
                hf_repo=m.hf_repo,
                size_bytes=m.size_bytes,
                size_human=human_size(m.size_bytes),
                requires_hf_token=m.requires_hf_token,
                description=m.description,
            )
        )

    return ModelInfoResponse(
        key=key,
        models=model_list,
        total_size_bytes=total,
        total_size_human=human_size(total),
        requires_hf_token=need_token,
        cache_directory=str(hf_cache_dir()),
        consented=is_consented(key),
    )


@router.get("/models", response_model=ModelListResponse)
async def list_models() -> ModelListResponse:
    """Return all available ASR models with transitive sizes and consent state.

    This is a cheap, read-only endpoint — no imports of the ASR stack, no
    network calls, no file I/O beyond reading the consent file.
    """
    return ModelListResponse(models=[_model_info_response(key) for key in reg.ASR_MODELS])


@router.get("/models/{key}", response_model=ModelInfoResponse)
async def model_info(key: str) -> ModelInfoResponse:
    """Return detailed download info for a single model, including its
    dependencies, total transitive size, on-disk destination, and consent state.
    """
    if key not in reg.ASR_MODELS:
        raise HTTPException(404, f"Unknown model key: {key!r}")
    return _model_info_response(key)


@router.post("/models/{key}/consent", response_model=ConsentResponse)
async def grant_model_consent(key: str, body: ConsentRequest) -> ConsentResponse:
    """Record or revoke the user's consent to download *key*.

    Consent is persisted to ``platformdirs`` user data (not the package
    directory) so it survives reinstalls.  The download endpoint refuses to
    start without recorded consent.

    If *body.consent* is ``False``, consent is revoked.
    """
    if key not in reg.ASR_MODELS:
        raise HTTPException(404, f"Unknown model key: {key!r}")

    if body.consent:
        record_consent(key)
    else:
        revoke_consent(key)

    return ConsentResponse(key=key, consented=body.consent)


@router.post("/models/{key}/download", response_model=DownloadStartResponse)
async def start_model_download(key: str) -> DownloadStartResponse:
    """Begin downloading *key* and all its transitive dependencies.

    **Preconditions:**
    - Consent must have been recorded via ``POST /models/{key}/consent``.
    - If any model requires an HF token, ``hf_token`` must be set in the
      config (see ``PATCH /api/v1/config``).

    **Response:** ``202 Accepted`` with download metadata.  Progress is
    streamed via SSE at ``GET /models/{key}/download/progress``.
    """
    if key not in reg.ASR_MODELS:
        raise HTTPException(404, f"Unknown model key: {key!r}")

    need_token = requires_token(key)
    hf_token = _load_hf_token()

    if need_token and not hf_token:
        raise HTTPException(
            400,
            f"Model '{key}' requires a Hugging Face access token but "
            f"no HF_TOKEN is configured.  Set it via PATCH /api/v1/config "
            f"or the web UI settings panel.",
        )

    manager = get_download_manager()

    # The manager's start_download is lock-guarded and handles dedup — this
    # route is a thin caller.
    try:
        ds = manager.start_download(key, token=hf_token)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc

    total = total_transitive_size(key)
    return DownloadStartResponse(
        key=key,
        model_count=len(ds.models),
        total_size_bytes=total,
        total_size_human=human_size(total),
    )


@router.get("/models/{key}/download/status")
async def get_download_status(key: str) -> dict:
    """Poll the current status of a download (or lack thereof).

    Returns ``null`` state if no download has ever been started for *key*.
    For real-time progress use ``GET /models/{key}/download/progress`` (SSE).
    """
    if key not in reg.ASR_MODELS:
        raise HTTPException(404, f"Unknown model key: {key!r}")

    manager = get_download_manager()
    ds = manager.get_status(key)

    if ds is None:
        return {"key": key, "status": "never_started"}

    return {
        "key": key,
        "started": ds.started,
        "finished": ds.finished,
        "error_message": ds.error_message,
        "models": [
            {
                "key": ms.key,
                "hf_repo": ms.hf_repo,
                "state": ms.state.value,
                "total_bytes": ms.total_bytes,
                "downloaded_bytes": ms.downloaded_bytes,
                "error_message": ms.error_message,
            }
            for ms in ds.models
        ],
    }


@router.post("/models/{key}/download/cancel")
async def cancel_model_download(key: str) -> dict:
    """Request cancellation of an in-flight download for *key*."""
    if key not in reg.ASR_MODELS:
        raise HTTPException(404, f"Unknown model key: {key!r}")

    manager = get_download_manager()
    manager.cancel_download(key)
    return {"key": key, "status": "cancellation_requested"}


@router.get("/models/{key}/download/progress")
async def stream_download_progress(key: str) -> StreamingResponse:
    """SSE stream of download progress events for *key*.

    Returns an error event immediately if no download is active for *key*.
    Otherwise streams JSON-encoded events of type ``progress``, ``error``,
    ``cancelled``, ``cancelling``, or ``completed``.

    Events are formatted as standard SSE:
    ``data: {json}\\n\\n``
    """
    if key not in reg.ASR_MODELS:
        raise HTTPException(404, f"Unknown model key: {key!r}")

    manager = get_download_manager()
    ds = manager.get_status(key)

    if ds is None:

        async def _error_gen():
            payload = {"type": "error", "error": f"No download active for {key}"}
            yield f"data: {json.dumps(payload)}\n\n"

        return StreamingResponse(_error_gen(), media_type="text/event-stream")

    queue = manager.subscribe_events(key)

    async def _event_generator():
        try:
            while True:
                # Send any queued events first.
                try:
                    while True:
                        event = queue.get_nowait()
                        yield f"data: {json.dumps(event)}\n\n"
                except Empty:
                    pass

                # Check if the download is done.
                ds_now = manager.get_status(key)
                if ds_now is not None and ds_now.finished:
                    # Drain any last events.
                    while True:
                        try:
                            event = queue.get_nowait()
                            yield f"data: {json.dumps(event)}\n\n"
                        except Empty:
                            break
                    return

                # Wait for the next event.
                try:
                    event = queue.get(timeout=1.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except Empty:
                    # Timeout — send a heartbeat so the connection stays alive.
                    yield f"data: {json.dumps({'type': 'heartbeat', 'key': key})}\n\n"
        finally:
            manager.unsubscribe_events(key, queue)

    return StreamingResponse(_event_generator(), media_type="text/event-stream")

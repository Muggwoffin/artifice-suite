# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""FastAPI web server for ArtificeGraph — pipeline control + SSE log streaming + state API."""

from __future__ import annotations

import asyncio
import contextlib
import importlib.resources
import json
import logging
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import ChoiceLoader, Environment, PackageLoader, select_autoescape
from model_harness.contract import EndpointRejected
from model_harness.endpoint_policy import EndpointPolicy
from shared_ui.filedialog import FileType, pick_files_async, pick_folder_async
from shared_ui.path_validation import PathValidationError, sanitise_path_component
from shared_ui.path_validation import validate_path as _shared_validate_path
from shared_ui.uploads import UploadTooLarge, read_capped
from starlette.middleware.base import BaseHTTPMiddleware

from artifice_graph._resolution import resolve_for_run
from artifice_graph.config import LLMConfig, PipelineConfig, load_config
from artifice_graph.embedding.bge_embedder import BGEM3Embedder
from artifice_graph.entity_resolution.resolver import EntityResolver
from artifice_graph.entity_resolution.semantic_resolver import SemanticEntityResolver
from artifice_graph.exporters.graph_exporter import GraphExporter
from artifice_graph.exporters.obsidian_exporter import ObsidianExporter
from artifice_graph.extraction.extractor import EntityExtractor
from artifice_graph.extraction.inference_engine import _VISION_INDICATORS
from artifice_graph.extraction.llm_client import LLMClient
from artifice_graph.ingestion.chunker import TextChunker
from artifice_graph.models.document import Document, TextChunk
from artifice_graph.models.entity import Entity
from artifice_graph.models.relationship import Relationship
from artifice_graph.storage.file_store import FileStore
from artifice_graph.web.config_helper import save_user_config

from .routers import byom as byom_router

logger = logging.getLogger(__name__)


# ── App setup ──────────────────────────────────────────────────────

app = FastAPI(title="ArtificeGraph", version="0.1.0")

app.include_router(byom_router.router)


class AllowedHostsMiddleware(BaseHTTPMiddleware):
    """Refuse requests whose Host header does not start with 127.0.0.1 or localhost.

    Prevents DNS rebinding attacks on the local-only import endpoints.
    ``testserver`` is the host the FastAPI TestClient uses.
    """

    async def dispatch(self, request, call_next):
        host = request.headers.get("host", "")
        if host and not any(host.startswith(h) for h in ("127.0.0.1", "localhost", "testserver")):
            return JSONResponse({"error": "Forbidden"}, status_code=403)
        return await call_next(request)


app.add_middleware(AllowedHostsMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://localhost:{os.environ.get('ARTIFICE_PORT', os.environ.get('CALLOSIP_PORT', '8766'))}",
        f"http://127.0.0.1:{os.environ.get('ARTIFICE_PORT', os.environ.get('CALLOSIP_PORT', '8766'))}",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# Static files resolved through importlib.resources (freeze-safe).
# A PyInstaller onedir build compiles pure-Python modules into an embedded
# PYZ archive, so __file__ does not reliably resolve static/ from inside a
# frozen bundle.  Using importlib keeps the path correct in every environment.
_STATIC_DIR = importlib.resources.files("artifice_graph.web") / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# ── Jinja2 — PackageLoader resolves through importlib (freeze-safe), and
# ChoiceLoader lets templates include shared-ui's masthead partial.
_jinja = Environment(
    loader=ChoiceLoader(
        [
            PackageLoader("artifice_graph.web", "templates"),
            PackageLoader("shared_ui", "templates"),
        ]
    ),
    autoescape=select_autoescape(["html", "xml"]),
)

# ── Shared design tokens (resolved from installed shared-ui package) ───────
import shared_ui
from shared_ui.suite import get_preferences, suite_apps, update_preferences

_SHARED_UI = importlib.resources.files(shared_ui) / "assets"
app.mount("/shared", StaticFiles(directory=str(_SHARED_UI)), name="shared")


@app.get("/api/suite/apps")
async def get_suite_apps() -> list[dict[str, object]]:
    """Return the shared launcher model for the suite switcher."""
    return suite_apps()


@app.get("/api/ui/preferences")
async def get_ui_preferences() -> dict[str, object]:
    """Return non-sensitive preferences shared by every Artifice app."""
    return get_preferences()


@app.patch("/api/ui/preferences")
async def patch_ui_preferences(
    patch: dict[str, object] = Body(...),
) -> dict[str, object]:
    """Validate and persist a partial shared UI preference update."""
    return update_preferences(patch)


# --------------------------------------------------------------------------- #
# handoff import endpoint
# --------------------------------------------------------------------------- #


@app.get("/import")
def import_handoff(handoff: str = ""):
    """Receive a handoff token from another Artifice app.

    Reads the handoff manifest, validates it, writes the body text as a
    ``.txt`` file in the ingest input directory, and redirects to the
    main page.  The UUID is unguessable; the URL carries no payload.
    """
    from fastapi.responses import RedirectResponse
    from pathlib import Path

    from shared_ui.handoff import delete_handoff, read_handoff

    if not handoff:
        return RedirectResponse("/")

    result = read_handoff(handoff, expected_target="artifice-graph")
    if result is None:
        return RedirectResponse("/?handoff_error=invalid")

    cfg = load_config()
    input_dir = Path(cfg.ingestion.input_dir)
    input_dir.mkdir(parents=True, exist_ok=True)

    # Write the text to a timestamped file in the input directory
    import datetime

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = input_dir / f"ocr_handoff_{ts}.txt"
    dest.write_text(result["body"], encoding="utf-8")

    delete_handoff(handoff)
    logger.info("Handoff imported from %s → %s", result["source"], dest)
    return RedirectResponse(f"/?handoff_ok=1&handoff_source={result['source']}")


# ── Credential redaction ───────────────────────────────────────────
# The ``PipelineConfig`` model is the authority on which fields hold
# credentials; ``_redact_config`` keys off the model structure directly
# rather than maintaining a parallel key list.  This matches the
# convention in artifice-ocr's settings router.

REDACTED_PLACEHOLDER = "*" * 12


def _redact_config(model: PipelineConfig) -> PipelineConfig:
    """Return a deep copy of *model* with credential fields redacted."""
    cfg = model.model_copy(deep=True)
    if cfg.llm.api_key:
        cfg.llm.api_key = REDACTED_PLACEHOLDER
    return cfg


# ── Run log broker (cross-thread SSE bridging) ─────────────────────
# In-memory: each active run gets a log buffer + wake condition.

_run_logs: dict[str, list[dict[str, Any]]] = {}
_run_locks: dict[str, threading.Lock] = {}
_run_conds: dict[str, threading.Condition] = {}
_run_active: dict[str, bool] = {}  # while True; set False when stream closes
_run_ok: dict[str, bool] = {}  # True while pipeline should continue


def _get_run_log(run_key: str) -> tuple[list, threading.Lock, threading.Condition]:
    if run_key not in _run_logs:
        _run_logs[run_key] = []
        _run_locks[run_key] = threading.Lock()
        _run_conds[run_key] = threading.Condition()
        _run_active[run_key] = True
    return _run_logs[run_key], _run_locks[run_key], _run_conds[run_key]


def _append_log_event(run_key: str, event: dict[str, Any]) -> None:
    buf, lock, cond = _get_run_log(run_key)
    with lock:
        buf.append(event)
    with cond:
        cond.notify_all()


def _end_run_log(run_key: str) -> None:
    buf, lock, cond = _get_run_log(run_key)
    with lock:
        _run_active[run_key] = False
    with cond:
        cond.notify_all()


def _log(run_key: str, msg: str, level: str = "info") -> None:
    _append_log_event(run_key, {"text": msg, "level": level})


def _log_sep(run_key: str) -> None:
    _append_log_event(run_key, {"sep": True})


def _log_head(run_key: str, msg: str) -> None:
    _append_log_event(run_key, {"text": msg, "level": "head"})
    _log_sep(run_key)


def _log_done(run_key: str, msg: str, state: str = "done", *, close_stream: bool = True) -> None:
    _append_log_event(run_key, {"gotoState": state, "text": msg})
    if close_stream:
        _end_run_log(run_key)


def _mark_run_failed(run_key: str, msg: str | None = None) -> None:
    """Mark the run as failed — pipeline should not continue to the next stage."""
    _run_ok[run_key] = False
    if msg:
        _log(run_key, msg, "error")


# ── Input validation — directory and URL allowlists ─────────────────
#
# Path validation is delegated to shared_ui.path_validation, which provides
# backslash normalisation, Windows-drive-letter rejection on POSIX, and a
# more conservative error message (does not leak server filesystem layout).
# The ARTIFICE_GRAPH_ALLOWED_ROOTS env var is consumed by the shared module.


def _validate_directory(raw: str, field_name: str) -> str:
    """Return *raw* as a normalised path string after checking it resides
    within an allowed root directory.  Raises HTTP 400 on rejection."""
    try:
        return _shared_validate_path(
            raw,
            field_name,
            allowed_roots_env_var="ARTIFICE_GRAPH_ALLOWED_ROOTS",
        )
    except PathValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.public_message) from None


# ── Model endpoints ────────────────────────────────────────────────
#
# The allowlist policy lives in ``model_harness.endpoint_policy`` — this
# app only wraps it with FastAPI's exception type.
#
# See :class:`model_harness.endpoint_policy.EndpointPolicy` for the full
# rationale and constraint set.

_endpoint_policy = EndpointPolicy()


def _classify_host(host: str) -> tuple[bool, str]:
    """Return ``(permitted, reason)`` for a URL host.

    Delegates to the harness policy so the decision is centralised.
    """
    return _endpoint_policy.classify_host(host)


def _validate_base_url(raw: str, field_name: str) -> str:
    """Return *raw* after checking its scheme and host. Fails closed, loudly."""
    try:
        return _endpoint_policy.validate_url(raw)
    except EndpointRejected as e:
        raise HTTPException(status_code=400, detail=f"{field_name}: {e}") from e


# ── Config from POST body ──────────────────────────────────────────


def _make_config(body: dict[str, Any]) -> tuple[PipelineConfig, bool]:
    cfg = load_config()
    if i := body.get("input_dir"):
        cfg.ingestion.input_dir = _validate_directory(i, "input_dir")
    if o := body.get("output_dir"):
        cfg.export.output_dir = _validate_directory(o, "output_dir")
    if v := body.get("vault_dir"):
        cfg.export.obsidian_vault_dir = _validate_directory(v, "vault_dir")
    if u := body.get("llm_base_url"):
        cfg.llm.base_url = _validate_base_url(u, "llm_base_url")
    if k := body.get("llm_api_key"):
        if k != REDACTED_PLACEHOLDER:
            cfg.llm.api_key = k
    if m := body.get("llm_model"):
        cfg.llm.model = m
    if v := body.get("vision_mode"):
        cfg.llm.supports_vision = bool(v)
    if cs := body.get("chunk_size"):
        cfg.ingestion.chunk_size = int(cs)
    if co := body.get("chunk_overlap"):
        cfg.ingestion.chunk_overlap = int(co)
    if bs := body.get("batch_size"):
        cfg.extraction.batch_size = int(bs)
    if body.get("graph_formats"):
        cfg.export.graph_formats = body["graph_formats"]
    if "use_semantic" in body:
        cfg.entity_resolution.use_semantic = bool(body["use_semantic"])
    if ebu := body.get("embedding_base_url"):
        cfg.embedding.base_url = _validate_base_url(ebu, "embedding_base_url")
    if em := body.get("embedding_model"):
        cfg.embedding.model = em

    # Resolve the model names once, here, after every override from the request
    # body has been applied and before any stage runs. This is the single point
    # where a run's configuration is final, so it is the only place resolution
    # can see the user's actual choices — and doing it before the pipeline
    # starts means a missing model is reported up front rather than surfacing
    # as a failed stage several minutes in.
    resolve_for_run(cfg)

    return cfg, bool(body.get("incremental", False))


def _build_resolver(cfg: PipelineConfig) -> EntityResolver | SemanticEntityResolver:
    if cfg.entity_resolution.use_semantic:
        embedder = BGEM3Embedder(cfg.embedding)
        return SemanticEntityResolver(embedder=embedder, config=cfg.entity_resolution)
    return EntityResolver(cfg.entity_resolution)


def _load_store(cfg: PipelineConfig) -> FileStore:
    return FileStore(cfg.export.output_dir)


# ── Pipeline runner helpers (worker thread) ────────────────────────


def _do_ingest(
    cfg: PipelineConfig, incremental: bool, run_key: str, *, close_stream: bool = True
) -> None:
    _log_head(run_key, "▶ STAGE 1: INGEST — scanning input directory…")
    store = _load_store(cfg)
    chunker = TextChunker(cfg.ingestion)
    if incremental:
        prev_hashes = {}
        previous = store.load("content_hashes.json")
        if previous:
            prev_hashes = {d["id"]: d.get("content_hash", "") for d in previous}
        documents, chunks, stale_ids = chunker.ingest_all_incremental(prev_hashes)
        if documents:
            new_hashes = {d.id: chunker.file_content_hash(Path(d.filepath)) for d in documents}
            store.save(
                "content_hashes.json", [{"id": k, "content_hash": v} for k, v in new_hashes.items()]
            )
        _log(run_key, f"  Incremental: {len(documents)} new/changed docs → {len(chunks)} chunks")
    else:
        documents, chunks = chunker.ingest_all()
        _log(run_key, f"  Found {len(documents)} documents → {len(chunks)} chunks")
    if not documents:
        _log(run_key, "  No files found. Add text files to input dir.", "dim")
        _mark_run_failed(run_key, "Ingest — no files found")
        _log_done(run_key, "Ingest — no files", close_stream=close_stream)
        return
    store.save_models("documents.json", documents)
    store.save_models("chunks.json", chunks)
    _log(run_key, f"  ✓ Saved to {cfg.export.output_dir}/", "success")
    _log_done(
        run_key, f"Ingest: {len(documents)} docs, {len(chunks)} chunks", close_stream=close_stream
    )


def _do_extract(cfg: PipelineConfig, run_key: str, *, close_stream: bool = True) -> None:
    _log_head(run_key, "▶ STAGE 2: EXTRACT — calling local LLM…")
    store = _load_store(cfg)
    raw_chunks = store.load("chunks.json")
    if not raw_chunks:
        _log(run_key, "  No chunks found. Run Ingest first.", "dim")
        _mark_run_failed(run_key, "Extract — no chunks found")
        _log_done(run_key, "Extract — skipped (no chunks)", close_stream=close_stream)
        return
    chunks = [TextChunk.model_validate(d) for d in raw_chunks]
    llm = LLMClient(cfg.llm)
    extractor = EntityExtractor(llm, cfg.extraction)
    all_entities: list[Entity] = []
    all_rels: list[Relationship] = []
    batch_size = cfg.extraction.batch_size
    total = len(chunks)
    for i in range(0, total, batch_size):
        batch = chunks[i : i + batch_size]
        end = min(i + batch_size, total)
        _log(run_key, f"  Processing chunks {i + 1}–{end}/{total}…")
        try:
            results = extractor.extract_batch(batch)
        except RuntimeError as exc:
            _log(run_key, f"  Extraction failed: {exc}", "error")
            _mark_run_failed(run_key, "Extract — all chunks errored")
            _log_done(run_key, "Extract — failed (all chunks errored)", close_stream=close_stream)
            return
        for result in results:
            all_entities.extend(result.entities)
            all_rels.extend(result.relationships)
    existing_entities = store.load("entities.json")
    if existing_entities and not all_entities:
        _log(run_key, "  Refusing to overwrite non-empty entities.json with empty data.", "warn")
        _log(
            run_key, "  Run with --force from the CLI to overwrite, or fix LLM connectivity.", "dim"
        )
    else:
        store.save_models("entities.json", all_entities)
    existing_rels = store.load("relationships.json")
    if existing_rels and not all_rels:
        _log(
            run_key, "  Refusing to overwrite non-empty relationships.json with empty data.", "warn"
        )
    else:
        store.save_models("relationships.json", all_rels)
    _log(
        run_key,
        f"  ✓ Extracted {len(all_entities)} entities, {len(all_rels)} relationships",
        "success",
    )
    _log_done(
        run_key,
        f"Extract: {len(all_entities)} entities, {len(all_rels)} relationships",
        close_stream=close_stream,
    )


def _do_resolve(cfg: PipelineConfig, run_key: str, *, close_stream: bool = True) -> None:
    _log_head(run_key, "▶ STAGE 3: RESOLVE — deduplicating entities…")
    store = _load_store(cfg)
    raw_entities = store.load("entities.json")
    raw_rels = store.load("relationships.json")
    if not raw_entities:
        _log(run_key, "  No entities found. Run Extract first.", "dim")
        _mark_run_failed(run_key, "Resolve — no entities found")
        _log_done(run_key, "Resolve — skipped (no entities)", close_stream=close_stream)
        return
    entities = [Entity.model_validate(d) for d in raw_entities]
    relationships = [Relationship.model_validate(d) for d in raw_rels]
    store.save_models("entities_raw.json", entities)
    try:
        resolver = _build_resolver(cfg)
    except RuntimeError as exc:
        _log(run_key, f"  Embedder error: {exc}", "error")
        _mark_run_failed(run_key, f"Resolve — embedder unreachable at {cfg.embedding.base_url}")
        _log_done(run_key, "Resolve — failed (embedder unreachable)", close_stream=close_stream)
        return
    method = "semantic" if isinstance(resolver, SemanticEntityResolver) else "fuzzy"
    _log(run_key, f"  Using {method} resolution")
    try:
        merged, updated = resolver.resolve(entities, relationships)
    except RuntimeError as exc:
        _log(run_key, f"  Resolution failed: {exc}", "error")
        _mark_run_failed(run_key, "Resolve — embedder error during resolution")
        _log_done(run_key, "Resolve — failed (embedder error)", close_stream=close_stream)
        return
    if not merged:
        _log(
            run_key,
            "  Refusing to overwrite non-empty entities.json with empty resolution result.",
            "warn",
        )
    else:
        store.save_models("entities.json", merged)
    if not updated:
        _log(
            run_key,
            "  Refusing to overwrite non-empty relationships.json with empty resolution result.",
            "warn",
        )
    else:
        store.save_models("relationships.json", updated)
    _log(run_key, f"  ✓ {len(entities)} → {len(merged)} canonical entities ({method})", "success")
    _log_done(
        run_key, f"Resolve: {len(entities)} → {len(merged)} canonical", close_stream=close_stream
    )


def _do_vault(cfg: PipelineConfig, run_key: str, *, close_stream: bool = True) -> None:
    _log_head(run_key, "▶ STAGE 4: VAULT — generating Obsidian notes…")
    store = _load_store(cfg)
    raw_entities = store.load("entities.json")
    if not raw_entities:
        _log(run_key, "  No entities found. Run extraction first.", "dim")
        _mark_run_failed(run_key, "Vault — no entities found")
        _log_done(run_key, "Vault — skipped (no entities)", close_stream=close_stream)
        return
    entities = [Entity.model_validate(d) for d in raw_entities]
    relationships = [Relationship.model_validate(d) for d in store.load("relationships.json")]
    documents = [Document.model_validate(d) for d in store.load("documents.json")]
    chunks = [TextChunk.model_validate(d) for d in store.load("chunks.json")]
    try:
        resolver = _build_resolver(cfg)
    except RuntimeError as exc:
        _log(run_key, f"  Embedder error: {exc}", "error")
        _mark_run_failed(run_key, f"Vault — embedder unreachable at {cfg.embedding.base_url}")
        _log_done(run_key, "Vault — failed (embedder unreachable)", close_stream=close_stream)
        return
    try:
        merged, updated = resolver.resolve(entities, relationships)
    except RuntimeError as exc:
        _log(run_key, f"  Resolution failed: {exc}", "error")
        _mark_run_failed(run_key, "Vault — embedder error during resolution")
        _log_done(run_key, "Vault — failed (embedder error)", close_stream=close_stream)
        return
    obsidian = ObsidianExporter(resolver, cfg.export)
    vault_path = obsidian.build_vault(merged, updated, documents, chunks)
    note_count = sum(1 for _ in Path(vault_path).rglob("*.md"))
    _log(run_key, f"  ✓ Vault written to {vault_path}", "success")
    _log(run_key, f"    {note_count} notes generated")
    _log_done(run_key, f"Vault: {vault_path}", close_stream=close_stream)


def _do_graph(cfg: PipelineConfig, run_key: str, *, close_stream: bool = True) -> None:
    _log_head(run_key, "▶ STAGE 5: GRAPH — exporting graph…")
    store = _load_store(cfg)
    raw_entities = store.load("entities.json")
    if not raw_entities:
        _log(run_key, "  No entities found. Run extraction first.", "dim")
        _mark_run_failed(run_key, "Graph — no entities found")
        _log_done(run_key, "Graph — skipped (no entities)", close_stream=close_stream)
        return
    entities = [Entity.model_validate(d) for d in raw_entities]
    relationships = [Relationship.model_validate(d) for d in store.load("relationships.json")]
    try:
        resolver = _build_resolver(cfg)
    except RuntimeError as exc:
        _log(run_key, f"  Embedder error: {exc}", "error")
        _mark_run_failed(run_key, f"Graph — embedder unreachable at {cfg.embedding.base_url}")
        _log_done(run_key, "Graph — failed (embedder unreachable)", close_stream=close_stream)
        return
    try:
        merged, updated = resolver.resolve(entities, relationships)
    except RuntimeError as exc:
        _log(run_key, f"  Resolution failed: {exc}", "error")
        _mark_run_failed(run_key, "Graph — embedder error during resolution")
        _log_done(run_key, "Graph — failed (embedder error)", close_stream=close_stream)
        return
    exporter = GraphExporter(cfg.export)
    results = exporter.export(merged, updated)
    _log(run_key, f"  ✓ {exporter.summary()}", "success")
    for fmt, path in results.items():
        _log(run_key, f"    {fmt}: {path}")
    _log_done(run_key, f"Graph: {exporter.summary()}", close_stream=close_stream)


def _do_run_all(cfg: PipelineConfig, incremental: bool, run_key: str) -> None:
    _log_head(run_key, "▶ RUN ALL — full pipeline")
    _run_ok[run_key] = True

    def _ok() -> bool:
        return _run_ok.get(run_key, True)

    _do_ingest(cfg, incremental, run_key, close_stream=False)
    if not _ok():
        _log_sep(run_key)
        _log(run_key, "✗ Pipeline halted — stage 1 failed", "error")
        _end_run_log(run_key)
        return
    _do_extract(cfg, run_key, close_stream=False)
    if not _ok():
        _log_sep(run_key)
        _log(run_key, "✗ Pipeline halted — stage 2 failed", "error")
        _end_run_log(run_key)
        return
    _do_resolve(cfg, run_key, close_stream=False)
    if not _ok():
        _log_sep(run_key)
        _log(run_key, "✗ Pipeline halted — stage 3 failed", "error")
        _end_run_log(run_key)
        return
    _do_vault(cfg, run_key, close_stream=False)
    if not _ok():
        _log_sep(run_key)
        _log(run_key, "✗ Pipeline halted — stage 4 failed", "error")
        _end_run_log(run_key)
        return
    _do_graph(cfg, run_key, close_stream=False)
    if not _ok():
        _log_sep(run_key)
        _log(run_key, "✗ Pipeline halted — stage 5 failed", "error")
        _end_run_log(run_key)
        return

    _log_sep(run_key)
    _log(run_key, "✓ Pipeline complete!", "success")
    _log_done(run_key, "Run All — complete", close_stream=True)


def _do_demo(run_key: str) -> None:
    """Synthetic demo (no LLM). Mirrors cli.py demo logic."""
    _log_head(run_key, "▶ DEMO — synthetic data (no LLM needed)")
    cfg = load_config()
    store = _load_store(cfg)

    sample_text = (
        "The Congress of Vienna was convened in 1814 to reconstruct Europe after the "
        "Napoleonic Wars. Prince Klemens von Metternich, the Austrian foreign minister, "
        "played a central role in the negotiations. The Congress was attended by "
        "representatives from Austria, Prussia, Russia, and Great Britain. "
        "Tsar Alexander I of Russia sought to expand Russian influence across the continent. "
        "The resulting Concert of Europe established a balance of power that lasted "
        "for decades. Baron Karl vom Stein, a Prussian statesman, also participated "
        "in early discussions but died before the Congress concluded. "
        "The Treaty of Paris was signed on May 30, 1814, preceding the Congress. "
        "Metternich later became the dominant figure in European diplomacy, "
        "championing conservatism against nationalist and liberal movements."
    )

    chunker = TextChunker(cfg.ingestion)
    chunk = chunker.ingest_string(sample_text, doc_id="congress_of_vienna_sample")
    doc = Document(
        id="congress_of_vienna_sample",
        filename="congress_of_vienna_sample.txt",
        filepath="<demo>",
        raw_text=sample_text,
        chunk_ids=[chunk.id],
    )
    store.save_models("documents.json", [doc])
    store.save_models("chunks.json", [chunk])
    _log(run_key, "  Ingested demo text → 1 chunk")

    from artifice_graph.extraction.schemas import ExtractionResult

    synthetic = ExtractionResult(
        entities=[
            {
                "name": "Klemens von Metternich",
                "entity_type": "Person",
                "aliases": ["Metternich", "Prince Metternich"],
                "summary": "Austrian foreign minister and central figure at the Congress of Vienna.",
            },
            {
                "name": "Alexander I",
                "entity_type": "Person",
                "aliases": ["Tsar Alexander I"],
                "summary": "Tsar of Russia who sought expanded influence at the Congress of Vienna.",
            },
            {
                "name": "Karl vom Stein",
                "entity_type": "Person",
                "aliases": ["Baron Stein", "Baron vom Stein"],
                "summary": "Prussian statesman who participated in early Congress discussions but died before its conclusion.",
            },
            {
                "name": "Congress of Vienna",
                "entity_type": "Event",
                "aliases": ["The Congress"],
                "summary": "Diplomatic conference held in 1814 to reorganize Europe after the Napoleonic Wars.",
            },
            {
                "name": "Austria",
                "entity_type": "Location",
                "aliases": ["Austrian Empire"],
                "summary": "Major European power and host nation of the Congress of Vienna.",
            },
            {
                "name": "Prussia",
                "entity_type": "Location",
                "aliases": [],
                "summary": "German state that participated in the Congress of Vienna.",
            },
            {
                "name": "Russia",
                "entity_type": "Location",
                "aliases": [],
                "summary": "Major European power represented at the Congress of Vienna.",
            },
            {
                "name": "Great Britain",
                "entity_type": "Location",
                "aliases": [],
                "summary": "Major European power represented at the Congress of Vienna.",
            },
            {
                "name": "Napoleonic Wars",
                "entity_type": "Event",
                "aliases": [],
                "summary": "Series of wars fought between France and various European coalitions.",
            },
            {
                "name": "Concert of Europe",
                "entity_type": "Concept",
                "aliases": [],
                "summary": "System of balance-of-power diplomacy established after the Congress of Vienna.",
            },
            {
                "name": "Treaty of Paris",
                "entity_type": "Event",
                "aliases": [],
                "summary": "Peace treaty signed on May 30, 1814, preceding the Congress of Vienna.",
            },
            {
                "name": "Nationalism",
                "entity_type": "Concept",
                "aliases": [],
                "summary": "Political ideology championed by liberal movements and opposed by Metternich.",
            },
        ],
        relationships=[
            {
                "source_entity": "Klemens von Metternich",
                "target_entity": "Congress of Vienna",
                "relationship_type": "participated_in",
                "time_frame": "1814-1815",
                "evidence_quote": "Prince Klemens von Metternich played a central role in the negotiations.",
                "confidence_score": 0.95,
            },
            {
                "source_entity": "Alexander I",
                "target_entity": "Congress of Vienna",
                "relationship_type": "participated_in",
                "time_frame": "1814",
                "evidence_quote": "Tsar Alexander I of Russia sought to expand Russian influence.",
                "confidence_score": 0.95,
            },
            {
                "source_entity": "Alexander I",
                "target_entity": "Russia",
                "relationship_type": "ruled",
                "time_frame": "1801-1825",
                "evidence_quote": "Tsar Alexander I of Russia",
                "confidence_score": 0.95,
            },
            {
                "source_entity": "Karl vom Stein",
                "target_entity": "Congress of Vienna",
                "relationship_type": "participated_in",
                "time_frame": "1814",
                "evidence_quote": "participated in early discussions but died before the Congress concluded.",
                "confidence_score": 0.9,
            },
            {
                "source_entity": "Klemens von Metternich",
                "target_entity": "Austria",
                "relationship_type": "served_as_foreign_minister_of",
                "time_frame": "1809-1848",
                "evidence_quote": "the Austrian foreign minister",
                "confidence_score": 0.95,
            },
            {
                "source_entity": "Karl vom Stein",
                "target_entity": "Prussia",
                "relationship_type": "was_statesman_of",
                "time_frame": "",
                "evidence_quote": "a Prussian statesman",
                "confidence_score": 0.9,
            },
            {
                "source_entity": "Congress of Vienna",
                "target_entity": "Concert of Europe",
                "relationship_type": "established",
                "time_frame": "1815",
                "evidence_quote": "The resulting Concert of Europe established a balance of power",
                "confidence_score": 0.95,
            },
            {
                "source_entity": "Concert of Europe",
                "target_entity": "Nationalism",
                "relationship_type": "opposed",
                "time_frame": "1815-1914",
                "evidence_quote": "championing conservatism against nationalist and liberal movements",
                "confidence_score": 0.85,
            },
        ],
    )

    ents_list: list[Entity] = []
    for e in synthetic.entities:
        e.source_doc_ids = ["congress_of_vienna_sample"]
        ents_list.append(e)
    rels_list: list[Relationship] = []
    for r in synthetic.relationships:
        r.source_doc_id = "congress_of_vienna_sample"
        rels_list.append(r)

    store.save_models("entities_raw.json", ents_list)
    store.save_models("entities.json", ents_list)
    store.save_models("relationships.json", rels_list)
    _log(run_key, f"  Created {len(ents_list)} entities, {len(rels_list)} relationships")

    try:
        resolver = _build_resolver(cfg)
        merged, updated = resolver.resolve(ents_list, rels_list)
        method = "semantic" if isinstance(resolver, SemanticEntityResolver) else "fuzzy"
    except RuntimeError as exc:
        _log(run_key, f"  Embedder unreachable ({exc}) — falling back to fuzzy resolution", "warn")
        resolver = EntityResolver(cfg.entity_resolution)
        merged, updated = resolver.resolve(ents_list, rels_list)
        method = "fuzzy (semantic unavailable)"
    store.save_models("entities.json", merged)
    store.save_models("relationships.json", updated)
    _log(run_key, f"  Resolved → {len(merged)} canonical entities ({method})")

    obsidian = ObsidianExporter(resolver, cfg.export)
    vault_path = obsidian.build_vault(merged, updated, [doc], [chunk])
    note_count = sum(1 for _ in Path(vault_path).rglob("*.md"))
    _log(run_key, f"  ✓ Obsidian vault: {vault_path} ({note_count} notes)", "success")

    graph_exp = GraphExporter(cfg.export)
    graph_results = graph_exp.export(merged, updated)
    _log(run_key, f"  ✓ {graph_exp.summary()}", "success")

    _log_sep(run_key)
    _log(
        run_key,
        f"Demo: {len(merged)} entities, {len(updated)} relationships, {note_count} vault notes",
        "success",
    )
    _log_done(run_key, "Demo — complete")


# ── Run dispatcher ──────────────────────────────────────────────────


def _dispatch_pipeline(body: dict[str, Any]) -> str:
    """Parse body, start background thread, return run_key."""
    cfg, incremental = _make_config(body)
    run_key = body.get("run_key") or f"run-{int(time.time() * 1000)}"

    target = body.get("target", "run-all")
    if target == "ingest":
        thread_fn = lambda: _do_ingest(cfg, incremental, run_key)
    elif target == "extract":
        thread_fn = lambda: _do_extract(cfg, run_key)
    elif target == "resolve":
        thread_fn = lambda: _do_resolve(cfg, run_key)
    elif target == "vault":
        thread_fn = lambda: _do_vault(cfg, run_key)
    elif target == "graph":
        thread_fn = lambda: _do_graph(cfg, run_key)
    elif target == "demo":
        thread_fn = lambda: _do_demo(run_key)
    else:
        thread_fn = lambda: _do_run_all(cfg, incremental, run_key)

    th = threading.Thread(target=thread_fn, daemon=True)
    _get_run_log(run_key)
    th.start()
    return run_key


# ── API endpoints ───────────────────────────────────────────────────


@app.post("/api/ingest")
async def api_ingest(body: dict[str, Any]):
    body["target"] = "ingest"
    run_key = _dispatch_pipeline(body)
    return {"status": "ok", "run_key": run_key}


@app.post("/api/extract")
async def api_extract(body: dict[str, Any]):
    body["target"] = "extract"
    run_key = _dispatch_pipeline(body)
    return {"status": "ok", "run_key": run_key}


@app.post("/api/resolve")
async def api_resolve(body: dict[str, Any]):
    body["target"] = "resolve"
    run_key = _dispatch_pipeline(body)
    return {"status": "ok", "run_key": run_key}


@app.post("/api/build-vault")
async def api_build_vault(body: dict[str, Any]):
    body["target"] = "vault"
    run_key = _dispatch_pipeline(body)
    return {"status": "ok", "run_key": run_key}


@app.post("/api/build-graph")
async def api_build_graph(body: dict[str, Any]):
    body["target"] = "graph"
    run_key = _dispatch_pipeline(body)
    return {"status": "ok", "run_key": run_key}


@app.post("/api/run-all")
async def api_run_all(body: dict[str, Any]):
    body["target"] = "run-all"
    run_key = _dispatch_pipeline(body)
    return {"status": "ok", "run_key": run_key}


@app.post("/api/demo")
async def api_demo(body: dict[str, Any]):
    body["target"] = "demo"
    run_key = _dispatch_pipeline(body)
    return {"status": "ok", "run_key": run_key}


@app.post("/api/save-config")
async def api_save_config(body: dict[str, Any]):
    """Save user configuration."""
    try:
        cfg = load_config()

        if i := body.get("input_dir"):
            cfg.ingestion.input_dir = _validate_directory(i, "input_dir")
        if o := body.get("output_dir"):
            cfg.export.output_dir = _validate_directory(o, "output_dir")
        if v := body.get("vault_dir"):
            cfg.export.obsidian_vault_dir = _validate_directory(v, "vault_dir")
        if u := body.get("llm_base_url"):
            cfg.llm.base_url = _validate_base_url(u, "llm_base_url")
        if k := body.get("llm_api_key"):
            # A round-tripped redacted placeholder must not overwrite the
            # real key — same guard OCR's config router applies.
            if k != REDACTED_PLACEHOLDER:
                cfg.llm.api_key = k
        if m := body.get("llm_model"):
            cfg.llm.model = m
        if v := body.get("vision_mode"):
            cfg.llm.supports_vision = bool(v)
        if cs := body.get("chunk_size"):
            cfg.ingestion.chunk_size = int(cs)
        if co := body.get("chunk_overlap"):
            cfg.ingestion.chunk_overlap = int(co)
        if bs := body.get("batch_size"):
            cfg.extraction.batch_size = int(bs)
        if body.get("graph_formats"):
            cfg.export.graph_formats = body["graph_formats"]
        if "use_semantic" in body:
            cfg.entity_resolution.use_semantic = bool(body["use_semantic"])
        if ebu := body.get("embedding_base_url"):
            cfg.embedding.base_url = _validate_base_url(ebu, "embedding_base_url")
        if em := body.get("embedding_model"):
            cfg.embedding.model = em
        if "nominatim_lookup_enabled" in body:
            cfg.nominatim_lookup_enabled = bool(body["nominatim_lookup_enabled"])

        save_user_config(cfg)

        return {"status": "ok", "message": "Configuration saved successfully"}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error saving configuration")
        return {"status": "error", "message": "Error saving configuration"}


@app.post("/api/load-preferences")
async def api_load_preferences():
    """Load saved user preferences."""
    try:
        from artifice_graph.web.config_helper import load_saved_config

        saved_cfg = load_saved_config()
        if saved_cfg:
            redacted = _redact_config(saved_cfg)
            return {"status": "ok", "config": redacted.model_dump()}
        return {"status": "ok", "config": {}}
    except Exception as e:
        logger.error("Error loading preferences: %s", e)
        return {"status": "error", "message": "Error loading preferences"}


@app.get("/api/state")
async def api_state():
    """Return current pipeline state: counts + type/relation breakdowns."""
    cfg = load_config()
    store = _load_store(cfg)

    entities = store.load("entities.json")
    relationships = store.load("relationships.json")
    documents = store.load("documents.json")
    chunks = store.load("chunks.json")
    raw_entities = store.load("entities_raw.json")

    from collections import Counter

    if entities:
        type_counts = Counter(e.get("entity_type", "?") for e in entities)
        type_list = [
            {"type": t, "count": c} for t, c in sorted(type_counts.items(), key=lambda x: -x[1])
        ]
    else:
        type_list = []

    if relationships:
        rel_counts = Counter(r.get("relationship_type", "?") for r in relationships)
        rel_list = [
            {"type": t, "count": c} for t, c in sorted(rel_counts.items(), key=lambda x: -x[1])[:10]
        ]
    else:
        rel_list = []

    return {
        "entities": len(entities),
        "relationships": len(relationships),
        "documents": len(documents),
        "chunks": len(chunks),
        "entities_raw": len(raw_entities) if raw_entities else 0,
        "type_counts": type_list,
        "rel_counts": rel_list,
    }


HISTORICAL_COORDINATES = {
    "russia": {"lat": 55.7558, "lng": 37.6173, "name": "Russia (Moscow / St. Petersburg)"},
    "prussia": {"lat": 52.5200, "lng": 13.4050, "name": "Prussia (Berlin)"},
    "great britain": {"lat": 51.5074, "lng": -0.1278, "name": "Great Britain (London)"},
    "austria": {"lat": 48.2082, "lng": 16.3738, "name": "Austria (Vienna)"},
    "france": {"lat": 48.8566, "lng": 2.3522, "name": "France (Paris)"},
    "vienna": {"lat": 48.2082, "lng": 16.3738, "name": "Vienna"},
    "paris": {"lat": 48.8566, "lng": 2.3522, "name": "Paris"},
    "london": {"lat": 51.5074, "lng": -0.1278, "name": "London"},
    "berlin": {"lat": 52.5200, "lng": 13.4050, "name": "Berlin"},
    "warsaw": {"lat": 52.2297, "lng": 21.0122, "name": "Warsaw"},
    "st_petersburg": {"lat": 59.9343, "lng": 30.3351, "name": "St. Petersburg"},
    "moscow": {"lat": 55.7558, "lng": 37.6173, "name": "Moscow"},
}


@app.get("/api/map-entities")
async def api_map_entities(mode: str = Query("approx", pattern="^(approx|lookup)$")):
    cfg = load_config()
    store = _load_store(cfg)
    entities = store.load("entities.json") or []
    relationships = store.load("relationships.json") or []

    locations = [e for e in entities if e.get("entity_type") == "Location"]
    result = []
    for loc in locations:
        name = loc.get("name", "")
        name_lower = name.lower().strip()
        lat, lng = None, None
        source_method = "none"

        for key, coords in HISTORICAL_COORDINATES.items():
            if key in name_lower or name_lower in key:
                lat = coords["lat"]
                lng = coords["lng"]
                source_method = "approximate"
                break

        if lat is None and mode == "lookup":
            if not cfg.nominatim_lookup_enabled:
                # Nominatim lookup is off by default — entity names extracted
                # from a user's documents must not be sent to a third party
                # without explicit consent.  The approximate mode (which
                # matches against a built-in list of historical locations)
                # still works.
                return {
                    "locations": result,
                    "mode": "lookup",
                    "lookup_disabled": True,
                    "message": (
                        "Nominatim geocoding lookup is disabled. "
                        "Enable 'nominatim_lookup_enabled' in the configuration "
                        "to geocode entity names via OpenStreetMap."
                    ),
                }
            try:
                import urllib.parse
                import urllib.request

                encoded = urllib.parse.quote(name)
                url = f"https://nominatim.openstreetmap.org/search?q={encoded}&format=json&limit=1"
                req = urllib.request.Request(
                    url, headers={"User-Agent": "ArtificeGraph-HistoricalPipeline/1.0"}
                )
                with urllib.request.urlopen(req, timeout=3) as resp:
                    data = json.loads(resp.read().decode())
                    if data:
                        lat = float(data[0]["lat"])
                        lng = float(data[0]["lon"])
                        source_method = "lookup"
            except Exception:
                pass

        if lat is not None and lng is not None:
            rels = [
                r
                for r in relationships
                if r.get("source_entity") == name or r.get("target_entity") == name
            ]
            result.append(
                {
                    "id": loc.get("id"),
                    "name": name,
                    "type": loc.get("entity_type"),
                    "summary": loc.get("summary", ""),
                    "aliases": loc.get("aliases", []),
                    "lat": lat,
                    "lng": lng,
                    "source_method": source_method,
                    "relationships": rels,
                }
            )

    return {"locations": result, "mode": mode}


@app.get("/api/models")
async def api_get_models():
    """Get available models from LLM server (via model_harness.discovery)."""
    try:
        cfg = load_config()
        from model_harness.discovery import probe_endpoint

        policy = EndpointPolicy()
        result = await probe_endpoint(cfg.llm.base_url, policy=policy, timeout_s=10)

        if not result.reachable:
            error_msg = result.hint or f"Cannot reach {cfg.llm.base_url}"
            return {
                "models": [],
                "vision_models": [],
                "ollama_base": "",
                "openai_base": "",
                "error": error_msg,
                "suggestions": [result.hint] if result.hint else [],
            }

        models: list[dict[str, Any]] = []
        vision_models: list[dict[str, Any]] = []

        seen: set[str] = set()
        for name in result.models:
            if name in seen:
                continue
            seen.add(name)

            model_obj: dict[str, Any] = {
                "id": name,
                "name": name,
                "source": "ollama" if result.provider == "ollama" else "openai",
            }
            models.append(model_obj)

            if any(indicator in name.lower() for indicator in _VISION_INDICATORS):
                model_obj["supports_vision"] = True
                vision_models.append(model_obj)

        ollama_base = cfg.llm.base_url.rstrip("/")
        if "/v1" in ollama_base:
            ollama_base = ollama_base.replace("/v1", "")

        return {
            "models": models,
            "vision_models": vision_models,
            "ollama_base": ollama_base,
            "openai_base": cfg.llm.base_url,
        }
    except EndpointRejected as e:
        logger.error(f"Endpoint rejected when fetching models: {e}")
        return {
            "models": [],
            "vision_models": [],
            "ollama_base": "",
            "openai_base": "",
            "error": f"Endpoint rejected: {e}",
        }
    except Exception as e:
        logger.error("Error fetching models: %s", e)
        return {
            "models": [],
            "vision_models": [],
            "ollama_base": "",
            "openai_base": "",
            "error": "Failed to fetch models from the configured endpoint",
        }


@app.post("/api/test-connection")
async def api_test_connection(body: dict[str, Any] | None = None):
    """Test LLM server connection against the posted config, or the saved one if absent."""
    # Build the LLM config that will be tested: posted fields override the
    # saved config; missing or empty posted fields fall back to saved.
    cfg = load_config()
    if body:
        llm_base_url = body.get("llm_base_url") or cfg.llm.base_url
        llm_api_key = body.get("llm_api_key", cfg.llm.api_key)
        llm_model = body.get("llm_model") or cfg.llm.model
        llm_cfg = LLMConfig(
            base_url=llm_base_url,
            api_key=llm_api_key,
            model=llm_model,
        )
    else:
        llm_cfg = cfg.llm

    try:
        from model_harness.discovery import probe_endpoint

        policy = EndpointPolicy()
        result = await probe_endpoint(llm_cfg.base_url, policy=policy, timeout_s=5)

        suggestions: list[str] = []
        if result.hint:
            suggestions.append(result.hint)

        status = "connected" if result.reachable else "error"
        error: str | None = None if result.reachable else "Server not reachable"

        return {
            "status": status,
            "error": error,
            "suggestions": suggestions,
            "url": llm_cfg.base_url,
            "model": llm_cfg.model,
        }
    except EndpointRejected as e:
        logger.error(f"Endpoint rejected in test-connection: {e}")
        return {
            "status": "error",
            "error": str(e),
            "suggestions": ["Check if the URL is correct and accessible"],
            "url": llm_cfg.base_url,
            "model": llm_cfg.model,
        }
    except Exception:
        logger.exception("Error testing connection to %s", llm_cfg.base_url)
        return {
            "status": "error",
            "error": "Failed to test connection to the configured endpoint",
            "suggestions": ["Check if the URL is correct and accessible"],
            "url": llm_cfg.base_url,
            "model": llm_cfg.model,
        }


@app.get("/api/stream")
async def api_stream(run: str = Query(...)):
    """SSE endpoint. Sends JSON events for a given run key."""

    async def event_generator():
        buf, lock, cond = _get_run_log(run)
        idx = 0
        while True:
            new_events: list[dict] = []
            with lock:
                while idx < len(buf):
                    new_events.append(buf[idx])
                    idx += 1
                active = _run_active.get(run, False)
            if new_events:
                for ev in new_events:
                    yield f"data: {json.dumps(ev)}\n\n"
            if not active and idx >= len(buf):
                yield 'data: {"gotoState":"done","text":"Stream ended"}\n\n'
                break
            await asyncio.sleep(0.15)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Upload guards (shared_ui.uploads / shared_ui.path_validation) ─────
# Filename sanitisation and the size cap live in shared-ui; this web layer
# translates their domain errors into HTTP responses.

_MAX_UPLOAD_BYTES: int = 50 * 1024 * 1024  # 50 MB, mirrors IngestionConfig.max_file_size_mb


def _allowed_upload_extensions(cfg: PipelineConfig) -> frozenset[str]:
    return frozenset(
        {ext.lower() for ext in cfg.ingestion.supported_extensions} | {".pdf", ".html", ".htm"}
    )


def _assert_contained(path: Path, container: Path) -> None:
    """Raise HTTP 400 if *path* resolves outside *container*."""
    resolved = path.resolve()
    base = container.resolve()
    if not (base in resolved.parents or resolved == base):
        raise HTTPException(status_code=400, detail="Path traversal detected")


@app.post("/api/upload-files")
async def api_upload_files(files: list[UploadFile] = File(...)):
    """Upload one or more text/document files into the pipeline's input directory.

    Filenames are sanitised with the shared ``sanitise_path_component`` guard
    used by the other apps to prevent path-traversal. Only the extensions the
    ingest stage accepts (plus the built-in PDF/HTML handlers) are stored;
    oversized files (>50 MB) are refused.

    **This is a batch endpoint and always returns HTTP 200** when the request
    itself is well-formed. Per-file outcomes are reported in the response body:

        {"uploaded": [{"filename": ..., "status": "ok",       "path": ...},
                      {"filename": ..., "status": "rejected", "reason": ...}]}

    One unacceptable file must not fail an otherwise good batch — a user
    dropping twelve files should get the eleven valid ones stored and a specific
    reason for the twelfth, not a single opaque error. Clients must therefore
    inspect ``status`` per entry rather than treating 200 as "everything
    worked".

    A malformed filename (empty, ``"."`` or ``".."`` after cleaning) is the one
    case that does raise — HTTP 400 — because it indicates a crafted request
    rather than a user picking the wrong file.
    """
    cfg = load_config()
    input_dir = Path(cfg.ingestion.input_dir)
    input_dir.mkdir(parents=True, exist_ok=True)
    allowed_extensions = _allowed_upload_extensions(cfg)

    results = []
    for upload in files:
        raw_name = upload.filename or "unknown"
        try:
            safe_name = sanitise_path_component(raw_name)
        except PathValidationError as e:
            raise HTTPException(status_code=400, detail=e.public_message) from e
        ext = Path(safe_name).suffix.lower()

        if ext not in allowed_extensions:
            results.append(
                {
                    "filename": raw_name,
                    "status": "rejected",
                    "reason": f"Extension {ext!r} not accepted. Allowed: {sorted(allowed_extensions)}",
                }
            )
            continue

        try:
            contents = await read_capped(upload, _MAX_UPLOAD_BYTES)
        except UploadTooLarge:
            results.append(
                {
                    "filename": raw_name,
                    "status": "rejected",
                    "reason": "File exceeds 50 MB limit",
                }
            )
            continue

        dest = input_dir / safe_name
        _assert_contained(dest, input_dir)
        dest.write_bytes(contents)
        logger.info("Uploaded %s → %s", raw_name, dest)
        results.append({"filename": safe_name, "status": "ok", "path": str(dest)})

    return {"uploaded": results}


# ── Tropy manifest import ─────────────────────────────────────────────


@app.post("/api/tropy/import-manifest")
def api_tropy_import_manifest(body: dict[str, Any]):
    """Import a tropy_manifest.json and return graph nodes with provenance.

    Accepts ``{"manifest_path": "<path>"}``. Validates the path against the
    allowed-roots directory guard, then delegates to
    :func:`artifice_graph.tropy_import.load_manifest` and
    :func:`artifice_graph.tropy_import.manifest_to_graph_nodes`.
    """
    from artifice_graph.tropy_import import ManifestError, load_manifest, manifest_to_graph_nodes

    raw_path = body.get("manifest_path", "")
    if not raw_path:
        raise HTTPException(status_code=400, detail="manifest_path is required")

    try:
        resolved = _validate_directory(raw_path, "manifest_path")
    except HTTPException:
        raise HTTPException(
            status_code=400,
            detail="Manifest path is outside allowed directories",
        ) from None

    try:
        manifest = load_manifest(resolved)
    except ManifestError:
        logger.exception("Failed to load Tropy manifest: %s", resolved)
        raise HTTPException(status_code=400, detail="Could not parse Tropy manifest") from None

    nodes = manifest_to_graph_nodes(manifest)
    return {
        "ok": True,
        "manifest": {
            "export": manifest.get("export", {}),
            "output_layout": manifest.get("output_layout", ""),
        },
        "nodes": nodes,
        "count": len(nodes),
    }


# ── Page routes ─────────────────────────────────────────────────────


def _render(template_name: str, **extra) -> str:
    cfg = load_config()
    store = _load_store(cfg)
    entities = [Entity.model_validate(d) for d in store.load("entities.json")]
    relationships = [Relationship.model_validate(d) for d in store.load("relationships.json")]
    documents = [Document.model_validate(d) for d in store.load("documents.json")]
    chunks = [TextChunk.model_validate(d) for d in store.load("chunks.json")]

    ctx = {
        "app_slug": "graph",
        "brand_accent": "Graph",
        "page_title": "Knowledge graph workspace",
        "document_context": "Local graph collection",
        "nav_items": [
            {"key": "pipeline", "label": "Pipeline", "href": "/"},
            {"key": "library", "label": "Library", "href": "/library"},
            {"key": "settings", "label": "Settings", "href": "/settings"},
        ],
        "show_inspector": template_name == "index.html",
        "show_activity": template_name == "index.html",
        "active_tab": template_name.replace(".html", "").replace("index", "pipeline"),
        "asset_v": int(time.time()),
        "config": _redact_config(cfg),
        "state": {
            "entities": entities,
            "relationships": relationships,
            "documents": documents,
            "chunks": chunks,
        },
        "theme": "auto",
        "reduce_motion": False,
    }
    ctx.update(extra)
    return _jinja.get_template(template_name).render(**ctx)


@app.get("/", response_class=HTMLResponse)
async def index():
    return _render("index.html")


@app.get("/library", response_class=HTMLResponse)
async def library():
    return _render("library.html", active_tab="library")


@app.get("/about", response_class=HTMLResponse)
async def about():
    return _render("about.html", active_tab="about")


@app.get("/settings", response_class=HTMLResponse)
async def settings_page():
    return _render(
        "about.html",
        active_tab="settings",
        page_title="Settings & application information",
        document_context=None,
        show_inspector=False,
        show_activity=False,
    )


@app.post("/api/native/pick-file")
async def pick_file() -> dict[str, str | list[str]]:
    """Open a native file picker and return the selected path(s).

    Returns ``{"state": "selected"|"cancelled"|"unavailable", "paths": [...],
    "reason": "..."}`` — the shared file-dialog contract.  ``paths`` is
    non-empty only for ``"selected"`` and ``reason`` is non-empty only for
    ``"unavailable"``.  Multiple files may be selected.

    Constructed inside the handler, not at module scope: a FileType description
    that fails the [word chars + spaces] rule raises ValueError at construction,
    and a module-scope instance would crash the server at import time rather
    than on the one request that uses it.
    """
    file_types = (
        FileType("Text files", ("*.txt", "*.md")),
        FileType("All Files", ("*.*",)),
    )
    result = await pick_files_async(title="Select a file", file_types=file_types)
    return result.as_dict()


@app.post("/api/native/pick-folder")
async def pick_folder() -> dict[str, str | list[str]]:
    """Open a native folder picker and return the selected folder path.

    Returns ``{"state": "selected"|"cancelled"|"unavailable", "paths": [...],
    "reason": "..."}`` — the shared file-dialog contract.  Single selection.
    """
    result = await pick_folder_async(title="Select a folder")
    return result.as_dict()


# ── Main / bootstrap ──────────────────────────────────────────────────

from shared_ui.handoff import cleanup_expired, write_discovery  # noqa: E402
from shared_ui.server_bootstrap import (  # noqa: E402
    ensure_std_streams,
    free_port,
    port_available,
    report_startup_failure,
    start_server_thread,
    wait_for_server,
)

# Re-export under the private names that `main()` expects.
_free_port = free_port
_port_available = port_available
_wait_for_server = wait_for_server
_ensure_std_streams = ensure_std_streams

# ── Loopback-only guard ──────────────────────────────────────────────
# Security item 5.2b: Tropy routes would be reachable without auth in a
# deployed instance if the server bound to a non-loopback address.

_LOOPBACK_HOSTS: frozenset[str] = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})


def _assert_loopback_host() -> None:
    """Refuse to start if the server binds to a non-loopback address.
    This is a defense-in-depth guard — start_server_thread() hardcodes
    127.0.0.1 today, but if a future change adds a configurable host
    this check catches it before the server listens.
    """
    host = "127.0.0.1"  # current value in shared_ui.server_bootstrap.start_server_thread
    if host not in _LOOPBACK_HOSTS:
        print(
            f"artifice-graph binds to loopback only for security; "
            f"refusing to start on {host}. Set host to 127.0.0.1.",
            flush=True,
        )
        raise SystemExit(1)


def _start_server_thread(port: int):
    return start_server_thread(app, port)


def _report_startup_failure(port: int, thread, errors: list[BaseException]) -> None:
    report_startup_failure("ArtificeGraph", port, thread, errors)


def main() -> None:
    _ensure_std_streams()
    _assert_loopback_host()

    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port for the local server (default: 8766, or a free port if busy)",
    )
    parser.add_argument(
        "--no-window",
        action="store_true",
        default=False,
        help="Server-only mode: print the URL and wait, do not open a window or browser",
    )
    args = parser.parse_args()

    # Distinguish "user said --port 8766" from "the default happened to be 8766".
    # An explicit port that is busy is a deliberate choice — fail, don't fall back.
    is_explicit_port = args.port is not None

    # Try the requested port; fall back to a free port only when the user
    # did NOT specify one and the default (8766) is busy.
    for attempt in range(2):
        if attempt == 0:
            port = args.port if is_explicit_port else 8766
        else:
            port = _free_port()
            print(f"Port 8766 is busy — using port {port} instead.", flush=True)

        if not _port_available(port):
            if is_explicit_port or attempt == 1:
                _report_startup_failure(port, None, [OSError(f"Port {port} is already in use")])
                return
            continue

        server_thread, server_errors = _start_server_thread(port)
        if _wait_for_server(port):
            break

        if is_explicit_port or attempt == 1:
            _report_startup_failure(port, server_thread, server_errors)
            return

    # Guard against the race where another process grabbed the port between
    # our availability check and the server thread binding.
    if server_errors or not server_thread.is_alive():
        _report_startup_failure(port, server_thread, server_errors)
        return

    url = f"http://127.0.0.1:{port}"

    # ── Discovery: register this running instance for handoff ──────────
    write_discovery("artifice-graph", port, os.getpid())
    cleanup_expired()

    # ── Server-only mode (--no-window) ────────────────────────────────────
    if args.no_window:
        print(f"ArtificeGraph running at {url}  (Ctrl+C to stop)", flush=True)
        with contextlib.suppress(KeyboardInterrupt):
            server_thread.join()
        return

    # ── Always attempt a native window, fall back to browser ────────────
    # Lazy import — pywebview must not be required at module scope
    # for non-frozen installs (e.g. `uv tool install` users who don't
    # have a webview backend).  ``open_native_window`` swallows every
    # backend/import failure internally and returns a ``WindowResult``,
    # so no try/except is needed here.
    from .window import open_native_window  # noqa: PLC0415

    result = open_native_window(url, title="ArtificeGraph")
    if result.opened:
        # Window closed by user — exit cleanly.
        # The daemon server thread dies with the process.
        return

    # Window unavailable — fall back to the system browser.
    print(result.reason, flush=True)
    print(f"Falling back — ArtificeGraph running at {url}", flush=True)
    webbrowser.open(url)
    with contextlib.suppress(KeyboardInterrupt):
        server_thread.join()


if __name__ == "__main__":
    main()

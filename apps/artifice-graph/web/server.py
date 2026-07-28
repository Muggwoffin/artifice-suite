"""FastAPI web server for ArtificeGraph — pipeline control + SSE log streaming + state API."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

import httpx
import uvicorn
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

# ── Ensure src is importable ───────────────────────────────────────
_PROJECT = Path(__file__).resolve().parent.parent
_SRC = _PROJECT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from artifice_graph.config import PipelineConfig, load_config
from artifice_graph.embedding.bge_embedder import BGEM3Embedder
from artifice_graph.entity_resolution.resolver import EntityResolver
from artifice_graph.entity_resolution.semantic_resolver import SemanticEntityResolver
from artifice_graph.exporters.graph_exporter import GraphExporter
from artifice_graph.exporters.obsidian_exporter import ObsidianExporter
from artifice_graph.extraction.extractor import EntityExtractor
from artifice_graph.extraction.llm_client import LLMClient
from artifice_graph.ingestion.chunker import TextChunker
from artifice_graph.models.document import Document, TextChunk
from artifice_graph.models.entity import Entity, EntityType
from artifice_graph.models.relationship import Relationship
from artifice_graph.storage.file_store import FileStore
from web.config_helper import load_saved_config, save_user_config

logger = logging.getLogger(__name__)

# ── App setup ──────────────────────────────────────────────────────

app = FastAPI(title="ArtificeGraph", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://localhost:{os.environ.get('CALLOSIP_PORT', '8766')}",
        f"http://127.0.0.1:{os.environ.get('CALLOSIP_PORT', '8766')}",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

HERE = Path(__file__).resolve().parent

# Jinja2
_jinja = Environment(
    loader=FileSystemLoader(str(HERE / "templates")),
    autoescape=select_autoescape(["html", "xml"]),
)

# Static files
app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")

# ── Shared design tokens (canonical source: packages/shared-ui) ────
_SHARED_UI = _PROJECT.parent.parent / "packages" / "shared-ui"
if not _SHARED_UI.is_dir():
    raise RuntimeError(
        f"Shared UI directory not found at {_SHARED_UI.resolve()}. "
        "Ensure packages/shared-ui/ exists in the monorepo root."
    )
app.mount("/shared", StaticFiles(directory=str(_SHARED_UI)), name="shared")

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


# ── Config from POST body ──────────────────────────────────────────

def _make_config(body: dict[str, Any]) -> tuple[PipelineConfig, bool]:
    cfg = load_config()
    if i := body.get("input_dir"):
        cfg.ingestion.input_dir = i
    if o := body.get("output_dir"):
        cfg.export.output_dir = o
    if v := body.get("vault_dir"):
        cfg.export.obsidian_vault_dir = v
    if u := body.get("llm_base_url"):
        cfg.llm.base_url = u
    if k := body.get("llm_api_key"):
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
        cfg.embedding.base_url = ebu
    if em := body.get("embedding_model"):
        cfg.embedding.model = em
    return cfg, bool(body.get("incremental", False))


def _build_resolver(cfg: PipelineConfig) -> EntityResolver | SemanticEntityResolver:
    if cfg.entity_resolution.use_semantic:
        embedder = BGEM3Embedder(cfg.embedding)
        return SemanticEntityResolver(embedder=embedder, config=cfg.entity_resolution)
    return EntityResolver(cfg.entity_resolution)


def _load_store(cfg: PipelineConfig) -> FileStore:
    return FileStore(cfg.export.output_dir)


# ── Pipeline runner helpers (worker thread) ────────────────────────

def _do_ingest(cfg: PipelineConfig, incremental: bool, run_key: str, *, close_stream: bool = True) -> None:
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
            store.save("content_hashes.json", [{"id": k, "content_hash": v} for k, v in new_hashes.items()])
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
    _log_done(run_key, f"Ingest: {len(documents)} docs, {len(chunks)} chunks", close_stream=close_stream)


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
        batch = chunks[i:i + batch_size]
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
        _log(run_key, "  Run with --force from the CLI to overwrite, or fix LLM connectivity.", "dim")
    else:
        store.save_models("entities.json", all_entities)
    existing_rels = store.load("relationships.json")
    if existing_rels and not all_rels:
        _log(run_key, "  Refusing to overwrite non-empty relationships.json with empty data.", "warn")
    else:
        store.save_models("relationships.json", all_rels)
    _log(run_key, f"  ✓ Extracted {len(all_entities)} entities, {len(all_rels)} relationships", "success")
    _log_done(run_key, f"Extract: {len(all_entities)} entities, {len(all_rels)} relationships", close_stream=close_stream)


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
        _mark_run_failed(run_key, f"Resolve — embedder error during resolution")
        _log_done(run_key, "Resolve — failed (embedder error)", close_stream=close_stream)
        return
    if not merged:
        _log(run_key, "  Refusing to overwrite non-empty entities.json with empty resolution result.", "warn")
    else:
        store.save_models("entities.json", merged)
    if not updated:
        _log(run_key, "  Refusing to overwrite non-empty relationships.json with empty resolution result.", "warn")
    else:
        store.save_models("relationships.json", updated)
    _log(run_key, f"  ✓ {len(entities)} → {len(merged)} canonical entities ({method})", "success")
    _log_done(run_key, f"Resolve: {len(entities)} → {len(merged)} canonical", close_stream=close_stream)


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
            {"name": "Klemens von Metternich", "entity_type": "Person", "aliases": ["Metternich", "Prince Metternich"],
             "summary": "Austrian foreign minister and central figure at the Congress of Vienna."},
            {"name": "Alexander I", "entity_type": "Person", "aliases": ["Tsar Alexander I"],
             "summary": "Tsar of Russia who sought expanded influence at the Congress of Vienna."},
            {"name": "Karl vom Stein", "entity_type": "Person", "aliases": ["Baron Stein", "Baron vom Stein"],
             "summary": "Prussian statesman who participated in early Congress discussions but died before its conclusion."},
            {"name": "Congress of Vienna", "entity_type": "Event", "aliases": ["The Congress"],
             "summary": "Diplomatic conference held in 1814 to reorganize Europe after the Napoleonic Wars."},
            {"name": "Austria", "entity_type": "Location", "aliases": ["Austrian Empire"],
             "summary": "Major European power and host nation of the Congress of Vienna."},
            {"name": "Prussia", "entity_type": "Location", "aliases": [],
             "summary": "German state that participated in the Congress of Vienna."},
            {"name": "Russia", "entity_type": "Location", "aliases": [],
             "summary": "Major European power represented at the Congress of Vienna."},
            {"name": "Great Britain", "entity_type": "Location", "aliases": [],
             "summary": "Major European power represented at the Congress of Vienna."},
            {"name": "Napoleonic Wars", "entity_type": "Event", "aliases": [],
             "summary": "Series of wars fought between France and various European coalitions."},
            {"name": "Concert of Europe", "entity_type": "Concept", "aliases": [],
             "summary": "System of balance-of-power diplomacy established after the Congress of Vienna."},
            {"name": "Treaty of Paris", "entity_type": "Event", "aliases": [],
             "summary": "Peace treaty signed on May 30, 1814, preceding the Congress of Vienna."},
            {"name": "Nationalism", "entity_type": "Concept", "aliases": [],
             "summary": "Political ideology championed by liberal movements and opposed by Metternich."},
        ],
        relationships=[
            {"source_entity": "Klemens von Metternich", "target_entity": "Congress of Vienna",
             "relationship_type": "participated_in", "time_frame": "1814-1815",
             "evidence_quote": "Prince Klemens von Metternich played a central role in the negotiations.", "confidence_score": 0.95},
            {"source_entity": "Alexander I", "target_entity": "Congress of Vienna",
             "relationship_type": "participated_in", "time_frame": "1814",
             "evidence_quote": "Tsar Alexander I of Russia sought to expand Russian influence.", "confidence_score": 0.95},
            {"source_entity": "Alexander I", "target_entity": "Russia",
             "relationship_type": "ruled", "time_frame": "1801-1825",
             "evidence_quote": "Tsar Alexander I of Russia", "confidence_score": 0.95},
            {"source_entity": "Karl vom Stein", "target_entity": "Congress of Vienna",
             "relationship_type": "participated_in", "time_frame": "1814",
             "evidence_quote": "participated in early discussions but died before the Congress concluded.", "confidence_score": 0.9},
            {"source_entity": "Klemens von Metternich", "target_entity": "Austria",
             "relationship_type": "served_as_foreign_minister_of", "time_frame": "1809-1848",
             "evidence_quote": "the Austrian foreign minister", "confidence_score": 0.95},
            {"source_entity": "Karl vom Stein", "target_entity": "Prussia",
             "relationship_type": "was_statesman_of", "time_frame": "",
             "evidence_quote": "a Prussian statesman", "confidence_score": 0.9},
            {"source_entity": "Congress of Vienna", "target_entity": "Concert of Europe",
             "relationship_type": "established", "time_frame": "1815",
             "evidence_quote": "The resulting Concert of Europe established a balance of power", "confidence_score": 0.95},
            {"source_entity": "Concert of Europe", "target_entity": "Nationalism",
             "relationship_type": "opposed", "time_frame": "1815-1914",
             "evidence_quote": "championing conservatism against nationalist and liberal movements", "confidence_score": 0.85},
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
    _log(run_key, f"Demo: {len(merged)} entities, {len(updated)} relationships, {note_count} vault notes", "success")
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
            cfg.ingestion.input_dir = i
        if o := body.get("output_dir"):
            cfg.export.output_dir = o
        if v := body.get("vault_dir"):
            cfg.export.obsidian_vault_dir = v
        if u := body.get("llm_base_url"):
            cfg.llm.base_url = u
        if k := body.get("llm_api_key"):
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
            cfg.embedding.base_url = ebu
        if em := body.get("embedding_model"):
            cfg.embedding.model = em

        save_user_config(cfg)

        return {"status": "ok", "message": "Configuration saved successfully"}
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        return {"status": "error", "message": f"Error saving configuration: {str(e)}"}


@app.post("/api/load-preferences")
async def api_load_preferences():
    """Load saved user preferences."""
    try:
        from web.config_helper import load_saved_config
        saved_cfg = load_saved_config()
        if saved_cfg:
            return {"status": "ok", "config": saved_cfg.model_dump()}
        return {"status": "ok", "config": {}}
    except Exception as e:
        logger.error(f"Error loading preferences: {e}")
        return {"status": "error", "message": f"Error loading preferences: {str(e)}"}


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
        type_list = [{"type": t, "count": c} for t, c in sorted(type_counts.items(), key=lambda x: -x[1])]
    else:
        type_list = []

    if relationships:
        rel_counts = Counter(r.get("relationship_type", "?") for r in relationships)
        rel_list = [{"type": t, "count": c} for t, c in sorted(rel_counts.items(), key=lambda x: -x[1])[:10]]
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
            try:
                import urllib.parse
                import urllib.request
                encoded = urllib.parse.quote(name)
                url = f"https://nominatim.openstreetmap.org/search?q={encoded}&format=json&limit=1"
                req = urllib.request.Request(url, headers={"User-Agent": "ArtificeGraph-HistoricalPipeline/1.0"})
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
                r for r in relationships
                if r.get("source_entity") == name or r.get("target_entity") == name
            ]
            result.append({
                "id": loc.get("id"),
                "name": name,
                "type": loc.get("entity_type"),
                "summary": loc.get("summary", ""),
                "aliases": loc.get("aliases", []),
                "lat": lat,
                "lng": lng,
                "source_method": source_method,
                "relationships": rels
            })

    return {"locations": result, "mode": mode}


@app.get("/api/models")
async def api_get_models():
    """Get available models from LLM server."""
    try:
        cfg = load_config()
        llm = LLMClient(cfg.llm)

        async with httpx.AsyncClient(timeout=10) as client:
            ollama_base = cfg.llm.base_url.rstrip("/")

            if "/v1" in ollama_base:
                ollama_base = ollama_base.replace("/v1", "")

            models = []
            vision_models = []

            try:
                resp = await client.get(f"{ollama_base}/api/tags", timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    for model_info in data.get("models", []):
                        model_obj = {
                            "id": model_info.get("name", ""),
                            "name": model_info.get("name", ""),
                            "source": "ollama"
                        }
                        models.append(model_obj)

                        model_name = str(model_info.get("name", "")).lower()
                        vision_indicators = ["vision", "vl", "multi-modal", "image", "visual"]
                        if any(indicator in model_name for indicator in vision_indicators):
                            model_obj["supports_vision"] = True
                            vision_models.append(model_obj)
            except Exception:
                pass

            try:
                if "api.openai.com" in cfg.llm.base_url:
                    resp = await client.get(
                        f"{cfg.llm.base_url}/v1/models",
                        headers={"Authorization": f"Bearer {cfg.llm.api_key}" if cfg.llm.api_key else None},
                        timeout=10
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        for model_info in data.get("data", []):
                            model_obj = {
                                "id": model_info.get("id", ""),
                                "name": model_info.get("name", model_info.get("id", "")),
                                "source": "openai"
                            }
                            models.append(model_obj)

                            model_id = model_info.get("id", "").lower()
                            vision_indicators = ["vision", "vl", "multi-modal", "image", "visual"]
                            if any(indicator in model_id for indicator in vision_indicators):
                                model_obj["supports_vision"] = True
                                vision_models.append(model_obj)
            except Exception:
                pass

            await llm.close()

        return {
            "models": models,
            "vision_models": vision_models,
            "ollama_base": ollama_base,
            "openai_base": cfg.llm.base_url,
        }
    except Exception as e:
        logger.error(f"Error fetching models: {e}")
        return {
            "models": [],
            "vision_models": [],
            "ollama_base": "",
            "openai_base": "",
            "error": str(e)
        }


@app.get("/api/test-connection")
async def api_test_connection():
    """Test LLM server connection."""
    try:
        cfg = load_config()
        llm = LLMClient(cfg.llm)

        async with httpx.AsyncClient(timeout=5) as client:
            ollama_base = cfg.llm.base_url.rstrip("/")
            if "/v1" in ollama_base:
                ollama_base = ollama_base.replace("/v1", "")

            status = "error"
            error = "Server not reachable"
            suggestions = []

            try:
                resp = await client.get(ollama_base, timeout=5)
                if resp.status_code == 200:
                    status = "connected"
                    error = None
                else:
                    status = "error"
                    error = f"Server responded with status {resp.status_code}"
            except httpx.ConnectError as e:
                status = "error"
                error = f"Connection failed: {str(e)}"
                if "11434" in ollama_base:
                    suggestions.extend([
                        "Make sure Ollama server is running: 'ollama serve'",
                        "Set OLLAMA_ORIGINS=* to allow cross-origin requests"
                    ])
                elif "1234" in ollama_base:
                    suggestions.append("Ensure LM Studio server is running and accessible")

            try:
                if "api.openai.com" in cfg.llm.base_url:
                    resp = await client.get(
                        f"{cfg.llm.base_url}/v1/models",
                        headers={"Authorization": f"Bearer {cfg.llm.api_key}" if cfg.llm.api_key else None},
                        timeout=5
                    )
                    if resp.status_code == 200:
                        if status == "connected":
                            status = "connected"
                        else:
                            status = "partial"
                        error = None
                    else:
                        if status == "connected":
                            status = "partial"
                        else:
                            status = "error"
                        error = f"OpenAI API error: {resp.status_code}"
            except Exception as e:
                if status == "connected":
                    status = "partial"
                else:
                    status = "error"
                error = error or f"OpenAI API check failed: {str(e)}"

            await llm.close()

        return {
            "status": status,
            "error": error,
            "suggestions": suggestions,
            "url": cfg.llm.base_url,
            "model": cfg.llm.model,
        }
    except Exception as e:
        logger.error(f"Error testing connection: {e}")
        return {
            "status": "error",
            "error": str(e),
            "suggestions": ["Check if the URL is correct and accessible"],
            "url": load_config().llm.base_url,
            "model": load_config().llm.model,
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
                yield "data: {\"gotoState\":\"done\",\"text\":\"Stream ended\"}\n\n"
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


# ── Page routes ─────────────────────────────────────────────────────

def _render(template_name: str, **extra) -> str:
    cfg = load_config()
    store = _load_store(cfg)
    entities = [Entity.model_validate(d) for d in store.load("entities.json")]
    relationships = [Relationship.model_validate(d) for d in store.load("relationships.json")]
    documents = [Document.model_validate(d) for d in store.load("documents.json")]
    chunks = [TextChunk.model_validate(d) for d in store.load("chunks.json")]

    ctx = {
        "active_tab": template_name.replace(".html", "").replace("index", "pipeline"),
        "asset_v": int(time.time()),
        "config": cfg,
        "state": {"entities": entities, "relationships": relationships, "documents": documents, "chunks": chunks},
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


# ── Main ────────────────────────────────────────────────────────────

def main() -> None:
    port = int(os.environ.get("CALLOSIP_PORT", "8766"))
    host = os.environ.get("CALLOSIP_HOST", "127.0.0.1")
    uvicorn.run("web.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()

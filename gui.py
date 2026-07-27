"""Graph Pipeline GUI — tkinter interface for the full extraction pipeline."""

from __future__ import annotations

import io
import json
import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

# Ensure src is importable when run directly
_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from graph_pipeline.config import PipelineConfig, load_config
from graph_pipeline.embedding.bge_embedder import BGEM3Embedder
from graph_pipeline.entity_resolution.resolver import EntityResolver
from graph_pipeline.entity_resolution.semantic_resolver import SemanticEntityResolver
from graph_pipeline.exporters.graph_exporter import GraphExporter
from graph_pipeline.exporters.obsidian_exporter import ObsidianExporter
from graph_pipeline.extraction.extractor import EntityExtractor
from graph_pipeline.extraction.llm_client import LLMClient
from graph_pipeline.ingestion.chunker import TextChunker
from graph_pipeline.models.document import Document, TextChunk
from graph_pipeline.models.entity import Entity, EntityType
from graph_pipeline.models.relationship import Relationship
from graph_pipeline.storage.file_store import FileStore


# ── Colour palette (LudwigLang / ArtificeGraph) ──
BG = "#f6f3ea"
BG_LIGHT = "#fbf9f3"
BG_RECESSED = "#efebdf"
FG = "#1b1813"
FG_DIM = "#4b463d"
FG_FAINT = "#716c5e"
ACCENT = "#2f7d45"
ACCENT_DEEP = "#1f5a31"
ACCENT_WASH = "rgba(47, 125, 69, 0.07)"
RULE = "#ddd6c6"
RULE_DARK = "#45413a"
BTN_BG = "#fbf9f3"
ENTRY_BG = "#f6f3ea"
SEL_BG = "#efebdf"


class PipelineGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Graph Pipeline — Historical Entity Extraction")
        self.geometry("980x740")
        self.configure(bg=BG)
        self.resizable(True, True)

        self._running = False
        self._build_ui()
        self._log("Graph Pipeline GUI ready.")
        self._log("Configure directories and LLM settings, then run a command.")

    # ── UI construction ─────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG, font=("Georgia", 10))
        style.configure("TButton", background=BTN_BG, foreground=FG, font=("Arial Narrow", 10), padding=(12, 6), borderwidth=1, relief="solid")
        style.map("TButton", background=[("active", ACCENT_WASH)], foreground=[("active", ACCENT_DEEP)])
        style.configure("Accent.TButton", background=ACCENT, foreground=BG_LIGHT, font=("Arial Narrow", 10, "bold"))
        style.map("Accent.TButton", background=[("active", ACCENT_DEEP)])
        style.configure("Danger.TButton", background="#8c3f5a", foreground=BG_LIGHT)
        style.configure("TEntry", fieldbackground=ENTRY_BG, foreground=FG, insertcolor=FG)
        style.configure("TLabelframe", background=BG, foreground=FG)
        style.configure("TLabelframe.Label", background=BG, foreground=ACCENT, font=("Arial Narrow", 11, "bold"))
        style.configure("TCheckbutton", background=BG, foreground=FG)
        style.configure("Header.TLabel", font=("Georgia", 16, "bold"), foreground=ACCENT, background=BG)
        style.configure("TNotebook", background=BG)
        style.configure("TNotebook.Tab", font=("Arial Narrow", 9), foreground=FG_DIM, padding=(8, 4))
        style.map("TNotebook.Tab", background=[("selected", ACCENT_WASH)], foreground=[("selected", ACCENT_DEEP)])
        style.configure("TProgressbar", background=ACCENT, troughcolor=BG_RECESSED, borderwidth=0)
        style.configure("Vertical.TSeparator", background=RULE)

        header = ttk.Label(self, text="Graph Pipeline", style="Header.TLabel")
        header.pack(pady=(12, 4))

        # ── Top config area ─────────────────────────────────────────────
        config_frame = ttk.Frame(self)
        config_frame.pack(fill=tk.X, padx=16, pady=(4, 8))

        self._build_dir_row(config_frame, "Input OCR Dir:", "input_dir", 0, default="data/input_ocr")
        self._build_dir_row(config_frame, "Output Dir:", "output_dir", 1, default="data/output")
        self._build_dir_row(config_frame, "Vault Dir:", "vault_dir", 2, default="data/obsidian_vault")
        self._build_entry_row(config_frame, "LLM Base URL:", "llm_url", 3, default="http://localhost:11434")
        self._build_entry_row(config_frame, "Model:", "llm_model", 4, default="gemma2:27b")

        self._semantic_var = tk.BooleanVar(value=True)
        semantic_cb = ttk.Checkbutton(config_frame, text="Use Semantic Dedup (bge-m3)", variable=self._semantic_var)
        semantic_cb.grid(row=5, column=0, columnspan=3, sticky=tk.W, pady=4)

        # ── Command buttons ─────────────────────────────────────────────
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=16, pady=(4, 8))

        ttk.Label(btn_frame, text="Commands:", style="TLabel").grid(row=0, column=0, sticky=tk.W, padx=(0, 8))

        cmds = [
            ("1. Ingest", self._cmd_ingest, ACCENT),
            ("2. Extract", self._cmd_extract, ACCENT3),
            ("3. Resolve", self._cmd_resolve, ACCENT2),
            ("4. Vault", self._cmd_vault, ACCENT2),
            ("5. Graph", self._cmd_graph, ACCENT2),
        ]
        for i, (label, cmd, color) in enumerate(cmds):
            btn = ttk.Button(btn_frame, text=label, command=cmd, style="TButton")
            btn.grid(row=0, column=i + 1, padx=4, sticky=tk.EW)

        sep = ttk.Frame(btn_frame, height=2)
        sep.grid(row=1, column=0, columnspan=7, sticky=tk.EW, pady=6)

        run_btn = ttk.Button(btn_frame, text="Run All (1-5)", command=self._cmd_run_all, style="Accent.TButton")
        run_btn.grid(row=2, column=0, columnspan=4, padx=4, sticky=tk.EW, pady=(2, 0))

        demo_btn = ttk.Button(btn_frame, text="Demo (no LLM)", command=self._cmd_demo, style="TButton")
        demo_btn.grid(row=2, column=4, columnspan=3, padx=4, sticky=tk.EW, pady=(2, 0))

        for c in range(7):
            btn_frame.columnconfigure(c, weight=1)

        # ── Status + Log ────────────────────────────────────────────────
        self._status_var = tk.StringVar(value="Idle")
        status_bar = tk.Label(self, textvariable=self._status_var, fg=ACCENT, font=("Arial Narrow", 9), bg=BG)
        status_bar.pack(fill=tk.X, padx=16, pady=(4, 0))

        log_frame = ttk.Frame(self)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(4, 12))

        self.log_area = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            bg=ENTRY_BG,
            fg=FG,
            insertbackground=FG,
            font=("Consolas", 10),
            relief=tk.FLAT,
            borderwidth=0,
            state=tk.DISABLED,
        )
        self.log_area.pack(fill=tk.BOTH, expand=True)
        self.log_area.tag_configure("info", foreground=FG)
        self.log_area.tag_configure("success", foreground=ACCENT)
        self.log_area.tag_configure("error", foreground="#8c3f5a")
        self.log_area.tag_configure("dim", foreground=FG_FAINT)

        # ── Summary panel ───────────────────────────────────────
        self._summary_var = tk.StringVar(value="")
        summary_label = tk.Label(self, textvariable=self._summary_var, fg=FG_FAINT, font=("Arial Narrow", 9), bg=BG)
        summary_label.pack(fill=tk.X, padx=16, pady=(0, 8))

    def _build_dir_row(self, parent: ttk.Frame, label: str, attr: str, row: int, default: str = "") -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W, pady=2, padx=(0, 6))
        var = tk.StringVar(value=default)
        setattr(self, f"_{attr}_var", var)
        entry = ttk.Entry(parent, textvariable=var, width=40)
        entry.grid(row=row, column=1, sticky=tk.EW, pady=2)
        btn = ttk.Button(parent, text="Browse…", command=lambda: self._browse_dir(var))
        btn.grid(row=row, column=2, padx=(4, 0), pady=2)
        parent.columnconfigure(1, weight=1)

    def _build_entry_row(self, parent: ttk.Frame, label: str, attr: str, row: int, default: str = "") -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W, pady=2, padx=(0, 6))
        var = tk.StringVar(value=default)
        setattr(self, f"_{attr}_var", var)
        entry = ttk.Entry(parent, textvariable=var, width=40)
        entry.grid(row=row, column=1, sticky=tk.EW, pady=2)
        parent.columnconfigure(1, weight=1)

    def _browse_dir(self, var: tk.StringVar) -> None:
        d = filedialog.askdirectory()
        if d:
            var.set(d)

    # ── Logging helpers ─────────────────────────────────────────────────

    def _log(self, msg: str, tag: str = "info") -> None:
        self.log_area.configure(state=tk.NORMAL)
        self.log_area.insert(tk.END, msg + "\n", tag)
        self.log_area.see(tk.END)
        self.log_area.configure(state=tk.DISABLED)

    def _log_separator(self) -> None:
        self._log("─" * 72, "dim")

    def _set_status(self, text: str) -> None:
        self._status_var.set(text)
        self.update_idletasks()

    def _set_summary(self, text: str) -> None:
        self._summary_var.set(text)

    # ── Config helpers ──────────────────────────────────────────────────

    def _make_config(self) -> PipelineConfig:
        cfg = PipelineConfig()
        cfg.ingestion.input_dir = self._input_dir_var.get()
        cfg.export.output_dir = self._output_dir_var.get()
        cfg.export.obsidian_vault_dir = self._vault_dir_var.get()
        cfg.storage.entities_file = str(Path(cfg.export.output_dir) / "entities.json")
        cfg.storage.relationships_file = str(Path(cfg.export.output_dir) / "relationships.json")
        cfg.storage.documents_file = str(Path(cfg.export.output_dir) / "documents.json")
        cfg.storage.chunks_file = str(Path(cfg.export.output_dir) / "chunks.json")
        cfg.llm.base_url = self._llm_url_var.get()
        cfg.llm.model = self._llm_model_var.get()
        cfg.entity_resolution.use_semantic = self._semantic_var.get()
        return cfg

    def _build_resolver(self, cfg: PipelineConfig):
        if cfg.entity_resolution.use_semantic:
            embedder = BGEM3Embedder(cfg.embedding)
            return SemanticEntityResolver(embedder=embedder, config=cfg.entity_resolution)
        return EntityResolver(cfg.entity_resolution)

    # ── Threaded command runner ─────────────────────────────────────────

    def _run(self, fn, *args) -> None:
        if self._running:
            messagebox.showwarning("Busy", "A pipeline command is already running.")
            return
        self._running = True
        self._set_status("Running…")

        def _worker() -> None:
            try:
                fn(*args)
                self.after(0, lambda: self._set_status("Done"))
            except Exception as exc:
                self.after(0, lambda: self._log(f"ERROR: {exc}", "error"))
                self.after(0, lambda: self._set_status("Error"))
            finally:
                self._running = False

        threading.Thread(target=_worker, daemon=True).start()

    # ── Commands ────────────────────────────────────────────────────────

    def _cmd_ingest(self) -> None:
        def _do() -> None:
            cfg = self._make_config()
            self.after(0, lambda: self._log_separator())
            self.after(0, lambda: self._log("▶ INGEST — scanning input directory…"))

            chunker = TextChunker(cfg.ingestion)
            documents, chunks = chunker.ingest_all()
            self.after(0, lambda: self._log(f"  Found {len(documents)} documents → {len(chunks)} chunks"))

            if not documents:
                self.after(0, lambda: self._log("  No files found. Add .txt/.md files to the input dir.", "dim"))
                return

            store = FileStore(cfg.export.output_dir)
            store.save_models("documents.json", documents)
            store.save_models("chunks.json", chunks)
            self.after(0, lambda: self._log(f"  ✓ Saved to {cfg.export.output_dir}/", "success"))
            self.after(0, lambda: self._update_summary(documents=len(documents), chunks=len(chunks)))

        self._run(_do)

    def _cmd_extract(self) -> None:
        def _do() -> None:
            cfg = self._make_config()
            self.after(0, lambda: self._log_separator())
            self.after(0, lambda: self._log("▶ EXTRACT — calling local LLM…"))

            store = FileStore(cfg.export.output_dir)
            chunks = [TextChunk.model_validate(d) for d in store.load("chunks.json")]
            if not chunks:
                self.after(0, lambda: self._log("  No chunks found. Run Ingest first.", "dim"))
                return

            llm = LLMClient(cfg.llm)
            extractor = EntityExtractor(llm, cfg.extraction)

            all_entities: list[Entity] = []
            all_rels: list[Relationship] = []

            batch_size = cfg.extraction.batch_size
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i : i + batch_size]
                self.after(0, lambda ii=i: self._log(f"  Processing chunks {ii+1}–{min(ii+batch_size, len(chunks))}/{len(chunks)}…"))
                results = extractor.extract_batch(batch)
                for result in results:
                    all_entities.extend(result.entities)
                    all_rels.extend(result.relationships)

            store.save_models("entities.json", all_entities)
            store.save_models("relationships.json", all_rels)
            self.after(0, lambda: self._log(f"  ✓ Extracted {len(all_entities)} entities, {len(all_rels)} relationships", "success"))
            self.after(0, lambda: self._update_summary(entities=len(all_entities), relationships=len(all_rels)))

        self._run(_do)

    def _cmd_resolve(self) -> None:
        def _do() -> None:
            cfg = self._make_config()
            self.after(0, lambda: self._log_separator())
            self.after(0, lambda: self._log("▶ RESOLVE — deduplicating entities…"))

            store = FileStore(cfg.export.output_dir)
            entities = [Entity.model_validate(d) for d in store.load("entities.json")]
            relationships = [Relationship.model_validate(d) for d in store.load("relationships.json")]

            if not entities:
                self.after(0, lambda: self._log("  No entities found. Run Extract first.", "dim"))
                return

            resolver = self._build_resolver(cfg)
            merged, updated = resolver.resolve(entities, relationships)
            store.save_models("entities.json", merged)
            store.save_models("relationships.json", updated)

            method = "semantic" if isinstance(resolver, SemanticEntityResolver) else "fuzzy"
            self.after(0, lambda: self._log(f"  ✓ {len(entities)} → {len(merged)} canonical entities ({method})", "success"))
            self.after(0, lambda: self._update_summary(entities=len(merged)))

        self._run(_do)

    def _cmd_vault(self) -> None:
        def _do() -> None:
            cfg = self._make_config()
            self.after(0, lambda: self._log_separator())
            self.after(0, lambda: self._log("▶ BUILD VAULT — generating Obsidian notes…"))

            store = FileStore(cfg.export.output_dir)
            entities = [Entity.model_validate(d) for d in store.load("entities.json")]
            relationships = [Relationship.model_validate(d) for d in store.load("relationships.json")]
            documents = [Document.model_validate(d) for d in store.load("documents.json")]
            chunks = [TextChunk.model_validate(d) for d in store.load("chunks.json")]

            if not entities:
                self.after(0, lambda: self._log("  No entities found. Run extraction first.", "dim"))
                return

            resolver = self._build_resolver(cfg)
            merged, updated = resolver.resolve(entities, relationships)

            obsidian = ObsidianExporter(resolver, cfg.export)
            vault_path = obsidian.build_vault(merged, updated, documents, chunks)
            self.after(0, lambda: self._log(f"  ✓ Vault written to {vault_path}", "success"))

            note_count = sum(1 for _ in vault_path.rglob("*.md"))
            self.after(0, lambda: self._log(f"    {note_count} markdown notes generated"))
            self.after(0, lambda: self._update_summary(vault=str(vault_path), notes=note_count))

        self._run(_do)

    def _cmd_graph(self) -> None:
        def _do() -> None:
            cfg = self._make_config()
            self.after(0, lambda: self._log_separator())
            self.after(0, lambda: self._log("▶ BUILD GRAPH — exporting NetworkX…"))

            store = FileStore(cfg.export.output_dir)
            entities = [Entity.model_validate(d) for d in store.load("entities.json")]
            relationships = [Relationship.model_validate(d) for d in store.load("relationships.json")]

            if not entities:
                self.after(0, lambda: self._log("  No entities found. Run extraction first.", "dim"))
                return

            resolver = self._build_resolver(cfg)
            merged, updated = resolver.resolve(entities, relationships)

            exporter = GraphExporter(cfg.export)
            results = exporter.export(merged, updated)
            self.after(0, lambda: self._log(f"  ✓ {exporter.summary()}", "success"))
            for fmt, path in results.items():
                self.after(0, lambda f=fmt, p=path: self._log(f"    {f}: {p}"))

        self._run(_do)

    def _cmd_run_all(self) -> None:
        def _do() -> None:
            self.after(0, lambda: self._log_separator())
            self.after(0, lambda: self._log("▶ RUN ALL — full pipeline", "success"))

            self._cmd_ingest_inner()
            self._cmd_extract_inner()
            self._cmd_resolve_inner()
            self._cmd_vault_inner()
            self._cmd_graph_inner()

            self.after(0, lambda: self._log_separator())
            self.after(0, lambda: self._log("✓ Pipeline complete!", "success"))

        self._run(_do)

    def _cmd_demo(self) -> None:
        def _do() -> None:
            cfg = self._make_config()
            self.after(0, lambda: self._log_separator())
            self.after(0, lambda: self._log("▶ DEMO — synthetic data (no LLM needed)", "success"))

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
            chunk = chunker.ingest_string(sample_text, doc_id="demo_source")
            doc = Document(
                id="demo_source", filename="demo.txt", filepath="<demo>",
                raw_text=sample_text, chunk_ids=[chunk.id],
            )

            store = FileStore(cfg.export.output_dir)
            store.save_models("documents.json", [doc])
            store.save_models("chunks.json", [chunk])
            self.after(0, lambda: self._log("  Ingested demo text → 1 chunk"))

            synthetic_entities = [
                Entity(name="Klemens von Metternich", entity_type=EntityType.PERSON,
                       aliases=["Metternich", "Prince Metternich"],
                       summary="Austrian foreign minister and central figure at the Congress of Vienna.",
                       source_doc_ids=["demo_source"]),
                Entity(name="Alexander I", entity_type=EntityType.PERSON,
                       aliases=["Tsar Alexander I"],
                       summary="Tsar of Russia who sought expanded influence at the Congress of Vienna.",
                       source_doc_ids=["demo_source"]),
                Entity(name="Karl vom Stein", entity_type=EntityType.PERSON,
                       aliases=["Baron Stein", "Baron vom Stein"],
                       summary="Prussian statesman who participated in early Congress discussions.",
                       source_doc_ids=["demo_source"]),
                Entity(name="Congress of Vienna", entity_type=EntityType.EVENT,
                       aliases=["The Congress"],
                       summary="Diplomatic conference held in 1814 to reorganize Europe.",
                       source_doc_ids=["demo_source"]),
                Entity(name="Austria", entity_type=EntityType.LOCATION,
                       aliases=["Austrian Empire"],
                       summary="Major European power and host nation of the Congress.",
                       source_doc_ids=["demo_source"]),
                Entity(name="Prussia", entity_type=EntityType.LOCATION, aliases=[],
                       summary="German state that participated in the Congress of Vienna.",
                       source_doc_ids=["demo_source"]),
                Entity(name="Russia", entity_type=EntityType.LOCATION, aliases=[],
                       summary="Major European power represented at the Congress.",
                       source_doc_ids=["demo_source"]),
                Entity(name="Great Britain", entity_type=EntityType.LOCATION, aliases=[],
                       summary="Major European power represented at the Congress.",
                       source_doc_ids=["demo_source"]),
                Entity(name="Napoleonic Wars", entity_type=EntityType.EVENT, aliases=[],
                       summary="Series of wars that preceded the Congress of Vienna.",
                       source_doc_ids=["demo_source"]),
                Entity(name="Concert of Europe", entity_type=EntityType.CONCEPT, aliases=[],
                       summary="Balance-of-power system established after the Congress.",
                       source_doc_ids=["demo_source"]),
                Entity(name="Treaty of Paris", entity_type=EntityType.EVENT, aliases=[],
                       summary="Peace treaty signed on May 30, 1814.",
                       source_doc_ids=["demo_source"]),
                Entity(name="Nationalism", entity_type=EntityType.CONCEPT, aliases=[],
                       summary="Political ideology championed by liberal movements.",
                       source_doc_ids=["demo_source"]),
            ]

            synthetic_rels = [
                Relationship(source_entity="Klemens von Metternich", target_entity="Congress of Vienna",
                             relationship_type="participated_in", time_frame="1814-1815",
                             evidence_quote="played a central role in the negotiations", confidence_score=0.95,
                             source_doc_id="demo_source"),
                Relationship(source_entity="Alexander I", target_entity="Congress of Vienna",
                             relationship_type="participated_in", time_frame="1814",
                             evidence_quote="sought to expand Russian influence", confidence_score=0.95,
                             source_doc_id="demo_source"),
                Relationship(source_entity="Alexander I", target_entity="Russia",
                             relationship_type="ruled", time_frame="1801-1825",
                             evidence_quote="Tsar Alexander I of Russia", confidence_score=0.95,
                             source_doc_id="demo_source"),
                Relationship(source_entity="Karl vom Stein", target_entity="Congress of Vienna",
                             relationship_type="participated_in", time_frame="1814",
                             evidence_quote="participated in early discussions but died before the Congress concluded",
                             confidence_score=0.9, source_doc_id="demo_source"),
                Relationship(source_entity="Klemens von Metternich", target_entity="Austria",
                             relationship_type="served_as_foreign_minister_of", time_frame="1809-1848",
                             evidence_quote="the Austrian foreign minister", confidence_score=0.95,
                             source_doc_id="demo_source"),
                Relationship(source_entity="Karl vom Stein", target_entity="Prussia",
                             relationship_type="was_statesman_of", time_frame="",
                             evidence_quote="a Prussian statesman", confidence_score=0.9,
                             source_doc_id="demo_source"),
                Relationship(source_entity="Congress of Vienna", target_entity="Concert of Europe",
                             relationship_type="established", time_frame="1815",
                             evidence_quote="The resulting Concert of Europe established a balance of power",
                             confidence_score=0.95, source_doc_id="demo_source"),
                Relationship(source_entity="Concert of Europe", target_entity="Nationalism",
                             relationship_type="opposed", time_frame="1815-1914",
                             evidence_quote="championing conservatism against nationalist and liberal movements",
                             confidence_score=0.85, source_doc_id="demo_source"),
            ]

            store.save_models("entities.json", synthetic_entities)
            store.save_models("relationships.json", synthetic_rels)
            self.after(0, lambda: self._log(f"  Created {len(synthetic_entities)} entities, {len(synthetic_rels)} relationships"))

            resolver = self._build_resolver(cfg)
            merged, updated = resolver.resolve(synthetic_entities, synthetic_rels)
            store.save_models("entities.json", merged)
            store.save_models("relationships.json", updated)
            method = "semantic" if isinstance(resolver, SemanticEntityResolver) else "fuzzy"
            self.after(0, lambda: self._log(f"  Resolved → {len(merged)} canonical entities ({method})"))

            obsidian = ObsidianExporter(resolver, cfg.export)
            vault_path = obsidian.build_vault(merged, updated, [doc], [chunk])
            note_count = sum(1 for _ in vault_path.rglob("*.md"))
            self.after(0, lambda: self._log(f"  ✓ Obsidian vault: {vault_path} ({note_count} notes)", "success"))

            graph_exp = GraphExporter(cfg.export)
            graph_results = graph_exp.export(merged, updated)
            self.after(0, lambda: self._log(f"  ✓ {graph_exp.summary()}", "success"))

            self.after(0, lambda: self._set_summary(
                f"Demo: {len(merged)} entities, {len(updated)} relationships, {note_count} vault notes"
            ))

        self._run(_do)

    # ── Inner helpers for run-all (called from worker thread) ───────────

    def _cmd_ingest_inner(self) -> None:
        cfg = self._make_config()
        self.after(0, lambda: self._log("  [1/5] Ingesting…"))
        chunker = TextChunker(cfg.ingestion)
        documents, chunks = chunker.ingest_all()
        self.after(0, lambda: self._log(f"    {len(documents)} docs → {len(chunks)} chunks"))
        store = FileStore(cfg.export.output_dir)
        store.save_models("documents.json", documents)
        store.save_models("chunks.json", chunks)

    def _cmd_extract_inner(self) -> None:
        cfg = self._make_config()
        self.after(0, lambda: self._log("  [2/5] Extracting via LLM…"))
        store = FileStore(cfg.export.output_dir)
        chunks = [TextChunk.model_validate(d) for d in store.load("chunks.json")]
        if not chunks:
            return
        llm = LLMClient(cfg.llm)
        extractor = EntityExtractor(llm, cfg.extraction)
        all_e, all_r = [], []
        results = extractor.extract_batch(chunks)
        for r in results:
            all_e.extend(r.entities)
            all_r.extend(r.relationships)
        store.save_models("entities.json", all_e)
        store.save_models("relationships.json", all_r)
        self.after(0, lambda: self._log(f"    {len(all_e)} entities, {len(all_r)} relationships"))

    def _cmd_resolve_inner(self) -> None:
        cfg = self._make_config()
        self.after(0, lambda: self._log("  [3/5] Resolving entities…"))
        store = FileStore(cfg.export.output_dir)
        ents = [Entity.model_validate(d) for d in store.load("entities.json")]
        rels = [Relationship.model_validate(d) for d in store.load("relationships.json")]
        if not ents:
            return
        resolver = self._build_resolver(cfg)
        merged, updated = resolver.resolve(ents, rels)
        store.save_models("entities.json", merged)
        store.save_models("relationships.json", updated)
        method = "semantic" if isinstance(resolver, SemanticEntityResolver) else "fuzzy"
        self.after(0, lambda: self._log(f"    {len(ents)} → {len(merged)} canonical ({method})"))

    def _cmd_vault_inner(self) -> None:
        cfg = self._make_config()
        self.after(0, lambda: self._log("  [4/5] Building vault…"))
        store = FileStore(cfg.export.output_dir)
        ents = [Entity.model_validate(d) for d in store.load("entities.json")]
        rels = [Relationship.model_validate(d) for d in store.load("relationships.json")]
        docs = [Document.model_validate(d) for d in store.load("documents.json")]
        chunks = [TextChunk.model_validate(d) for d in store.load("chunks.json")]
        if not ents:
            return
        resolver = self._build_resolver(cfg)
        merged, updated = resolver.resolve(ents, rels)
        obsidian = ObsidianExporter(resolver, cfg.export)
        vault_path = obsidian.build_vault(merged, updated, docs, chunks)
        self.after(0, lambda: self._log(f"    Vault: {vault_path}"))

    def _cmd_graph_inner(self) -> None:
        cfg = self._make_config()
        self.after(0, lambda: self._log("  [5/5] Exporting graph…"))
        store = FileStore(cfg.export.output_dir)
        ents = [Entity.model_validate(d) for d in store.load("entities.json")]
        rels = [Relationship.model_validate(d) for d in store.load("relationships.json")]
        if not ents:
            return
        resolver = self._build_resolver(cfg)
        merged, updated = resolver.resolve(ents, rels)
        graph_exp = GraphExporter(cfg.export)
        results = graph_exp.export(merged, updated)
        self.after(0, lambda: self._log(f"    {graph_exp.summary()}"))

    def _update_summary(self, **kwargs) -> None:
        parts = [f"{k}: {v}" for k, v in kwargs.items()]
        self._set_summary("  |  ".join(parts))


def main() -> None:
    app = PipelineGUI()
    app.mainloop()


if __name__ == "__main__":
    main()

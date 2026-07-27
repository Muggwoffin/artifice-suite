from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich import box

from artifice_graph.config import load_config
from artifice_graph.embedding.bge_embedder import BGEM3Embedder
from artifice_graph.entity_resolution.resolver import EntityResolver
from artifice_graph.entity_resolution.semantic_resolver import SemanticEntityResolver
from artifice_graph.exporters.graph_exporter import GraphExporter
from artifice_graph.exporters.obsidian_exporter import ObsidianExporter
from artifice_graph.extraction.extractor import EntityExtractor
from artifice_graph.extraction.llm_client import LLMClient
from artifice_graph.ingestion.chunker import TextChunker
from artifice_graph.models.document import Document, TextChunk
from artifice_graph.models.entity import Entity
from artifice_graph.models.relationship import Relationship
from artifice_graph.storage.file_store import FileStore

app = typer.Typer(
    name="artificegraph",
    help="Local-first GraphRAG & Entity Extraction pipeline for historical OCR text.",
    no_args_is_help=True,
)
console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True, console=console)],
)
logger = logging.getLogger(__name__)


def _load_pipeline_data(store: FileStore) -> tuple[list[Entity], list[Relationship], list[Document], list[TextChunk]]:
    entities = [Entity.model_validate(d) for d in store.load("entities.json")]
    relationships = [Relationship.model_validate(d) for d in store.load("relationships.json")]
    documents = [Document.model_validate(d) for d in store.load("documents.json")]
    chunks = [TextChunk.model_validate(d) for d in store.load("chunks.json")]
    return entities, relationships, documents, chunks


def _build_resolver(
    config: object,
    use_semantic: bool | None = None,
) -> EntityResolver | SemanticEntityResolver:
    from artifice_graph.config import PipelineConfig
    cfg: PipelineConfig = config
    should_use = use_semantic if use_semantic is not None else cfg.entity_resolution.use_semantic
    if should_use:
        embedder = BGEM3Embedder(cfg.embedding)
        return SemanticEntityResolver(embedder=embedder, config=cfg.entity_resolution)
    return EntityResolver(cfg.entity_resolution)


# ── Shared stage runner with error isolation ─────────────────────────────

def _run_stage(stage: int, total: int, label: str, fn) -> bool:
    """Run a pipeline stage with error isolation. Returns True on success."""
    try:
        console.print(f"[dim][{stage}/{total}] {label}[/dim]")
        fn()
        return True
    except typer.Exit:
        return False
    except Exception as exc:
        console.print(f"  [bold red]Stage {stage} failed:[/bold red] {exc}")
        logger.debug("Stage %d traceback", stage, exc_info=True)
        return False


# ── Commands ─────────────────────────────────────────────────────────────

@app.command()
def ingest(
    input_dir: str = typer.Argument("data/input_ocr", help="Directory containing OCR text files"),
    chunk_size: int = typer.Option(2000, help="Max characters per chunk"),
    chunk_overlap: int = typer.Option(200, help="Overlap between chunks"),
    output_dir: str = typer.Option(None, "--output-dir", help="Output directory"),
    incremental: bool = typer.Option(False, "--incremental", help="Only process new/changed files"),
    model: str = typer.Option(None, "--model", help="LLM model name"),
    base_url: str = typer.Option(None, "--base-url", help="LLM API base URL"),
) -> None:
    """Ingest OCR text files and produce sliding-window chunks."""
    config = load_config()
    config.ingestion.input_dir = input_dir
    config.ingestion.chunk_size = chunk_size
    config.ingestion.chunk_overlap = chunk_overlap
    if output_dir:
        config.export.output_dir = output_dir
    if model:
        config.llm.model = model
    if base_url:
        config.llm.base_url = base_url

    store = FileStore(config.export.output_dir)
    chunker = TextChunker(config.ingestion)

    if incremental:
        previous = store.load("content_hashes.json")
        prev_hashes = {d["id"]: d.get("content_hash", "") for d in previous} if previous else {}
        documents, chunks, stale_ids = chunker.ingest_all_incremental(prev_hashes)
        if not documents:
            console.print("[yellow]No new or changed files to process.[/yellow]")
            return
        new_hashes = {d.id: chunker.file_content_hash(Path(d.filepath)) for d in documents}
        store.save("content_hashes.json", [{"id": k, "content_hash": v} for k, v in new_hashes.items()])
        console.print(f"[bold green]Incremental: {len(documents)} new/changed docs -> {len(chunks)} chunks[/bold green]")
    else:
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
            task = progress.add_task("Discovering files…", total=None)
            documents, chunks = chunker.ingest_all()
            progress.update(task, description=f"Found {len(documents)} documents, {len(chunks)} chunks")

    if not documents:
        console.print("[yellow]No files found. Add files to the input directory.[/yellow]")
        raise typer.Exit(1)

    console.print(Panel(f"[bold green]Ingested {len(documents)} documents -> {len(chunks)} chunks[/bold green]"))

    store.save_models("documents.json", documents)
    store.save_models("chunks.json", chunks)
    console.print(f"[dim]Saved to {config.export.output_dir}/documents.json, chunks.json[/dim]")


@app.command()
def extract(
    batch_size: int = typer.Option(5, help="Number of chunks to process"),
    model: str = typer.Option(None, "--model", help="LLM model name"),
    base_url: str = typer.Option(None, "--base-url", help="LLM API base URL"),
    api_key: str = typer.Option(None, "--api-key", help="API key for cloud providers"),
    output_dir: str = typer.Option(None, "--output-dir", help="Output directory"),
) -> None:
    """Extract entities and relationships from ingested chunks using local LLM."""
    config = load_config()
    if model:
        config.llm.model = model
    if base_url:
        config.llm.base_url = base_url
    if api_key:
        config.llm.api_key = api_key
    config.extraction.batch_size = batch_size
    if output_dir:
        config.export.output_dir = output_dir

    store = FileStore(config.export.output_dir)
    chunks = [TextChunk.model_validate(d) for d in store.load("chunks.json")]

    if not chunks:
        console.print("[yellow]No chunks found. Run 'graph-pipeline ingest' first.[/yellow]")
        raise typer.Exit(1)

    llm = LLMClient(config.llm)
    extractor = EntityExtractor(llm, config.extraction)

    all_entities: list[Entity] = []
    all_relationships: list[Relationship] = []

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        task = progress.add_task("Extracting entities…", total=len(chunks))
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            results = extractor.extract_batch(batch)
            for result in results:
                all_entities.extend(result.entities)
                all_relationships.extend(result.relationships)
            progress.advance(task, advance=len(batch))

    console.print(
        Panel(
            f"[bold blue]Extracted {len(all_entities)} entities, "
            f"{len(all_relationships)} relationships[/bold blue]"
        )
    )

    store.save_models("entities.json", all_entities)
    store.save_models("relationships.json", all_relationships)
    console.print(f"[dim]Saved to {config.export.output_dir}/entities.json, relationships.json[/dim]")


@app.command("resolve-entities")
def resolve_entities(
    semantic: bool = typer.Option(None, "--semantic/--no-semantic", help="Use embedding-based semantic dedup"),
    model: str = typer.Option(None, "--model", help="LLM model name"),
    base_url: str = typer.Option(None, "--base-url", help="LLM API base URL"),
    api_key: str = typer.Option(None, "--api-key", help="API key for cloud providers"),
    output_dir: str = typer.Option(None, "--output-dir", help="Output directory"),
) -> None:
    """Deduplicate and normalize extracted entities."""
    config = load_config()
    if model:
        config.llm.model = model
    if base_url:
        config.llm.base_url = base_url
    if api_key:
        config.llm.api_key = api_key
    if output_dir:
        config.export.output_dir = output_dir

    store = FileStore(config.export.output_dir)
    entities, relationships, _, _ = _load_pipeline_data(store)

    if not entities:
        console.print("[yellow]No entities found. Run 'graph-pipeline extract' first.[/yellow]")
        raise typer.Exit(1)

    store.save_models("entities_raw.json", entities)

    resolver = _build_resolver(config, use_semantic=semantic)
    method = "semantic" if isinstance(resolver, SemanticEntityResolver) else "fuzzy"
    console.print(f"[dim]Using {method} resolution[/dim]")

    merged_entities, updated_relationships = resolver.resolve(entities, relationships)

    console.print(
        Panel(
            f"[bold magenta]Resolved {len(entities)} -> {len(merged_entities)} canonical entities[/bold magenta]"
        )
    )

    store.save_models("entities.json", merged_entities)
    store.save_models("relationships.json", updated_relationships)


@app.command("build-vault")
def build_vault(
    semantic: bool = typer.Option(None, "--semantic/--no-semantic", help="Use embedding-based semantic dedup"),
    model: str = typer.Option(None, "--model", help="LLM model name"),
    base_url: str = typer.Option(None, "--base-url", help="LLM API base URL"),
    api_key: str = typer.Option(None, "--api-key", help="API key for cloud providers"),
    output_dir: str = typer.Option(None, "--output-dir", help="Output directory"),
) -> None:
    """Build a hyperlinked Obsidian vault from resolved entities."""
    config = load_config()
    if model:
        config.llm.model = model
    if base_url:
        config.llm.base_url = base_url
    if api_key:
        config.llm.api_key = api_key
    if output_dir:
        config.export.output_dir = output_dir

    store = FileStore(config.export.output_dir)
    entities, relationships, documents, chunks = _load_pipeline_data(store)

    if not entities:
        console.print("[yellow]No entities found. Run extraction and resolution first.[/yellow]")
        raise typer.Exit(1)

    resolver = _build_resolver(config, use_semantic=semantic)
    merged_entities, updated_relationships = resolver.resolve(entities, relationships)

    obsidian = ObsidianExporter(resolver, config.export)
    vault_path = obsidian.build_vault(merged_entities, updated_relationships, documents, chunks)

    console.print(
        Panel(f"[bold cyan]Obsidian vault built at: {vault_path}[/bold cyan]")
    )


@app.command("build-graph")
def build_graph(
    semantic: bool = typer.Option(None, "--semantic/--no-semantic", help="Use embedding-based semantic dedup"),
    output_dir: str = typer.Option(None, "--output-dir", help="Output directory"),
    format: list[str] = typer.Option(None, "--format", help="Export format(s): graphml, gexf, json, csv, cypher"),
) -> None:
    """Export the knowledge graph as GraphML, GEXF, JSON, CSV, and/or Cypher."""
    config = load_config()
    if output_dir:
        config.export.output_dir = output_dir

    store = FileStore(config.export.output_dir)
    entities, relationships, _, _ = _load_pipeline_data(store)

    if not entities:
        console.print("[yellow]No entities found. Run extraction first.[/yellow]")
        raise typer.Exit(1)

    resolver = _build_resolver(config, use_semantic=semantic)
    merged_entities, updated_relationships = resolver.resolve(entities, relationships)

    exporter = GraphExporter(config.export)
    results = exporter.export(merged_entities, updated_relationships, formats=format)

    console.print(
        Panel(
            f"[bold green]{exporter.summary()}[/bold green]\n"
            + "\n".join(f"  {k}: {v}" for k, v in results.items())
        )
    )


@app.command("run-all")
def run_all(
    input_dir: str = typer.Argument("data/input_ocr", help="Directory containing OCR text files"),
    model: str = typer.Option("gemma2:27b", help="LLM model name"),
    base_url: str = typer.Option("http://localhost:11434", help="LLM API base URL"),
    semantic: bool = typer.Option(None, "--semantic/--no-semantic", help="Use embedding-based semantic dedup"),
    output_dir: str = typer.Option(None, "--output-dir", help="Output directory"),
    incremental: bool = typer.Option(False, "--incremental", help="Only process new/changed files"),
    format: list[str] = typer.Option(None, "--format", help="Graph export format(s): graphml, gexf, json, csv, cypher"),
) -> None:
    """Run the full pipeline: ingest -> extract -> resolve -> build vault + graph."""
    console.print(Panel("[bold]Running full pipeline[/bold]", title="graph-pipeline"))

    stages_ok = 0
    stages_total = 5

    def _ingest():
        ingest(input_dir=input_dir, output_dir=output_dir, incremental=incremental)
    def _extract():
        extract(model=model, base_url=base_url, output_dir=output_dir)
    def _resolve():
        resolve_entities(semantic=semantic, output_dir=output_dir)
    def _vault():
        build_vault(semantic=semantic, output_dir=output_dir)
    def _graph():
        build_graph(semantic=semantic, output_dir=output_dir, format=format)

    for ok in [_run_stage(1, stages_total, "Ingesting", _ingest),
               _run_stage(2, stages_total, "Extracting via LLM", _extract),
               _run_stage(3, stages_total, "Resolving entities", _resolve),
               _run_stage(4, stages_total, "Building vault", _vault),
               _run_stage(5, stages_total, "Building graph", _graph)]:
        if ok:
            stages_ok += 1

    if stages_ok == stages_total:
        console.print(Panel("[bold green]Pipeline complete![/bold green]", title="Done"))
    else:
        console.print(
            Panel(f"[bold yellow]{stages_ok}/{stages_total} stages completed successfully[/bold yellow]")
        )


@app.command("inspect")
def inspect(
    output_dir: str = typer.Option(None, "--output-dir", help="Output directory"),
) -> None:
    """Display summary statistics for the current pipeline state."""
    config = load_config()
    if output_dir:
        config.export.output_dir = output_dir

    store = FileStore(config.export.output_dir)
    entities, relationships, documents, chunks = _load_pipeline_data(store)

    table = Table(title="Pipeline State", box=box.ROUNDED)
    table.add_column("Artefact", style="cyan")
    table.add_column("Count", style="bold green", justify="right")

    table.add_row("Documents", str(len(documents)))
    table.add_row("Chunks", str(len(chunks)))
    table.add_row("Entities (raw)", str(store.load("entities_raw.json").__len__() if store.load("entities_raw.json") else 0))
    table.add_row("Entities (canonical)", str(len(entities)))
    table.add_row("Relationships", str(len(relationships)))
    table.add_row("Files in input dir", str(sum(1 for _ in Path(config.ingestion.input_dir).rglob("*") if _.is_file()) if Path(config.ingestion.input_dir).exists() else 0))

    console.print(table)

    if entities:
        from collections import Counter
        type_counts = Counter(e.entity_type.value for e in entities)
        type_table = Table(title="Entity Type Breakdown", box=box.SIMPLE)
        type_table.add_column("Type", style="cyan")
        type_table.add_column("Count", style="bold", justify="right")
        for etype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            type_table.add_row(etype, str(count))
        console.print(type_table)

    if relationships:
        from collections import Counter
        rel_counts = Counter(r.relationship_type for r in relationships)
        rel_table = Table(title="Relationship Type Breakdown (top 10)", box=box.SIMPLE)
        rel_table.add_column("Type", style="cyan")
        rel_table.add_column("Count", style="bold", justify="right")
        for rtype, count in sorted(rel_counts.items(), key=lambda x: -x[1])[:10]:
            rel_table.add_row(rtype, str(count))
        console.print(rel_table)

    if not entities and not documents:
        console.print("[yellow]No pipeline data found. Run 'graph-pipeline run-all' or 'graph-pipeline demo' first.[/yellow]")

    if entities:
        try:
            import networkx as nx
            G = nx.DiGraph()
            for e in entities:
                G.add_node(e.id, label=e.name, type=e.entity_type.value)
            for r in relationships:
                src_id = Entity._make_id(r.source_entity)
                tgt_id = Entity._make_id(r.target_entity)
                if G.has_node(src_id) and G.has_node(tgt_id):
                    G.add_edge(src_id, tgt_id)
            comps = list(nx.weakly_connected_components(G))
            top_degree = sorted(G.degree(), key=lambda x: -x[1])[:5]
            if top_degree:
                degree_table = Table(title="Most Connected Entities", box=box.SIMPLE)
                degree_table.add_column("Entity", style="cyan")
                degree_table.add_column("Connections", style="bold", justify="right")
                for node_id, deg in top_degree:
                    label = G.nodes[node_id].get("label", node_id)
                    degree_table.add_row(label, str(deg))
                console.print(degree_table)
                console.print(f"[dim]Connected components: {len(comps)}, Graph density: {nx.density(G):.4f}[/dim]")
        except Exception:
            pass


@app.command("demo")
def demo() -> None:
    """Run a demo pipeline with embedded sample historical text (no LLM required)."""
    config = load_config()

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

    chunker = TextChunker(config.ingestion)
    chunk = chunker.ingest_string(sample_text, doc_id="congress_of_vienna_sample")

    documents = [
        Document(
            id="congress_of_vienna_sample",
            filename="congress_of_vienna_sample.txt",
            filepath="<demo>",
            raw_text=sample_text,
            chunk_ids=[chunk.id],
        )
    ]

    store = FileStore(config.export.output_dir)
    store.save_models("documents.json", documents)
    store.save_models("chunks.json", [chunk])

    from artifice_graph.extraction.schemas import ExtractionResult

    synthetic_result = ExtractionResult(
        entities=[
            {"name": "Klemens von Metternich", "entity_type": "Person",
             "aliases": ["Metternich", "Prince Metternich"],
             "summary": "Austrian foreign minister and central figure at the Congress of Vienna."},
            {"name": "Alexander I", "entity_type": "Person",
             "aliases": ["Tsar Alexander I"],
             "summary": "Tsar of Russia who sought expanded influence at the Congress of Vienna."},
            {"name": "Karl vom Stein", "entity_type": "Person",
             "aliases": ["Baron Stein", "Baron vom Stein"],
             "summary": "Prussian statesman who participated in early Congress discussions but died before its conclusion."},
            {"name": "Congress of Vienna", "entity_type": "Event",
             "aliases": ["The Congress"],
             "summary": "Diplomatic conference held in 1814 to reorganize Europe after the Napoleonic Wars."},
            {"name": "Austria", "entity_type": "Location",
             "aliases": ["Austrian Empire"],
             "summary": "Major European power and host nation of the Congress of Vienna."},
            {"name": "Prussia", "entity_type": "Location", "aliases": [],
             "summary": "German state that participated in the Congress of Vienna."},
            {"name": "Russia", "entity_type": "Location", "aliases": [],
             "summary": "Major European power represented at the Congress of Vienna."},
            {"name": "Great Britain", "entity_type": "Location", "aliases": [],
             "summary": "Major European power represented at the Congress of Vienna."},
            {"name": "Napoleonic Wars", "entity_type": "Event", "aliases": [],
             "summary": "Series of wars fought between France and various European coalitions that preceded the Congress of Vienna."},
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
             "evidence_quote": "Prince Klemens von Metternich played a central role in the negotiations.",
             "confidence_score": 0.95},
            {"source_entity": "Alexander I", "target_entity": "Congress of Vienna",
             "relationship_type": "participated_in", "time_frame": "1814",
             "evidence_quote": "Tsar Alexander I of Russia sought to expand Russian influence.",
             "confidence_score": 0.95},
            {"source_entity": "Alexander I", "target_entity": "Russia",
             "relationship_type": "ruled", "time_frame": "1801-1825",
             "evidence_quote": "Tsar Alexander I of Russia", "confidence_score": 0.95},
            {"source_entity": "Karl vom Stein", "target_entity": "Congress of Vienna",
             "relationship_type": "participated_in", "time_frame": "1814",
             "evidence_quote": "participated in early discussions but died before the Congress concluded.",
             "confidence_score": 0.9},
            {"source_entity": "Klemens von Metternich", "target_entity": "Austria",
             "relationship_type": "served_as_foreign_minister_of", "time_frame": "1809-1848",
             "evidence_quote": "the Austrian foreign minister", "confidence_score": 0.95},
            {"source_entity": "Karl vom Stein", "target_entity": "Prussia",
             "relationship_type": "was_statesman_of", "time_frame": "",
             "evidence_quote": "a Prussian statesman", "confidence_score": 0.9},
            {"source_entity": "Congress of Vienna", "target_entity": "Concert of Europe",
             "relationship_type": "established", "time_frame": "1815",
             "evidence_quote": "The resulting Concert of Europe established a balance of power",
             "confidence_score": 0.95},
            {"source_entity": "Concert of Europe", "target_entity": "Nationalism",
             "relationship_type": "opposed", "time_frame": "1815-1914",
             "evidence_quote": "championing conservatism against nationalist and liberal movements",
             "confidence_score": 0.85},
        ],
    )

    from artifice_graph.models.entity import Entity as EntityModel, EntityType
    from artifice_graph.models.relationship import Relationship as RelModel

    entities = []
    for e in synthetic_result.entities:
        entities.append(
            EntityModel(
                name=e.name,
                entity_type=EntityType(e.entity_type),
                aliases=e.aliases,
                summary=e.summary,
                source_doc_ids=["congress_of_vienna_sample"],
            )
        )

    relationships = []
    for r in synthetic_result.relationships:
        relationships.append(
            RelModel(
                source_entity=r.source_entity,
                target_entity=r.target_entity,
                relationship_type=r.relationship_type,
                time_frame=r.time_frame,
                evidence_quote=r.evidence_quote,
                confidence_score=r.confidence_score,
                source_doc_id="congress_of_vienna_sample",
            )
        )

    store.save_models("entities_raw.json", entities)
    store.save_models("entities.json", entities)
    store.save_models("relationships.json", relationships)

    resolver = _build_resolver(config)
    merged_entities, updated_rels = resolver.resolve(entities, relationships)

    store.save_models("entities.json", merged_entities)
    store.save_models("relationships.json", updated_rels)

    obsidian = ObsidianExporter(resolver, config.export)
    vault_path = obsidian.build_vault(merged_entities, updated_rels, documents, [chunk])

    graph_exporter = GraphExporter(config.export)
    graph_results = graph_exporter.export(merged_entities, updated_rels, formats=["graphml", "gexf", "json", "csv"])

    console.print(Panel("[bold green]Demo complete![/bold green]", title="Done"))
    console.print(f"  Entities: {len(merged_entities)}")
    console.print(f"  Relationships: {len(updated_rels)}")
    console.print(f"  Graph: {graph_exporter.summary()}")
    console.print(f"  Vault: {vault_path}")
    for k, v in graph_results.items():
        console.print(f"  {k}: {v}")


if __name__ == "__main__":
    app()

# ArtificeGraph

A modular, local-first pipeline that transforms historical OCR text into structured knowledge graphs and hyperlinked Obsidian vaults—entirely offline using local LLMs and embedding models.

```
OCR text → chunk → entity/relation extraction (LLM) → semantic dedup (bge-m3) → NetworkX graph (GraphML/JSON) → Obsidian vault (Dataview Markdown)
```

Each stage is independent and runnable separately via CLI, GUI, or web UI.

---

## Table of Contents

- [Philosophy](#philosophy)
- [Capabilities](#capabilities)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [CLI Usage](#cli-usage)
- [Web UI](#web-ui)
- [GUI](#gui)
- [Pipeline Stages](#pipeline-stages)
- [Output Formats](#output-formats)
- [Output Directory Structure](#output-directory-structure)
- [Testing](#testing)
- [Demo (No LLM Required)](#demo-no-llm-required)
- [Roadmap](#roadmap)

---

## Philosophy

**Local-first, offline-by-default.** ArtificeGraph runs entirely on your machine using Ollama (or any OpenAI-compatible endpoint). No data leaves your system.

**Editorial, not algorithmic.** The design language derives from *The New Masses* (1920s–30s radical literary magazine) filtered through Soviet Constructivism—warm cream paper, dark ink, Esperanto green accents, serif body text. Every surface is a page; every component is typeset. Motion is restrained and tactile: cards lift like paper, rules draw in like ink, stars settle like type sorts.

**Historian-first.** Entity types (Person, Organization, Location, Event, Concept), typed relationships with evidence quotes, temporal awareness (planned), provenance tracking (planned), and importance scoring (planned) are built for historical research workflows—not generic NLP.

**Modular pipeline.** Five independent stages. Run one, run all, resume from any point. Incremental mode processes only changed files.

---

## Capabilities

| Area | Features |
|------|----------|
| **Input** | `.txt`, `.md`, `.pdf`, `.html` files; sliding-window chunking (configurable size/overlap); 50 MB file limit; content-hash incremental mode |
| **Entity Types** | Person, Organization, Location, Event, Concept (sub-types planned: Statesman, Battle, Treaty, etc.) |
| **Relationships** | Typed, directed, with confidence scores (0–1), evidence quotes, and time frames |
| **Entity Resolution** | Two strategies: fuzzy (SequenceMatcher ≥0.93) + semantic (bge-m3 cosine ≥0.85) with union-find clustering; YAML alias overrides |
| **LLM Backends** | Ollama (auto-detected), LM Studio, OpenAI-compatible; response caching keyed by model + prompt hash |
| **Graph Export** | GraphML (Gephi/yEd), GEXF (Gephi native, with viz attrs), JSON (node-link), CSV (nodes/edges), Cypher (Neo4j) |
| **Obsidian Vault** | `01_Sources/` with Dataview frontmatter; `02_Entities/{Persons,Organizations,Locations,Events,Concepts}/` with wikilinks, summaries, relationships + evidence, source backlinks |
| **Interfaces** | CLI (7 commands), tkinter GUI, FastAPI + Jinja2 web UI (LudwigLang design system) |
| **Demo Mode** | Synthetic Congress of Vienna graph (12 entities, 8 relationships)—runs without any LLM |

---

## Architecture

```
src/graph_pipeline/
├── cli.py                      # Typer CLI: 7 commands (ingest, extract, resolve-entities, build-vault, build-graph, run-all, demo, inspect)
├── config.py                   # Hierarchical Pydantic config (loads from config.yaml)
├── models/
│   ├── document.py             # Document & TextChunk (Pydantic v2)
│   ├── entity.py               # Entity with 5 types: Person, Organization, Location, Event, Concept
│   └── relationship.py         # Typed relationships with confidence, evidence, time_frame
├── ingestion/
│   └── chunker.py              # Sliding-window chunker; incremental via content hashes; file size guard
├── extraction/
│   ├── llm_client.py           # Auto-detects Ollama vs OpenAI-compatible backend
│   ├── cache.py                # Disk-backed LLM response cache (model + prompt hash)
│   ├── extractor.py            # Batch extraction with JSON retry logic
│   └── schemas.py              # Extraction response models
├── embedding/
│   └── bge_embedder.py         # bge-m3 via Ollama /api/embeddings; batching; cosine similarity
├── entity_resolution/
│   ├── resolver.py             # Fuzzy dedup: SequenceMatcher 0.93 + union-find
│   └── semantic_resolver.py    # Two-stage: fuzzy pre-filter → bge-m3 embeddings → cosine 0.85 → union-find; YAML aliases
├── exporters/
│   ├── graph_exporter.py       # NetworkX → GraphML, GEXF, JSON, CSV, Cypher
│   └── obsidian_exporter.py    # Obsidian vault: Dataview frontmatter, wikilinks, evidence quotes
└── storage/
    ├── file_store.py           # JSON persistence for pipeline artifacts
    └── graph_store.py          # NetworkX in-memory graph store
```

**Design Language** (LudwigLang / New Masses): cream paper (`#f6f3ea`), warm black ink (`#1b1813`), Esperanto green accent (`#2f7d45`), antique gold (`#bf9b30`). Playfair Display headlines, Libre Baskerville body, Archivo labels. Rounded corners (4–16px), paper-like shadows, editorial motion (fade-up, rule draw-in, card lift). Dark mode ("Lamplight Archive") via `prefers-color-scheme`. Full token system in `DESIGN_LANGUAGE.md`.

---

## Requirements

- **Python 3.11+**
- **Ollama** (recommended) at `http://localhost:11434` with models:
  - `gemma2:27b` (or any instruction-tuned LLM) for extraction
  - `bge-m3` for embedding-based entity dedup
- Or any **OpenAI-compatible endpoint** (LM Studio, etc.) via `--base-url` flag

---

## Installation

```bash
pip install -e .
pip install -e ".[dev]"   # for tests
pip install -e ".[web]"   # for web UI
```

---

## Configuration

All defaults from `config.yaml` at project root. Key settings:

| Section | Key | Default | Description |
|---------|-----|---------|-------------|
| `llm` | `base_url` | `http://localhost:11434` | LLM API endpoint |
| `llm` | `model` | `gemma2:27b` | Extraction model |
| `embedding` | `model` | `bge-m3` | Embedding model for semantic dedup |
| `ingestion` | `chunk_size` | `2000` | Characters per sliding-window chunk |
| `ingestion` | `chunk_overlap` | `200` | Overlap between adjacent chunks |
| `ingestion` | `max_file_size_mb` | `50` | Skip files larger than this |
| `extraction` | `batch_size` | `5` | Chunks per LLM call |
| `extraction` | `cache_dir` | `data/cache/llm_responses` | LLM response cache location |
| `entity_resolution` | `use_semantic` | `true` | Use bge-m3 semantic dedup |
| `entity_resolution` | `aliases_file` | `data/aliases.yaml` | Manual merge overrides |

---

## CLI Usage

```bash
graph-pipeline --help

# Full pipeline end-to-end:
graph-pipeline run-all data/input_ocr/

# Individual stages:
graph-pipeline ingest data/input_ocr/
graph-pipeline extract --model gemma2:27b
graph-pipeline resolve-entities --semantic
graph-pipeline build-vault
graph-pipeline build-graph

# Inspect current state:
graph-pipeline inspect

# Demo with synthetic data (no LLM needed):
graph-pipeline demo

# Incremental mode (only new/changed files):
graph-pipeline run-all --incremental

# Override output directory:
graph-pipeline run-all --output-dir data/custom_output
```

### Key Flags

| Flag | Applies to | Description |
|------|------------|-------------|
| `--semantic/--no-semantic` | `resolve-entities`, `build-vault`, `build-graph`, `run-all` | Enable/disable bge-m3 embedding dedup |
| `--incremental` | `ingest`, `run-all` | Only process files whose content hash changed |
| `--output-dir` | All commands | Override output directory |
| `--model` | `extract`, `run-all` | LLM model name |
| `--base-url` | `extract`, `run-all` | LLM API base URL |
| `--format` | `build-graph`, `run-all` | Graph export format(s): `graphml`, `gexf`, `json`, `csv`, `cypher` (repeatable) |

---

## Web UI

A FastAPI + Jinja2 interface implementing the LudwigLang design language (print-inflected, cream-paper palette, serif body text, green accent).

```bash
pip install -e ".[web]"
python -m web.server
# → http://localhost:8766
```

Or double-click `run_web.bat`.

### Pages

| Route | Description |
|-------|-------------|
| `/` | Pipeline control — config fields, stage buttons, live log via SSE |
| `/library` | Browse canonical entities, relationships, and documents from last run |
| `/about` | Project overview and design-language notes |

Configuration, pipeline execution, and streaming logs all use JSON API endpoints (`/api/*`) so you can drive the pipeline from other tools.

---

## GUI

```bash
python gui.py
```

A tkinter interface with config fields for directories, LLM endpoint, model selection, and semantic dedup checkbox. Commands run in background threads with a live log panel.

---

## Pipeline Stages

### 1. Ingestion
- Reads `.txt`, `.md`, `.pdf`, `.html` from input directory
- Sliding-window chunking with configurable size and overlap
- Tracks content hashes for incremental mode (skips unchanged files)
- 50 MB file size limit (configurable)

### 2. Extraction
- Sends chunks in batches to local LLM
- Parses structured JSON responses into entities and relationships
- Automatically retries on malformed responses
- Disk-backed response cache avoids redundant LLM calls (keyed by model name + prompt hash)
- Auto-detects Ollama vs OpenAI-compatible backends

### 3. Entity Resolution
Two strategies, controlled by `--semantic/--no-semantic`:

**Fuzzy resolver** (default fallback): SequenceMatcher at 0.93 threshold + union-find clustering.

**Semantic resolver** (recommended):
1. Applies manual YAML alias overrides from `data/aliases.yaml`
2. Fast fuzzy pre-filter at 0.93 similarity
3. Embeds each unique name with bge-m3 via Ollama
4. Computes pairwise cosine similarity at 0.85 threshold
5. Union-find clustering to merge duplicates
6. Picks canonical entity with richest metadata (longest summary, most aliases, most sources)

### 4. Obsidian Vault Export
- `01_Sources/` — source documents with Dataview frontmatter (`title`, `date`, `type: source`)
- `02_Entities/{Persons,Organizations,Locations,Events,Concepts}/` — one note per entity with:
  - Dataview frontmatter (`type`, `aliases`, `tags`)
  - Summary section
  - Relationships & Evidence section with `[[wikilinks]]` and direct quotes
  - Source Documents section with backlinks
- All entity mentions across notes are `[[wikilinked]]`

### 5. Graph Export
- NetworkX directed graph with entity nodes and relationship edges
- **GraphML** (`.graphml`) — for Gephi, yEd, Cytoscape
- **GEXF** (`.gexf`) — Gephi-native with visual attributes (entity-type colors, degree-based node sizing, edge confidence thickness)
- **JSON** (`.json`) — for web apps and programmatic use (node-link format)
- **CSV** (`.csv`) — node and edge tables for spreadsheets or data tools
- **Cypher** (`.cypher`) — CREATE statements for Neo4j import
- Node attributes: `label`, `entity_type`, `summary`, `aliases`
- Edge attributes: `relationship_type`, `time_frame`, `evidence_quote`, `confidence`

---

## Output Directory Structure

```
data/
├── input_ocr/          # Place your OCR text files here
├── output/
│   ├── entities.json       # Canonical entities after resolution
│   ├── entities_raw.json   # Pre-resolution snapshot (before dedup)
│   ├── relationships.json  # Relationships (source/target updated after merge)
│   ├── documents.json      # Original documents
│   ├── chunks.json         # Text chunks
│   ├── content_hashes.json # Content hashes for incremental mode
│   ├── knowledge_graph.graphml      # NetworkX GraphML (Gephi, yEd)
│   ├── knowledge_graph.gexf         # GEXF with viz attributes (Gephi native)
│   ├── knowledge_graph.json         # JSON node-link format
│   ├── knowledge_graph_nodes.csv    # Node table
│   ├── knowledge_graph_edges.csv    # Edge table
│   └── knowledge_graph.cypher       # Neo4j CREATE statements
├── obsidian_vault/     # Obsidian vault (open as a vault in Obsidian)
│   ├── 01_Sources/
│   └── 02_Entities/
│       ├── Persons/
│       ├── Organizations/
│       ├── Locations/
│       ├── Events/
│       └── Concepts/
├── cache/llm_responses/  # Disk cache of LLM responses
└── aliases.yaml          # Manual entity merge overrides
```

---

## Testing

```bash
pytest tests/ -v
```

13 tests covering chunking, entity dedup (fuzzy & semantic), graph export, Obsidian vault format, file storage, and demo mode. All run offline with no LLM dependency.

---

## Demo (No LLM Required)

```bash
graph-pipeline demo
```

Generates a synthetic knowledge graph from a sample text about the Congress of Vienna (12 entities, 8 relationships), runs resolution, and exports both a graph and an Obsidian vault—all without any LLM calls.

---

## Roadmap

See `PLAN.md` for the full expansion plan (PersonaeGraph rebrand).

| Phase | Focus | Target |
|-------|-------|--------|
| **1. Foundations** | Rename to PersonaeGraph; entity subtypes; TimeSpan model; provenance tracking; importance scoring | v2.0 |
| **2. Research Tools** | Setup wizard; Obsidian timeline; subgraph extraction; recommendation engine; improved visualization | v3.0 |
| **3. Advanced** | Context-aware LLM prompts; graph versioning/branching; citation export; collaborative curation UI; semi-automated extraction; multi-source merging; external KB enrichment (WikiData, VIAF) | v4.0 |

Cross-cutting: backward compatibility, test coverage, documentation, performance.

---

## License

MIT
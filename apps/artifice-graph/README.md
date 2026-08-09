# ArtificeGraph

**Local-First Knowledge Graph & Obsidian Vault Extraction for Historians**

*Part of the [Artifice Suite](../../README.md) — Local-First, Model-Agnostic Software Harnesses for Humanities Research.*

---

## 🏛️ Philosophy: The Software Harness vs. The Chatbot

ArtificeGraph transforms raw historical texts and OCR transcripts into structured NetworkX knowledge graphs and hyperlinked Obsidian vaults. It is engineered around Joseph Weizenbaum’s anti-ELIZA principle: **software should perform deterministic pipeline operations, invoking AI models strictly for structured entity and relationship extraction.**

┌────────────────────────────────────────────────────────────────────────────┐
│                         ArtificeGraph Harness                              │
│                                                                            │
│   1. Sliding-Window Document Ingestion & Content-Hash Chunking             │
│   2. Structured Entity/Relation Extraction (via packages/model-harness)   │
│   3. Semantic Entity Resolution (Fuzzy + bge-m3 Cosine Similarity)         │
│   4. Obsidian Vault Generation (Dataview Frontmatter & Wikilinks)          │
│   5. Multi-Format Graph Export (GraphML, GEXF, Cypher, JSON, CSV)          │
└────────────────────────────────────────────────────────────────────────────┘

1. **Deterministic Pipeline, No Conversational Noise:** ArtificeGraph never "chats" with you about your sources. It executes a modular 5-stage pipeline that ingests raw historical texts and yields structured research databases.
2. **Historian-First Data Model:** Built explicitly for historical methodology—tracking entity types (*Person*, *Organization*, *Location*, *Event*, *Concept*), typed relationships, verbatim evidence quotes, confidence scores, and temporal markers.
3. **Local-First & Private:** Primary historical documents, confidential archival transcripts, and prosopographical datasets remain 100% offline. Operates using local open-weights models via **Ollama** or **LM Studio**, or optionally cloud API endpoints via your own keys.
4. **Editorial Visual Identity:** Built using **The New Masses Design System** (`packages/shared-ui`)—a warm, paper-and-ink interface inspired by 1930s radical editorial design and Soviet Constructivism.

---

## ✨ Core Capabilities

### 1. Multi-Stage Pipeline Architecture
Each stage operates independently and can be executed separately or resumed at any point:
- **Ingestion**: Accepts `.txt`, `.md`, `.pdf`, and `.html` files. Performs sliding-window chunking (configurable size/overlap) with content-hash incremental processing.
- **Extraction**: Passes text chunks through `packages/model-harness` to extract typed entities and directed relationships with confidence scores and exact evidence quotes. Includes automatic JSON repair and disk-backed response caching.
- **Entity Resolution**: Two-tier deduplication combining fast fuzzy matching (SequenceMatcher) and semantic vector embeddings (`bge-m3` via Ollama) with union-find clustering and YAML alias overrides (`data/aliases.yaml`).
- **Obsidian Vault Exporter**: Generates a hyperlinked vault containing source documents (`01_Sources/`) and entity notes (`02_Entities/{Persons,Organizations,...}/`) with Dataview metadata, `[[wikilinks]]`, evidence quotes, and source backlinks.
- **Graph Exporters**: Generates NetworkX directed graphs exported as **GraphML** (Gephi/yEd), **GEXF** (Gephi-native with visual attributes), **JSON** (Node-link format), **CSV** (Node/Edge tables), and **Cypher** (Neo4j import scripts).

### 2. Tropy Provenance Import
Reads `artifice-ocr`'s `tropy_manifest.json` (`schema_version: "1.0"`) to build knowledge-graph nodes enriched with archival provenance:
- **Entity provenance**: item title, group, source photo path, orientation, and checksum attached to every graph node derived from a Tropy-imported OCR job.
- **Route**: `POST /api/tropy/import-manifest` — accepts a manifest path, validates the schema version, and merges provenance into the active graph.
- **Module**: `artifice_graph/tropy_import.py`.

### 3. Demo Mode (No Model Required)
Includes a built-in synthetic dataset on the Congress of Vienna (12 entities, 8 relationships) to test the graph exporters and Obsidian vault generators without requiring a running local LLM:
```bash
artifice-graph demo
```

---

## 🎨 Design System (`packages/shared-ui`)

All web and visual components in ArtificeGraph adhere to **The New Masses Design System**:
- **Palette**: Warm cream paper (`#f6f3ea`), deep warm black ink (`#1b1813`), Esperanto green accents (`#2f7d45`), and antique gold highlights (`#bf9b30`).
- **Typography**: Playfair Display (Headings), Libre Baskerville (Body text), and Archivo (UI Labels/Buttons).
- **Surface Elevation**: Paper-like diffused shadows (`shadow-paper`) and hard-offset tactile button press interactions.

---

## 📂 Monorepo Architecture

ArtificeGraph is located at `apps/artifice-graph` within the Artifice Suite monorepo and shares core dependencies with partner applications:

```
artifice-suite/
├── apps/
│   └── artifice-graph/
│       ├── src/
│       │   ├── cli.py                     # Typer CLI (7 commands)
│       │   ├── config.py                  # Pydantic configuration loader
│       │   ├── models/                    # Documents, entities, & relationships
│       │   ├── ingestion/                 # Sliding-window document chunker
│       │   ├── extraction/                # LLM extraction & disk cache
│       │   ├── embedding/                 # bge-m3 embedding generator
│       │   ├── entity_resolution/         # Fuzzy + semantic resolver & union-find
│       │   ├── exporters/                 # NetworkX & Obsidian exporters
│       │   ├── storage/                   # JSON & NetworkX graph persistence
│       │   └── web/                       # FastAPI server & LudwigLang web UI
│       ├── tests/                         # Pytest suite
│       └── README.md
└── packages/
    ├── shared-ui/                         # The New Masses CSS tokens & web components
    ├── model-harness/                    # BYOM connectors (Ollama/LM Studio/OpenAI)
    └── core-types/                       # Shared TypeScript & Python data interfaces
```

---

## 🚀 Setup & Installation

Ensure **Python 3.11+** is installed. From the monorepo root:

```bash
# Install shared packages and app in editable mode
pip install -e packages/core-types -e packages/model-harness -e packages/shared-ui -e apps/artifice-graph
```

### Local Model Requirements (Default)
Ensure Ollama is running locally with your extraction and embedding models:
```bash
# Extraction model
ollama pull gemma2:27b

# Embedding model for semantic entity deduplication
ollama pull bge-m3

ollama serve
```

### macOS & Apple Silicon Notes
- Ollama runs `bge-m3` embeddings and LLM extraction natively on Apple Silicon Metal GPUs.
- For Docker execution, use `http://host.docker.internal:11434` for model connections.

---

## 🖥️ Usage & Interfaces

### 1. CLI Commands
```bash
# Run full pipeline end-to-end:
artifice-graph run-all data/input_ocr/

# Run individual stages:
artifice-graph ingest data/input_ocr/
artifice-graph extract --model gemma2:27b
artifice-graph resolve-entities --semantic
artifice-graph build-vault
artifice-graph build-graph

# Run incremental mode (skip unchanged files):
artifice-graph run-all --incremental

# Demo mode (No LLM required):
artifice-graph demo
```

### 2. Web UI (Recommended)
Launches the FastAPI backend with The New Masses editorial controls, live streaming logs, and entity library browser:
```bash
python -m artifice_graph.web
```

---

## ⚙️ Configuration

ArtificeGraph reads settings from `config.yaml` or environment variables:

| Section | Key | Default | Description |
|---|---|---|---|
| `llm` | `base_url` | `http://localhost:11434` | LLM API endpoint |
| `llm` | `model` | `gemma2:27b` | Model used for extraction |
| `embedding` | `model` | `bge-m3` | Model used for semantic deduplication |
| `ingestion` | `chunk_size` | `2000` | Character count per sliding chunk |
| `ingestion` | `chunk_overlap` | `200` | Overlap between adjacent chunks |
| `entity_resolution` | `use_semantic` | `true` | Enable bge-m3 semantic deduplication |
| `entity_resolution` | `aliases_file` | `data/aliases.yaml` | Manual entity merge overrides |

---

## 📂 Output Directory Structure

Executing the pipeline populates the `data/output/` directory with structured research artifacts:

```
data/
├── input_ocr/              # Primary source text files (.txt, .pdf, .md)
├── output/
│   ├── entities.json           # Deduplicated canonical entities
│   ├── relationships.json      # Extracted relationships with evidence
│   ├── knowledge_graph.graphml # Gephi / yEd graph format
│   ├── knowledge_graph.gexf    # Native Gephi format with visual attributes
│   ├── knowledge_graph.json    # JSON node-link format
│   ├── knowledge_graph.cypher  # Neo4j CREATE statements
│   ├── knowledge_graph_nodes.csv # Spreadsheet node table
│   └── knowledge_graph_edges.csv # Spreadsheet edge table
├── obsidian_vault/         # Output Obsidian vault directory
│   ├── 01_Sources/         # Primary source notes with Dataview metadata
│   └── 02_Entities/        # Categorized entity notes (Persons, Locations, etc.)
└── aliases.yaml            # Manual entity resolution override rules
```

---

## 🛠️ Open-Source Extension Points

We welcome contributions from historical researchers, digital humanists, and software engineers!

1. **Custom Entity Types & Extraction Schemas (`apps/artifice-graph/src/models/`)**: Extend default entity categories (*Person*, *Organization*, *Location*, *Event*, *Concept*) with domain sub-types (e.g., *Diplomatic Mission*, *Archival Record Group*).
2. **Graph Exporters (`apps/artifice-graph/src/exporters/`)**: Implement custom graph serializers (e.g., RDF/Turtle, Graphviz DOT, or custom web visualizers).
3. **Obsidian Templates (`apps/artifice-graph/src/exporters/obsidian_exporter.py`)**: Customize Markdown metadata fields and Dataview query templates.

---

## 🧪 Testing

Run the offline pytest suite covering document chunking, fuzzy/semantic deduplication, NetworkX exports, and Obsidian vault generation:
```bash
pytest apps/artifice-graph/tests/
```

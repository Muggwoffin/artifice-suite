# PersonaeGraph — Expansion Plan

> **Legacy name:** CallOsip  
> **New name:** PersonaeGraph  

This document outlines a phased expansion plan for PersonaeGraph, transforming it from a general-purpose entity extraction pipeline into a tailored tool for historians building, curating, and exploring knowledge graphs from primary sources.

## Table of Contents

1. Current State
2. Phase 1: Foundations
3. Phase 2: Enhanced Research Tools
4. Phase 3: Advanced Analysis & Automation
5. Cross-Cutting Concerns
6. Implementation Roadmap
7. Success Metrics

---

## 1. Current State

### 1.1 Capabilities

| Area | Description |
|---|---|
| Entity types | Person, Location, Event, Organization, Concept |
| Relationship extraction | Typed, with confidence scores and evidence quotes |
| Entity resolution | Fuzzy (0.93) + semantic (bge-m3 0.85) with YAML alias overrides |
| Obsidian export | Dataview frontmatter, wikilinks, source/entity notes |
| Graph export | GraphML, GEXF, JSON, CSV, Cypher (Neo4j) |
| Interfaces | CLI (Typer) and GUI (tkinter) |
| LLM support | Ollama and OpenAI-compatible |
| Incremental mode | Content-hash tracking for unchanged files |
| Pipeline isolation | 5 independent stages with error isolation |

### 1.2 Gaps for historian workflows

- No temporal awareness (centuries, periods, reigns)
- No provenance tracking (OCR source, quality, versions)
- No importance or significance scoring for entities
- Single static graph – no versioning or comparison
- No guided discovery or recommendation
- No collaboration features

---

## 2. Phase 1 — Foundations

### 2.1 Rename and rebrand

Rename the entire project from CallOsip to PersonaeGraph:

| File | Change |
|---|---|
| pyproject.toml | name, description, entry point |
| README.md | headers, tagline, CLI examples |
| gui.py | window title, log prefix |
| cli.py | app name and help |
| src/graph_pipeline/\*.py | constants, class names, docstrings |

### 2.2 Entity subtypes

Add an optional `sub_type` field to the Entity model:

- Person: Statesman, Monarch, Military_Leader, Scholar, Clergy, Merchant, Artist, Commoner
- Organization: Government, Ministry, Military, Church, Guild, Corporation, Political_Faction
- Location: Country, Region, City, Artefact, Natural_Feature, Border, Territory
- Event: Battle, War, Treaty, Congress, Coronation, Marriage, Revolution, Expedition
- Concept: Political, Economic, Legal, Religious, Cultural, Scientific

Backward compatible: default value is "".

### 2.3 Temporal awareness

Implement a TimeSpan model:

```yaml
TimeSpan:
  start_year: int | null
  end_year: int | null
  century: int | null  # e.g. 19 for 19th
  period_label: str  # e.g. Napoleonic Era
  precision: str  # year | decade | century | millennium | precise
  certainty: float  # 0-1
```

TimeSpan is attached to:
- Entity – lifespan or period of significance
- Relationship – parse existing time_frame into structured TimeSpan
- Document – source date

New module: `time_parser.py` to normalize strings like "1809-1848", "ca. 450 BC", "late 18th c.".

### 2.4 Provenance tracking

Provenance model tracks the extraction lineage:

```yaml
Provenance:
  ocr_engine: str
  ocr_confidence: float  # 0-1
  extraction_confidence: float
  review_status: str  # unreviewed | verified | disputed | rejected
  reviewer_notes: str
  version: int
```

Attach to Entity and Relationship.

### 2.5 Entity importance scoring

importance_score (float 0-1) computed from:
- degree centrality in the NetworkX graph
- source document coverage count
- relationship diversity
- optional manual user override

Exported as node size in GEXF, sortable in Obsidian, ordering in CLI reports.

---

## 3. Phase 2 — Enhanced Research Tools

### 3.1 Setup wizard

`personaegraph init` interactive wizard:

- historical period and region
- active entity types to extract
- LLM backend and model selection
- dedup threshold tuning
- research templates: Medieval Genealogies, Revolutionary Figures, Congresses

Outputs a `personaegraph.yaml` with tuned defaults.

### 3.2 Historical timeline

Obsidian integration:
- Generate a Timeline note compatible with the Obsidian Timeline plugin
- Chronological groups by century, decade, and year

Graph side:
- GEXF temporal node attributes for Gephi timeline plugin
- JSON exports with time-bucketed node/edge groups for D3.js

### 3.3 Subgraph extraction

`personaegraph subgraph` command:
- Extract k-hop neighborhoods around seed entities
- Filter by: period, entity type, subtype, importance
- Results as standalone GraphML, Obsidian sub-vault, or Cypher script

Pre-built filtering modes: by-period, by-type, by-role, by-importance.

### 3.4 Recommendation engine

Given a seed entity or set of entities:

- Gap entities: co-occur in sources but not yet linked
- Bridge nodes: entities that connect disconnected subgraphs
- Contemporaries: overlapping TimeSpan not yet linked

Backend: common neighbors, Adamic-Adar, Jaccard on the NetworkX graph.

### 3.5 Improved visualisation

- GEXF: node sizing by importance, edge thickness by confidence, color saturation by provenance
- Obsidian: importance badges, sorted entity lists
- CLI: top-k importance reports
- GUI: collapsible entity details and graph preview

---

## 4. Phase 3 — Advanced Analysis & Automation

### 4.1 Context-aware LLM extraction

DynamicPromptBuilder that adapts the extraction prompt:
- Injects historical period and region
- Scopes to active entity types
- Uses graph state as few-shot examples
- Flags anachronistic language in the output

### 4.2 Graph versioning

Support for competing hypotheses:

```
data/graphs/
  main/
    v1/
    v2/
    current -> v1 /
  experimental /
    v1 /
    current -> v1 /
```

personaegraph branch and personaegraph merge commands.

### 4.3 Citation export

Generate citation files from the knowledge graph:
- Chicago, MLA, and BibTeX formats
- group by topic, period, or entity
- export as .bib and .json files

### 4.4 Collaborative curation

Web-based review interface (FastAPI + htmx):

- Entity and relationship review queue
- Side-by-side diff across pipeline runs
- Annotations and comments per entity
- User roles: viewer, editor, admin

### 4.5 Semi-automated extraction

Interactive mode for the CLI and GUI:

- Pause after each batch of extractions for user review
- Accept, reject, or modify entities/relationships before proceeding
- User edits become few-shot examples for subsequent batches

### 4.6 Multi-source merging

Merge knowledge graphs from different source corpuses:

- reconcile entity identity across graphs
- union-find merging of conflicting relationships
- weighted importance fusion

### 4.7 Knowledge base augmenter

Integrate with external historical databases (WikiData, VIAF, DNB):

- entity ID cross-referencing
- enrich entities with external metadata
- validate and auto-fill missing information

---

## 5. Cross-Cutting Concerns

### 5.1 Backward compatibility

- Old output files (entities.json, relationships.json) remain loadable
- Old config.yaml works with PersonaeGraph
- New fields are optional with sensible defaults

### 5.2 Testing

New tests for:
- time_parser.py
- importance scoring
- subgraph extraction and filtering
- recommendation engine
- each phase milestone

### 5.3 Documentation

New pages for:
- Historian quick start guide
- Research template configurations
- API reference
- Glossary of PersonaeGraph concepts

### 5.4 Performance

- TimeSpan queries via numpy masking or sortedcontainers
- Importance computation parallelized
- Large graph subgraph extraction with lazy loading

---

## 6. Implementation Roadmap

### 6.1 version 1.0 (current)
CallOsip baseline: working pipeline with CLI, GUI, Obsidian and Graph exports.

### 6.2 version 2.0 target (Phase 1)
- rename and rebrand complete
- Entity subtypes in the core model
- TimeSpan and time_parser.py
- Provenance tracking in the data model
- Importance scoring and export (GEXF, Obsidian, CLI)

### 6.3 version 3.0 target (Phase 1 + 2)
- 2.0 features stabilized
- Setup wizard
- Timeline generator in Obsidian
- Subgraph extraction and filtering
- Recommendation engine
- improved visualisation

### 6.4 version 4.0 target (Phase 1 + 2 + 3)
- 3.0 features stabilized
- Dynamic prompt builder
- Graph versioning and branching
- Citation export
- Collaborative curation backend
- Semi-automated extraction
- Multi-source merging
- external knowledge base enrichment

---

## 7. Success Metrics

| Metric | Description | target |
|---|---|---|
| Pipeline throughput | Time to extract graph from a 10-page source | <60 seconds |
| Extraction accuracy | Correct detection of entities and relationships | >80% for entities |
| Entity resolution precision | Non-deduplication of distinct entities | <5% false merge |
| User adoption | Historians using PersonaeGraph regularly | >50 active users |
| Graph size | Max nodes/edges before noticeable slowdown | >5000 nodes |
| Backward compatibility | Old outputs loadable by newer versions | 100 % |

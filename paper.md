---
title: 'Artifice Suite: Local-First, Bring-Your-Own-Model Tools for Historians'
tags:
  - Python
  - digital humanities
  - optical character recognition
  - knowledge graphs
  - oral history
  - speech transcription
  - local-first software
  - large language models
  - BYOM
  - open source software
authors:
  - name: Maurice J. Casey
    orcid: 0000-0001-6019-3578
    affiliation: 1
affiliations:
  - name: Queen's University Belfast
    index: 1
date: "TODO(author): fill in submission date,
license: AGPL-3.0-or-later
bibliography: paper.bib
---

<!--
JOSS paper. Sections below marked "TODO(author)" require your own voice,
claims, and judgment — do not fill them in with generated text. Sections
without that marker (Summary, Architecture Overview) are drafted from direct
inspection of the repository and are meant as a factual starting point for
you to edit, not a final draft.
-->

## Summary

Artifice Suite is a collection of four local-first, bring-your-own-model
(BYOM) desktop tools for historians and archivists, each built around a
structured "harness" architecture rather than a conversational chat
interface:

- **artifice-ocr** — extracts text from scanned historical documents (image
  or PDF) using a vision-language OCR model (`allenai/olmocr-2-7b` by
  default via Ollama or an OpenAI-compatible endpoint [@poznanski2025olmocr2;
  @poznanski2025olmocr]), with staged cleanup, structuring, and translation,
  and export to PDF or Tropy-compatible formats.
- **artifice-draft** — sends `.docx` paragraphs to an LLM and returns the
  document with copy-edit suggestions applied as native Word tracked
  changes, with configurable journal style guides (Chicago 17th
  [@chicago2017manual], MLA 9th [@mla2021handbook], APA 7th
  [@apa2020manual]) and historian-specific checks (citation format, date
  standardization, archival reference validation, foreign-phrase
  consistency).
- **artifice-graph** — extracts entities and typed relationships from
  historical text via an LLM, resolves duplicate entities (fuzzy string
  matching plus `bge-m3` semantic embedding dedup), and exports the result
  as a NetworkX-based knowledge graph [@hagberg2008networkx] (GraphML,
  GEXF, JSON, CSV, or Cypher) or an Obsidian vault of interlinked notes.
- **artifice-transcribe** — transcribes oral history audio with WhisperX
  [@bain2023whisperx] and performs speaker diarization with pyannote.audio
  [@bredin2023pyannote; @bredin2020pyannote], exposed through a FastAPI
  service with a review/export web UI.

All four apps share a common `src/`-layout Python package structure, a
`packages/model-harness` connector contract for BYOM model calls (Ollama,
LM Studio, or any OpenAI-compatible endpoint), and a common design system
(`Design_Philosophy.md`) for their web interfaces. Each app runs entirely
on the user's own machine (or a self-hosted container) against a
locally-run or self-selected model backend; no document, audio, or API key
is transmitted to a third party by the software itself. 
Should they choose, users can connect an API key to a hosted model backend. 
Any cloud access must be enabled explicitly to avoid accidental 
contravention of data privacy.

## Statement of need

<!-- TODO(author): Write this yourself. JOSS reviewers weight this section
heavily. Questions to answer, in your own words and with your own citations
to the archival/historical-methods literature:
  - Who is the target user (historians, archivists, oral historians,
    digital humanities practitioners), and what task were they doing
    before this existed?
  - What gap does BYOM/local-first fill that a hosted/SaaS tool
    (e.g. sending documents to a cloud OCR or transcription API) does not —
    privacy of unpublished archival material, cost at scale, institutional
    data-handling policy, offline archives access?
  - Why four separate apps sharing one harness rather than one monolith,
    or than using each underlying model/library directly?
  - What existing research workflow or publication does this support
    (your own prior project, a specific archive, a course)? -->

## State of the field

<!-- TODO(author): Write this yourself with citations. This should
position each app against the closest existing tools you are aware of, e.g.:
  - artifice-ocr vs. Transkribus, Tesseract-based pipelines, or other
    LLM-vision OCR wrappers
  - artifice-draft vs. Grammarly/ProWritingAid, LanguageTool, or other
    LLM copy-editing scripts
  - artifice-graph vs. other LLM-based GraphRAG/entity-extraction tools,
    manual Obsidian/Zotero-based knowledge management, or structured-markup
    approaches like TEI [@tei2024guidelines] for encoding entities/relations
    in historical text
  - artifice-transcribe vs. OHMS [@boyd2013ohms], otter.ai, or other
    oral-history-specific transcription platforms
Be specific about what is actually different (local-first BYOM + harness
architecture + historian-specific validators), not just "it uses AI." -->

## Architecture overview

Every app follows the same layout: a `src/<app>/` Python package installed
in editable mode via its own `pyproject.toml`, a `tests/` directory run
with `pytest`, and (where applicable) a `web/` FastAPI interface following
the shared design system. The suite is organized as a `uv` workspace
(root `pyproject.toml`), so all four apps and the shared
`packages/model-harness` package install together with a single command,
while remaining independently installable and independently versioned.

All LLM-backed features go through a structured call: the app sends a
schema-constrained prompt and parses a typed response (via Pydantic
models), rather than treating the model as a conversational partner. This
is enforced as a project convention (see `CONTRIBUTING.md`) rather than by
a single shared runtime at present — `packages/model-harness` currently
defines the shared connector configuration contract
(`ModelConnectorConfig`), with each app's own LLM client implementing the
actual request/response handling against Ollama, LM Studio, or a generic
OpenAI-compatible endpoint.

## AI usage disclosure

<!-- TODO(author): JOSS asks submitters to disclose the role of generative
AI tools in producing the software and/or the paper. Write your own
factual account here — e.g., which parts of the codebase were written,
reviewed, or refactored with AI assistance (this repository's history and
CLAUDE.md/.claude/ configuration are relevant primary sources for this),
and what your own role was in design, review, and validation. Do not let
this be written on your behalf. -->

## Acknowledgements

<!-- TODO(author): Acknowledge funding, institutional support, or
individuals who provided feedback, if any. -->

## References

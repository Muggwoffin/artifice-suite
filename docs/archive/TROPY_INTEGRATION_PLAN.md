# Tropy Integration & Auto-Title Plan (Artifice Suite)

## Overview

This document specifies the unified integration plan for connecting [Tropy](https://tropy.org) historical research archives with the Artifice Suite (`artifice-ocr`, `artifice-graph`, `artifice-draft`), including the optional auto-generation of page-level archival titles using the local cleanup model.

---

## Architecture & Core Decisions

1. **Hybrid Approach:** The JSON-LD file bridge remains the primary, safe default for all users. An opt-in, guarded live read-only `.tpy` browse mode is available via config/env flag (`ARTIFICE_OCR_TROPY_LIVE_READ`), opening SQLite databases in `mode=ro` with short-lived per-query connections and clean `SQLITE_BUSY` handling.
2. **Cross-App Data Flow:** `artifice-graph` consumes OCR provenance via a **documented manifest contract** (a versioned sidecar/extension of `tropy_manifest.json`) rather than coupling to OCR's private `history.db`.
3. **Deployment Security:** The server binds strictly to loopback (`127.0.0.1`); non-loopback bindings refuse to start. This resolves security surface item 5.2b regarding unauthenticated routes in deployed instances.
4. **Harness & Contract Discipline:** All model interactions — including the new auto-title generation stage — strictly flow through `packages/model-harness/src/model_harness/contract.py` with required Pydantic schemas, mode degradation tracking (`mode_used`), and repair auditing.
5. **Stale Code Clean-Up:** Removes references to the retired SQLite modules (`tropy.py`, `tropy_read.py`, `tropy_write.py`) from READMEs, tests, and baselines.

---

## Detailed Workstreams

### Workstream 1: File-Bridge UX Deepening (`artifice-ocr`)
- **Auto-Watch Directory:** Configurable `tropy_watch_dir` (validated against `ARTIFICE_OCR_ALLOWED_ROOTS`). Automatically detects incoming `.json` / `.jsonld` exports, parses via `tropy_jsonld.load_export`, and surfaces an in-app import notification.
- **Drag-and-Drop Ingestion:** Wire the web dropzone directly to `load_export_content`, following the transcribe upload-contents pattern.
- **One-Click Round-Trip Write-Back:** Generates the export `.jsonld`, reveals the file in the OS file manager, and presents copy-pasteable re-import steps with a "copy path" action in the success modal. Gate writes behind the existing preview verification.
- **Workflow Memory:** Persist active project, export, and output directories in `~/.artifice_ocr/settings.json` using the secure `write_private_json` restrict-to-current-user pattern (commit `18f5808` discipline).
- **Inline Safety & Error Surfacing:** Surface pathcheck rejections, missing photo warnings, and `TropyImportError` reasons inline within `modal-tropy-add`. Add a pre-flight validation check using `validate_absolute_photo` prior to queueing items.

### Workstream 2: Optional Live Read-Only `.tpy` Browse (`artifice-ocr`)
- **`tropy_db.py` Library Module:** Pure Python library layer (no FastAPI imports). Opens `.tpy` files using URI connection strings (`file:<path>?mode=ro`, `uri=True`).
- **Feature Flag Gating:** Controlled by `ARTIFICE_OCR_TROPY_LIVE_READ`. Routes mount only when enabled.
- **Direct Enqueue:** Browsed items map directly to `JobItem` instances via `photos_to_job_items`, bypassing manual export round-trips while reusing the existing pathcheck and normalization logic.

### Workstream 3: Provenance Continuity (`artifice-ocr` → `artifice-graph`, `artifice-draft`)
- **History UI & LudwigLang Export:** Surface provenance chips (`item_title`, `tropy_group`, relative photo path) in the OCR History view. Extend LudwigLang frontmatter with `tropy_item_id` and archive references where resolvable.
- **Manifest Contract for Graph:** Define a versioned JSON schema sidecar to `tropy_manifest.json` emitted during OCR export. `artifice-graph` parses this sidecar to construct knowledge graph nodes annotated with archive references, item IDs, and per-page confidence.
- **Draft Notes Round-Trip:** `artifice-draft` pulls Tropy notes from the file bridge envelope or browsed items, performs copy-editing, and pushes notes back through the export note shape (`_note_html` / `ExportPhoto`), maintaining local-first file-based isolation.

### Workstream 4: Auto-Generated Page Titles
- **Stage Integration:** A new optional pipeline stage running after OCR / normalization, utilizing the configured `cleanup_model` and `cleanup_backend`.
- **Harness Compliance:** Implemented via `model_harness.contract.StructuredRequest` with a required Pydantic schema:
  ```python
  class PageTitleSchema(BaseModel):
      title: str = Field(..., max_length=120, description="Short archival title reflecting page content")
      language: str = Field(..., description="Detected source language of the page")
  ```
- **Language Policy:** Titles are generated in the source language of the transcribed text.
- **Guard Enforcement:**
  - **Length Cap:** Max 120 characters / words threshold; truncated or retried if exceeded.
  - **Accent Preservation:** Rejects title modifications introducing diacritics absent in the source (reusing `_guard` umlaut checks).
  - **Repetition Check:** Rejects token loops or repetitive substring echoes.
  - **Provenance Marker:** Every title carries a metadata flag `generated_by_model: true` and records the model name, ensuring it is never conflated with original human-authored Tropy item titles.
- **Destinations:** Stored in stage metadata JSON, added as a History DB column (`generated_title`), written into LudwigLang frontmatter, and optionally mapped into the Tropy export note title field upon re-import.

### Workstream 5: Security Hardening (Addressing 5.2b)
- **Loopback Enforcement:** FastAPI servers refuse startup if bound to any non-loopback interface.
- **Path Echo Elimination:** Audit all Tropy, PDF, and LudwigLang export routes (`ludwiglang.py:53-54` etc.) to guarantee resolved server-side absolute paths are never echoed in HTTP error details or logs. Add a test suite asserting HTTP responses contain no absolute path substrings.
- **Exception Reflection Fix:** Correct graph's `api_get_models` error handler to return a generic message rather than reflecting raw exception text containing Bearer tokens.

### Workstream 6: Build & Verification Gate
- **Packaging Inspection:** Build wheels via `scripts/build-wheel.sh` and inspect contents via Python's `zipfile` module to ensure all assets are correctly bundled.
- **Test Suite Execution:** Run pytest across all apps (`uv run pytest`), ruff linting, and `gitleaks detect` prior to completion.
- **Documentation Parity:** Ensure `CITATION.cff` remains untouched and monorepo modularity conventions are strictly respected.

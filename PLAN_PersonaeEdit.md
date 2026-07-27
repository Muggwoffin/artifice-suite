# ArtificeDraft — Transformation Plan

## Overview

Transform the **Copy Edit** tool into **ArtificeDraft**, an academic editing tool purpose-built for historians and humanities scholars. The rebrand is a full rename (directory, files, code, UI). The core new feature is a **journal style guide system** — JSON config files for Chicago, MLA, and APA that the LLM reads as system prompt context, replacing or supplementing the generic editing presets. Six additional historian-specific modules provide citation validation, date standardization, Latin phrase handling, archival reference formatting, cross-document consistency checking, and word count/page estimation.

Requires Python 3.10+.

---

## Phase 1: Full Rename — CopyEdit → ArtificeDraft

Rename all references across ~25 files (~73 occurrences).

### Directory

```
CopyEdit Tool/  →  ArtificeDraft/
```

### Files to rename on disk

| Old name | New name |
|---|---|
| `launch_copyedit.pyw` | `launch_personae.pyw` |
| `launch_copyedit_web.pyw` | `launch_personae_web.pyw` |
| `assets/copyedit.ico` | `assets/artifice_draft.ico` |
| `assets/copyedit_preview.png` | `assets/artifice_draft_preview.png` |
| `assets/copyedit_web.ico` | `assets/artifice_draft_web.ico` |
| `assets/copyedit_web_preview.png` | `assets/artifice_draft_web_preview.png` |
| `Copy Editor.lnk` | `ArtificeDraft.lnk` |
| `Copy Editor (Web).lnk` | `ArtificeDraft (Web).lnk` |

### In-code references by category

| Category | Files affected | Example |
|---|---|---|
| Config paths `~/.copyedit/` | `launch_copyedit.pyw`, `launch_copyedit_web.pyw`, `src/web/runtime.py` | → `~/.artifice_draft/` |
| Env sentinels `COPYEDIT_*` | `launch_copyedit.pyw`, `launch_copyedit_web.pyw` | → `PERSONAE_*` |
| UI titles "Copy Editor" | `src/gui.py`, `src/web/server.py`, `src/web/static/index.html` | → "ArtificeDraft" |
| Default author "AI Copy Editor" | `src/config.py`, `src/doc_writer.py`, `src/_track_changes.py` | → "ArtificeDraft" |
| JS globals `CopyEditorApp` | `src/web/static/js/app.js`, `src/web/static/js/review.js` | → `ArtificeApp` |
| Log filename `copyedit.log` | `src/log_setup.py` | → `artifice_draft.log` |
| Changelog header | `src/changelog.py` | "COPY EDIT — CHANGE SUMMARY" → "PERSONAEEDIT — CHANGE SUMMARY" |
| Prompt identity | `src/prompts.py` | "professional copy editor" → "academic editor specialising in humanities scholarship" |
| Icon target paths | `scripts/make_icon.py`, `scripts/make_web_icon.py` | `copyedit.ico` → `artifice_draft.ico` |
| Shortcut descriptions | `scripts/make_shortcut.ps1`, `scripts/make_shortcut_web.ps1` | "Copy Editor" → "ArtificeDraft" |
| README / CLAUDE.md | `README.md`, `CLAUDE.md` | Full text rebrand |
| Test references | `tests/test_web.py` | `~/.copyedit/` → `~/.artifice_draft/` |

### Verification

After rename, run `python -m pytest tests/` and grep the repo for any remaining `copyedit` or `Copy Editor` references.

---

## Phase 2: Journal Style Guide System

### New module: `src/style_guides/`

```
src/style_guides/
├── __init__.py      # list_guides(), load_guide(name), load_guide_by_path(path), list_custom_guides()
├── base.py          # StyleGuide dataclass (the schema)
├── chicago.py       # Built-in Chicago Manual of Style 17th ed.
├── mla.py           # Built-in MLA 9th ed.
└── apa.py           # Built-in APA 7th ed.
```

### `StyleGuide` dataclass (`src/style_guides/base.py`)

```python
@dataclass
class StyleGuide:
    name: str                      # "Chicago Manual of Style"
    edition: str                   # "17th Edition"
    citation_style: str            # "notes-bibliography" | "author-date"
    footnote_format: str           # Footnote formatting rules (free text for LLM)
    bibliography_format: str       # Bibliography formatting rules
    heading_capitalization: str    # "title-case" | "sentence-case"
    prose_rules: list[str]         # Specific prose conventions
    quotation_rules: str           # Single vs double quotes, block quote threshold
    abbreviation_rules: str        # Latin abbreviations, acronyms
    date_format: str               # Preferred date formatting
    page_reference_format: str     # "p. 12" vs "12" vs "page 12"
    url_format: str                # URLs / retrieval dates
    system_prompt_addendum: str    # Full text injected into LLM system prompt
    custom_rules: list[str]        # User-added rules
```

### Built-in guides

Each guide is a Python function returning a populated `StyleGuide`:

- **Chicago** (`chicago.py`): Notes-bibliography system, footnote format (`First Last, *Title* [Place: Publisher, Year], page.`), Title Case headings, serial comma required, footnotes over endnotes, em-dash rules, date format "12 March 1945", lowercase after colons
- **MLA** (`mla.py`): In-text parenthetical `(Author Page)`, Works Cited formatting, sentence-case titles, container-based citation model, present tense for literary analysis
- **APA** (`apa.py`): Author-date `(Author, Year, p. X)`, Reference List, sentence-case article titles, DOIs required, active voice, bias-free language rules

### Custom style guides

Users can create guides via two methods:

1. **In-app structured form** (GUI + web): Labeled fields for each `StyleGuide` property. Saved to `~/.artifice_draft/style_guides/<name>.json`.
2. **JSON file import**: File picker that copies a `.json` file into `~/.artifice_draft/style_guides/`. JSON schema matches the `StyleGuide` dataclass fields.

Custom guides appear alongside built-ins in all UIs.

### Pipeline integration

| File | Change |
|---|---|
| `src/models.py` | Add `EditingStyle.JOURNAL` enum value |
| `src/config.py` | Add `style_guide: str | None = None` field |
| `src/prompts.py` | New `get_journal_prompt(guide: StyleGuide) -> str` — builds system prompt from guide rules + base editing instructions |
| `scripts/run_edit.py` | Add `--style-guide chicago\|mla\|apa\|<path>` CLI flag |
| `src/gui.py` | Add Journal Guide dropdown (built-in + custom) in settings panel |
| `src/web/server.py` | Add `GET /api/style-guides` and `POST /api/style-guides` endpoints |
| `src/web/runtime.py` | Wire style guide into pipeline config |
| `src/web/static/index.html` | Add style guide selector + custom guide editor panel |
| `src/web/static/js/app.js` | Style guide API integration, editor form logic |

### Config file locations

```
~/.artifice_draft/
├── web_settings.json
├── launcher.log
├── launcher_web.log
└── style_guides/           # Custom guides directory
    ├── journal_of_modern_history.json
    └── past_and_present.json
```

---

## Phase 3: Historian-Specific Features

Six new modules, each independent and developed in parallel.

### 3a. Citation Checker (`src/citation_checker.py`)

Validates footnote formatting and consistency against the active journal guide.

**Capabilities:**
- Detects footnote markers (`[^1]`, superscript numbers, `*` suffixes) and checks formatting
- Flags inconsistent citation formats within the same document
- Reports orphan footnotes (marker referenced but no corresponding note body, or vice versa)
- Validates footnote numbering sequences (no gaps, no duplicates)

**Integration:** Post-LLM advisory. Warnings feed into the review panel and change summary "Style Advisory" section.

### 3b. Date Standardizer (`src/date_standardizer.py`)

Normalizes date formats to journal preference.

**Capabilities:**
- Detects ambiguous dates ("3/4/1918" → flags for clarification since it could be March 4 or April 3)
- Standardizes to journal preference:
  - Chicago: "12 March 1945"
  - MLA: "12 Mar. 1945"
  - APA: "March 12, 1918"
- Handles historical date ranges ("1914–1918"), centuries ("12th century"), approximate dates ("c. 1450", "ca. 12th century")
- Handles split-era dates ("3 January 1776 / 14 January 1776" Old Style/New Style)

**Integration:** Post-LLM formatting pass with advisory warnings.

### 3c. Foreign Phrase Handler (`src/foreign_phrases.py`)

Checks Latin and foreign phrase conventions.

**Capabilities:**
- Detects Latin phrases (et al., ibid., op. cit., loc. cit., cf., e.g., i.e., etc., sic, passim, vid., s.v.) and checks italicization per journal rules
- Flags inconsistent use of "et al." vs "and others"
- Validates "ibid." usage (Chicago allows it; MLA prefers "Ibid.")
- Detects unmarked foreign phrases that should be italicized

**Integration:** Post-LLM advisory.

### 3d. Archival Reference Formatter (`src/archival_refs.py`)

Parses and validates archival citation formats.

**Capabilities:**
- Parses standard archival citation components: Repository, Collection/Group, Series, Box, Folder, File, Item, Date
- Validates against Chicago's archival citation model
- Flags incomplete references (missing repository name, date, or box/folder number)
- Suggests standardized formatting for partial references

**Integration:** Post-LLM advisory with suggested corrections.

### 3e. Consistency Reporter (`src/consistency.py`)

Cross-document consistency checks.

**Capabilities:**
- Flags inconsistent capitalization of proper nouns (e.g., "Byzantium" vs "byzantium")
- Detects inconsistent spelling of the same name ("Machiavelli" vs "Machiavel")
- Reports inconsistent use of titles and forms of address ("President Lincoln" vs "Lincoln" vs "Abraham Lincoln" vs "Mr. Lincoln")
- Detects inconsistent transliterations of non-English names

**Integration:** Post-LLM advisory with a full consistency report.

### 3f. Word Count & Page Estimate (extend `src/changelog.py`)

Extend the existing `ChangeSummary` dataclass.

**New fields:**
- `word_count_before: int`
- `word_count_after: int`
- `character_count: int`
- `estimated_pages: float` (250 words/page for double-spaced academic prose)

Displayed in the change summary header and web UI result panel.

### Advisory pipeline

All advisory modules follow the same pattern:

1. Receive the edited paragraphs + active style guide
2. Return a list of `StyleAdvisory` objects: `{paragraph_index, rule, message, severity, suggested_fix}`
3. Advisories are:
   - Displayed in the review panel (web) or CLI review output
   - Included in the change summary as a "Style Advisory" section
   - Optionally auto-fixable by re-running the LLM with the advisories as additional context

---

## Phase 4: Prompt Engineering Rewrite

### Layered prompt system in `src/prompts.py`

| Layer | Content | When present |
|---|---|---|
| **Base** | Core editing instructions — grammar, clarity, phrasing, return JSON format | Always |
| **Style** | Journal-specific formatting and citation rules from the active `StyleGuide.system_prompt_addendum` | When a journal guide is selected |
| **Domain** | Historical writing conventions — past tense for events, present tense for discussing texts, handling archaic terminology, proper use of scare quotes for period terms | When editing style is JOURNAL or ACADEMIC |

The existing presets (ACADEMIC, CREATIVE, CONCISE, BUSINESS) remain. When JOURNAL is selected, the prompt is: base + style guide + domain conventions.

---

## Phase 5: Tests

### Updated existing tests

- All test files updated for renamed paths, strings, and config locations
- `tests/test_web.py`: Mock `~/.artifice_draft/` instead of `~/.copyedit/`
- `tests/test_prompts.py`: Tests for new `get_journal_prompt()` and JOURNAL style
- `tests/test_llm_client.py`: Tests with style guide context in prompts

### New test files

| Test file | Coverage |
|---|---|
| `tests/test_style_guides.py` | `StyleGuide` dataclass, `list_guides()`, `load_guide()`, `load_guide_by_path()`, JSON roundtrip for custom guides, guide fields match expected values |
| `tests/test_citation_checker.py` | Footnote detection, inconsistent format flagging, orphan detection, valid footnote passes |
| `tests/test_date_standardizer.py` | Ambiguous date detection, format normalization per guide, date ranges, approximate dates |
| `tests/test_foreign_phrases.py` | Latin phrase detection, italicization check, ibid./et al. validation |
| `tests/test_archival_refs.py` | Component parsing, incomplete reference flagging, format validation |
| `tests/test_consistency.py` | Proper noun inconsistency detection, title form flagging, transliteration variants |
| `tests/test_style_guides_api.py` | Web API endpoints for listing, creating, importing custom guides |

---

## Implementation Order

| Step | Phase | Estimated scope |
|---|---|---|
| 1 | Rename | ~25 files, mechanical changes, no logic |
| 2 | Style guide system | New module + integration into pipeline, CLI, GUI, web |
| 3a–3f | Historian features | 6 new modules (independent, parallel) |
| 4 | Prompt rewrite | Depends on style guide system |
| 5 | Tests | Interleaved with each phase |

### Verification checklist

- [ ] `python -m pytest tests/` passes after each phase
- [ ] `grep -ri "copyedit\|copy.editor\|Copy Editor" --include="*.py" --include="*.js" --include="*.html" --include="*.css" --include="*.md" --include="*.ps1"` returns no hits after Phase 1
- [ ] `python scripts/run_edit.py --styles` lists Chicago, MLA, APA, and custom guides
- [ ] `python scripts/run_edit.py --style-guide chicago --headless test.docx` applies Chicago rules
- [ ] GUI dropdown shows all style guides including custom ones
- [ ] Web UI style guide selector works end-to-end
- [ ] Each historian module produces advisories for a test document with known issues
- [ ] Custom guide JSON import creates a usable guide
- [ ] In-app custom guide editor saves and loads correctly

---

## File Change Summary

### New files

```
src/style_guides/__init__.py
src/style_guides/base.py
src/style_guides/chicago.py
src/style_guides/mla.py
src/style_guides/apa.py
src/citation_checker.py
src/date_standardizer.py
src/foreign_phrases.py
src/archival_refs.py
src/consistency.py
tests/test_style_guides.py
tests/test_citation_checker.py
tests/test_date_standardizer.py
tests/test_foreign_phrases.py
tests/test_archival_refs.py
tests/test_consistency.py
tests/test_style_guides_api.py
PLAN_ArtificeDraft.md   (this document)
```

### Modified files

```
CLAUDE.md
README.md
requirements.txt
scripts/run_edit.py
scripts/make_icon.py
scripts/make_web_icon.py
scripts/make_shortcut.ps1
scripts/make_shortcut_web.ps1
src/__init__.py
src/models.py
src/config.py
src/prompts.py
src/gui.py
src/doc_writer.py
src/_track_changes.py
src/log_setup.py
src/changelog.py
src/review.py
src/web/server.py
src/web/runtime.py
src/web/static/index.html
src/web/static/js/app.js
src/web/static/js/review.js
tests/conftest.py
tests/test_doc_parser.py
tests/test_doc_writer.py
tests/test_llm_client.py
tests/test_prompts.py
tests/test_changelog.py
tests/test_review.py
tests/test_web.py
tests/test_revision_xml.py
```

### Renamed files

```
launch_copyedit.pyw        →  launch_personae.pyw
launch_copyedit_web.pyw    →  launch_personae_web.pyw
assets/copyedit.ico        →  assets/artifice_draft.ico
assets/copyedit_preview.png →  assets/artifice_draft_preview.png
assets/copyedit_web.ico    →  assets/artifice_draft_web.ico
assets/copyedit_web_preview.png →  assets/artifice_draft_web_preview.png
Copy Editor.lnk            →  ArtificeDraft.lnk
Copy Editor (Web).lnk      →  ArtificeDraft (Web).lnk
```

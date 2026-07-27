Handoff: Export Cleaned Documents to LudwigLang
================================================

Status: **PLAN ONLY — nothing in this document is implemented.** This is a
design handoff, written the same way as HANDOFF_PROMPT5.md, to hand to
whoever builds it next (human or agent). Read it before writing any code.


WHAT THIS WOULD DO
-------------------

Let a user take a cleaned document out of this pipeline's output and put it
into LudwigLang (a separate app — a German reading/vocabulary trainer at
`E:\Claude Sandbox\LudwigLang`) as a text to read and drill.

This pipeline produces cleaned OCR **per page**. LudwigLang consumes **whole
documents**. The job is: assemble pages into one document, map metadata into
LudwigLang's schema, gate on quality/language, then hand it off by one of
three transports.

This mirrors the existing Tropy integration (docs/TROPY_INTEGRATION.md,
src/ocr_pipeline/tropy.py / tropy_write.py / tropy_send.py) — that is the
proven template for "push a processed result to an external tool." Follow
its shape: a thin adapter module, a CLI command, and a GUI action, not a
redesign of either app.


THE DATA CONTRACT, AS VERIFIED
-------------------------------

**This side (source).** Cleaned output lives at:

    output/cleaned/text/<Collection>/<page>.txt   -- cleaned_text, plain
    output/cleaned/json/<Collection>/<page>.json  -- full record, see below

A cleaned JSON record (verified against output/cleaned/json/sample_document.json):

    {
      "source_file": "...",
      "stage": "cleaned",
      "raw_text": "...",
      "cleaned_text": "...",
      "engine": "ollama",
      "model": "gemma4:12b",
      "system_prompt": "...",
      "document_type": "default",
      "timestamp": "2026-07-22T07:20:48...",   -- PROCESSING time, not doc date
      "guard": {
        "ok": true,
        "reasons": [],
        "words_deleted": 0,
        "nouns_dropped": [],
        "length_ratio": 1.0
      }
    }

There is also a `translated/` stage (English) and a `structured/` stage —
**do not use either as the export source.** LudwigLang is a German-reading
tool; it needs the cleaned **original-language** text, not the translation.

Page ordering: files are named `<stem>_p0001.txt`, `_p0002.txt`, etc. (see
`Order Confirmation KV-2-481 (1)_p0001.json` / `_p0002.json` under
`output/cleaned/`). Sort lexicographically on this suffix to reassemble page
order — it already zero-pads correctly.

A `tropy_manifest.json` exists at `output/tropy_manifest.json` when a
collection originated from Tropy — this is the best available source of
real author/date/collection metadata (see tropy_read.py), better than
anything in the cleaned JSON.

**Other side (destination).** LudwigLang's import contract, verified against
`ludwiglang/routes_library.py`:

    POST /api/import
      { title: str, body: str, author?: str, date?: str,
        medium: "typed"|"handwritten"|"print", folder?: str }
      -> { id: <slug> }

    Writes: <data_dir>/texts/imported/<slug>/text.md
      ---
      id: <slug>
      source: imported
      title: <title>
      medium: <medium>
      language: de          <- HARDCODED. LudwigLang assumes German.
      author: <author>      (if given)
      date: <date>          (if given)
      ---

      <body>

    Limit: body must be <= 200,000 characters (HTTP 400 above that).

    A text also just works if it exists on disk as
    <data_dir>/texts/<any-source-name>/<id>/text.md with the same frontmatter
    shape — the library scans that whole tree. This is how transport C works
    with zero LudwigLang-side changes.

The import page's client-side drop handler (`web/static/import.js`) already
parses a dropped `.md` file's frontmatter (`title`, `author`, `date`,
`medium`) and fills the form — this is transport A below, and it requires
no server changes on either side.


THE BRIDGE ADAPTER
-------------------

One new module on this side, `src/ocr_pipeline/export_ludwiglang.py`,
responsible for four steps:

1. ASSEMBLY
   Group a collection's per-page files, sort by the `_pNNNN` suffix,
   concatenate `cleaned_text` with a blank line between pages. Page markers
   (e.g. a thin `-- 2 --` rule) should be an opt-in flag, off by default,
   since LudwigLang treats the body as continuous prose to tokenize.

2. METADATA MAPPING

     LudwigLang field   Source                          Notes
     ----------------   ------------------------------  --------------------------------
     title              collection name (user-editable)
     body               concatenated cleaned_text        original language only
     medium             user choice per collection        typed / handwritten / print
     author, date        tropy_manifest.json if linked;   do NOT use the cleaned JSON's
                         else left blank                  "timestamp" (processing time,
                                                           not document date)
     folder             collection name, optional

3. QUALITY GATE
   Only include pages where `guard.ok == true`. Report a count of
   skipped/low-confidence pages to the user before sending; do not silently
   drop them.

4. LANGUAGE GATE
   LudwigLang is German-only (hardcoded `language: "de"`, TTS is
   `lang=de`). Auto-detect or require user confirmation that the assembled
   text is German before allowing transport B or C. English collections
   (this pipeline's own `translated/` stage, or documents that turn out to
   be English) must not be sent — they would silently mislabel as German in
   LudwigLang's reading view.


TRANSPORT OPTIONS
-------------------

Three ways to hand off the assembled document; the adapter should support
all three behind one interface, since they trade off differently.

  A. EXPORT .md (offline-first, recommended MVP)
     Adapter writes one frontmatter .md file (same shape LudwigLang's own
     Import Text page produces). User drags it onto http://localhost:8765/import.
     No coupling between the two apps' processes. Ship this first.

  B. POST /api/import (one-click, needs LudwigLang running)
     A "Send to LudwigLang" button in this app's GUI/web posts directly to
     `http://localhost:8765/api/import` and can deep-link the browser to
     `/read/<id>` on success. Best UX, but fails ungracefully if LudwigLang's
     server isn't up — needs a clear error, not a silent hang.

  C. WRITE DIRECTLY into <ludwiglang_data_dir>/texts/ocr/<slug>/text.md
     For batch/offline export of many collections at once. Fully
     server-independent. Requires the adapter to know LudwigLang's
     `data_dir` (see ludwiglang/config.py::data_dir() for how LudwigLang
     itself resolves it — do not hardcode a path, read the same config
     resolution or take it as a CLI flag).

Phase 1 ships A only. B and C are follow-ups once A is validated with a
real collection.


IDEMPOTENCY
------------

Re-running the export on a collection that was already sent must not create
a duplicate text. Key on a stable id — collection name, or a hash of the
source file list — and either overwrite the matching destination or prompt
before overwriting. LudwigLang's own `store.slugify()` only de-collides
*names*; it has no concept of "this is the same collection re-exported," so
that logic has to live in the adapter, not be assumed on the other side.


NON-NEGOTIABLE RULES
---------------------

- Do not redesign either app's architecture. This is an adapter, not a merge.
- Never source the export text from `translated/` — original-language
  cleaned text only.
- Never send a collection to LudwigLang without the language gate passing
  (see above) — sending English text would silently corrupt the German
  trainer's assumptions (tokenization, TTS, word-status tracking all assume
  German).
- Never send pages where `guard.ok == false` without the user seeing that
  they were skipped.
- Do not hardcode LudwigLang's `data_dir` — resolve it the way LudwigLang
  itself does (config.py), or take it as an explicit argument.
- Do not modify LudwigLang's `/api/import` contract or `text.md` frontmatter
  shape to accommodate this pipeline. This pipeline adapts to LudwigLang's
  existing contract, not the reverse.
- Transport B must fail with a clear, actionable error if LudwigLang isn't
  reachable — never hang or fail silently.


Answers Ffrom THE PROJECT OWNER
--------------------------------------

Answer these before implementation starts:

1. Author/date: always pull from tropy_manifest.json when available
2. Language gate: auto-detect and block English language notes silently
3. Default transport: offline path (A) be
   primary with B as an optional convenience


PHASING
--------

  Phase   Scope
  ------  -----------------------------------------------------------------
  1 (MVP) Single collection, cleaned German text only, guard.ok pages only,
          transport A (export .md). Zero LudwigLang-side changes.
  2       Transport B: GUI button + deep-link to the LudwigLang reader.
  3       Carry page images through so LudwigLang's cursive-decode review
          cards can use real archival crops (its `region_images` field)
          instead of a rendered-font fallback, sourced from the Tropy
          manifest's asset paths.


FILES TO CREATE (Phase 1)
---------------------------

  File                                          Action
  --------------------------------------------  -------------------------------
  src/ocr_pipeline/export_ludwiglang.py (NEW)    Assembly + mapping + gates + transport A
  src/ocr_pipeline/cli.py                        Add `export-ludwiglang` command
  tests/test_export_ludwiglang.py (NEW)          Assembly order, guard filtering,
                                                  language gate, frontmatter output
  docs/LUDWIGLANG_EXPORT.md (NEW, later)         User-facing doc once Phase 1 ships,
                                                  same treatment as TROPY_INTEGRATION.md


END OF HANDOFF

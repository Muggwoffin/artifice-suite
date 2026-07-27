Handoff: Carry Facsimile Scans + Provenance into LudwigLang
==========================================================

Status: **PLAN ONLY — nothing in this document is implemented.** Design handoff,
same style as HANDOFF_LUDWIGLANG_EXPORT.md. Read both before writing code.

This is the detailed build-out of Phase 3 of HANDOFF_LUDWIGLANG_EXPORT.md
("carry page images through so LudwigLang's cursive-decode cards can use real
archival crops via its `region_images` field"). The text bridge it describes
(Phases 1–2) is DONE and shipping — `export_ludwiglang.py` + the `/api/ludwiglang/*`
routes + the export dialog. This handoff adds the images and provenance on top of
that working export, without touching it destructively.

Strategy context (the "why", cross-project): `E:\Claude Sandbox\LudwigLang\docs\OCR_BRIDGE_PLAN.md`.


WHAT THIS WOULD DO
-------------------

Today the OCR→LudwigLang export ships CLEAN TEXT ONLY. The archival scans — the
actual handwriting/print the learner should be reading — never cross the bridge.
LudwigLang, meanwhile, already has a COMPLETE cursive-learning pipeline (facsimile
strip in the reading view, a drag-to-crop tool, `cursive_evidence`, and
`cursive_decode` review cards). It is simply STARVED OF INPUT: it turns on the
moment a text's frontmatter contains a `region_images` list and the image files
exist under `<data_dir>/assets/`. Nothing currently produces either.

This job: extend the existing export so that exporting a collection also
(1) writes each kept page's scan into LudwigLang's assets dir, (2) emits the
`region_images` frontmatter LudwigLang already understands, and (3) carries
provenance (archive ref, Tropy item id, per-page OCR confidence). Result: an
imported archival document arrives READABLE SIDE-BY-SIDE WITH ITS SCAN and
immediately CROPPABLE into cursive flashcards, the day it lands.

NO NEW OCR CAPABILITY IS REQUIRED. This is plumbing over scans the pipeline
already has. (Automatic word-level crops are a SEPARATE, harder phase — see
"OUT OF SCOPE" — because the vision-LLM OCR returns text, not bounding boxes.)


THE DATA CONTRACT, AS VERIFIED
-------------------------------

**This side (source).** Same cleaned output the text export already reads. Each
kept page is an `ExportPage` (see `export_ludwiglang.py::_discover_pages`) whose
JSON record carries, verified against `stages/cleanup.py::perform`:

    {
      "source_file": "E:/.../Item Title/scan.pdf",  <- PRESENT. path to the scan/PDF
      "cleaned_text": "...",
      "guard": { "ok": true, ... },
      ...                                            <- NOTE: NO "page" field here.
    }

  - `source_file` is the ORIGINAL scan: an image (.jpg/.png/.tif) OR a multi-page
    PDF. Confirmed in `stages/ocr.py` (raw_ocr JSON) and preserved into the
    cleaned JSON by `stages/cleanup.py::perform` line ~116.
  - There is NO `page` field in the cleaned JSON. Page order/number comes from the
    stem's `_pNNNN` suffix — use the EXISTING `export_ludwiglang.py::_parse_page_num(stem)`.
    For a PDF, the 0-based page index to render = `_parse_page_num(stem) - 1`.
  - `tropy_manifest.json` at `<output>/tropy_manifest.json` is the source of real
    author/date AND of each page's Tropy `photos.orientation` (see below) and item
    title / archive box reference. Already read by `_read_manifest`.

**Other side (destination), VERIFIED against LudwigLang source:**

  - Reading view turns scans on via `routes_reading.py` line ~50:
        show_scans = bool(doc.meta.get("region_images")) and scans != "0"
    So MERELY HAVING `region_images` in frontmatter enables the facsimile strip
    AND the crop tool. No other flag needed.

  - Frontmatter shape consumed by `web/templates/reading.html` (lines ~39-53) and
    `web/static/reading.js` — `region_images` is a LIST OF OBJECTS:

        region_images:
          - file: /assets/<collection>/p0001.jpg    # served URL, REQUIRED
            page: 1                                   # int, REQUIRED (shown in caption/alt)
            bbox_approx: true                         # optional flag, caption note only

    reading.html iterates `meta['region_images']` and renders
    `<img class="read-facsimile-img" src="{{ r.file }}">`. reading.js reads that
    img's `src` back as the `region_file` for the crop POST.

  - Assets are served at `/assets`, mounted from `<data_dir>/assets` by
    `webapp.py`. So `file:` MUST be `/assets/<...>` AND the real file MUST live at
    `<data_dir>/assets/<...>` — the crop tool later resolves the URL back to disk
    (`cropping.py::_resolve_region`, which is path-guarded to the assets tree).
    If the URL and the on-disk file don't correspond, the facsimile shows but
    cropping 404s.

  - Crop flow that this unlocks (no work needed here — it already exists):
    drag box -> `POST /api/word/{slug}/crop {region_file, bbox[0..1], source_text_id}`
    -> `cropping.make_crop` writes `<data_dir>/assets/crops/<slug>-<n>.jpg`
    -> `store.add_cursive_evidence` -> `srs.register_cursive` -> a `cursive_decode`
    card appears in review.

  - A text "just appears" in LudwigLang with no API call or config edit if written
    to `<data_dir>/texts/imported/<collection>/text.md` with `source: imported`
    frontmatter (verified in the sibling handoff; `texts.py::discover` always scans
    `texts/imported`). Images go to `<data_dir>/assets/<collection>/`.


THE WORK
---------

One new function in the existing adapter, plus params threaded through the
existing route/dialog. Do NOT rewrite `export_md` — extend it.

1. NEW: `export_ludwiglang.py::export_region_images(pages, assets_root, collection_slug, *, manifest=None, max_edge=2000, jpeg_quality=85) -> list[dict]`
   - `pages`: the SAME `kept` list `assemble_collection` already builds (guard.ok
     only). Passing the kept pages GUARANTEES the facsimile strip is page-aligned
     with the assembled body — image N corresponds to text page N. Do not
     re-discover or re-filter; reuse the exact kept list.
   - For each page:
       stem_page = _parse_page_num(page.stem)
       src = Path(page.data["source_file"])
       orientation = <from manifest for this page, else 1>   # see gotcha
       if src is a PDF: render page index (stem_page - 1) to an image
           (REUSE stages/ocr.py::_pdf_single_page_image(src, idx, orientation))
       else: open src directly (apply orientation if != 1)
       downscale so max(width,height) <= max_edge; convert RGB; save JPEG q85 to
           assets_root / collection_slug / f"p{stem_page:04d}.jpg"
   - Return ordered list of dicts:
       { "file": f"/assets/{collection_slug}/p{stem_page:04d}.jpg",
         "page": stem_page,
         "ocr_confidence": <float|omit> }   # if a confidence stage ran; else omit
   - Skip a page (with a logged warning) if its source_file is missing/unreadable;
     never abort the whole export for one bad scan.

2. EXTEND `export_md(...)` with:
       include_scans: bool = False
       assets_root: Path | None = None          # <ll_data>/assets
       archive_ref: str = ""                     # provenance, e.g. "BArch R 58/6238"
   When `include_scans` and `assets_root`: call `export_region_images(kept, ...)`
   and inject `region_images` into the frontmatter dict. Add `archive_ref` (and
   `tropy_item_id` if resolvable from manifest) to `_build_frontmatter`.
   IMPORTANT: build region_images from the SAME `kept` pages used for the body.

3. FRONTMATTER: `_build_frontmatter` gains optional `region_images`, `archive_ref`,
   `tropy_item_id`. `_format_frontmatter` must emit a nested YAML list for
   `region_images` (it currently only handles flat str values — extend it, or
   switch to `yaml.safe_dump` for the frontmatter block; either is fine, but keep
   key order stable: title, medium, language, author, date, archive_ref, then
   region_images last).

4. DIRECT-WRITE TARGET: add an option to write straight into LudwigLang's data dir
   so the doc appears with no manual copy:
       texts:  <ll_data>/texts/imported/<collection_slug>/text.md
       assets: <ll_data>/assets/<collection_slug>/p{NNNN}.jpg
   Resolve `<ll_data>` the way LudwigLang does (env `LUDWIGLANG_DATA`, else
   `E:/LudwigLang-data`; see `ludwiglang/config.py::data_dir`) OR take it as an
   explicit arg/flag. DO NOT hardcode. (Matches the sibling handoff's transport C.)

5. ROUTE + MODEL: add to `web/models.py::LudwigLangExportRequest`:
       include_scans: bool = False
       ludwiglang_data_dir: str = ""     # empty => default resolution
       archive_ref: str = ""
   Thread them through `web/routers/ludwiglang.py::ludwiglang_export`.

6. UI: in `gui/views/ludwiglang_export.py` and the web export panel, add one
   checkbox "Include facsimile scans" (+ optional "Archive reference" text field
   and a data-dir field defaulting to the resolved LudwigLang data dir). The
   dialog already exists; this is a couple of controls.


GOTCHAS (verified / load-bearing)
----------------------------------

- ORIENTATION. `stages/ocr.py` applies a Tropy `photos.orientation` correction
  (1..8, EXIF convention) BEFORE OCR, sourced per-page. If you export the raw scan
  without the same correction, a page that was OCR'd upside-down-corrected will
  display sideways in LudwigLang and won't match its transcription. Pull the
  per-page orientation from `tropy_manifest.json` and apply it (reuse
  `_exif_orientation_matrix` / the render path in ocr.py). If orientation is
  unavailable, default to 1 and log it — do not silently assume 0-correction is
  right.

- PAGE ALIGNMENT. The body is built from `kept` (guard.ok) pages only. If you
  build region_images from a DIFFERENT set (e.g. all pages), image N will not be
  text page N and the facsimile caption will lie. Build both from the same list.

- URL/DISK CORRESPONDENCE. `region_images[].file` must be exactly the served path
  of the file you wrote under `<ll_data>/assets`. The crop tool resolves the URL
  back to disk and is path-guarded to the assets tree; a mismatch = 404 on crop.

- SIZE. LudwigLang-data is already ~1.2 GB with 3400 lexemes. Downscale to
  max_edge ~2000 px, JPEG q85. These are reading/cropping images, not archival
  masters — the master stays in Tropy/the source PDF.

- PATH SAFETY / SLUG. Sanitize the collection name to a slug for BOTH the assets
  subdir and the texts dir (mirror `ludwiglang/store.py::slugify` semantics), and
  assert every write stays within `<ll_data>`.

- IDEMPOTENCY. Re-exporting a collection must overwrite its
  `assets/<collection>/` images and its `text.md`, not accumulate duplicates.
  Clear/replace the collection's asset dir on re-export.


OUT OF SCOPE (do NOT attempt here)
-----------------------------------

- AUTOMATIC WORD-LEVEL CROPS. The current OCR is a VISION-LLM (LM Studio) that
  returns text with NO coordinates. There are no word bounding boxes anywhere in
  the pipeline, so nothing can be auto-cropped per word. That requires either a
  separate word-boxing engine (Kraken/docTR/Tesseract) aligned to the cleaned
  text, or an unproven LLM-grounding spike — a whole separate phase (OCR_BRIDGE_
  PLAN.md Phase 3). This handoff delivers the facsimile + MANUAL/model-assisted
  cropping, which already makes cursive decks practical.

- Changing LudwigLang's `region_images` / crop contract. This side adapts to
  LudwigLang's existing shape, never the reverse.


NON-NEGOTIABLE RULES
---------------------

- Do not touch the working text export destructively — add params, keep the
  text-only path (include_scans=False) behaving exactly as today.
- Build region_images from the SAME guard.ok `kept` pages as the body.
- Apply the per-page Tropy orientation so the facsimile matches the transcription.
- Downscale images; never copy full-resolution masters into LudwigLang-data.
- `region_images[].file` must correspond to a real file under `<ll_data>/assets`.
- Do not hardcode LudwigLang's data dir — resolve like `ludwiglang/config.py` or
  take it as an argument.
- Original-language cleaned text only (inherited rule — never `translated/`).
- guard.ok pages only, and the user must see the skipped count (inherited rule).


FILES TO CREATE / MODIFY
-------------------------

  File                                             Action
  -----------------------------------------------  ---------------------------------
  src/ocr_pipeline/export_ludwiglang.py            + export_region_images(); extend
                                                     export_md / _build_frontmatter /
                                                     _format_frontmatter; direct-write
  src/ocr_pipeline/web/models.py                   + include_scans, ludwiglang_data_dir,
                                                     archive_ref on LudwigLangExportRequest
  src/ocr_pipeline/web/routers/ludwiglang.py       thread new params into export
  src/ocr_pipeline/gui/views/ludwiglang_export.py  + "Include facsimile scans" checkbox
                                                     (+ archive ref / data-dir fields)
  web export panel (static)                        + same checkbox/fields
  tests/test_export_ludwiglang_facsimile.py (NEW)  see TEST PLAN
  (LudwigLang side)                                NO CODE CHANGE — it already renders
                                                     region_images. Optional: show
                                                     archive_ref in the reading header.


TEST PLAN
----------

Unit (pytest, `py -3.12` — the pipeline's interpreter, NOT 3.14 on PATH):
  - export_region_images: image source -> one downscaled JPEG at expected path;
    returned dict has matching /assets URL + page number.
  - PDF source: renders the correct page index (stem `_p0003` -> index 2).
  - Page alignment: given 3 pages where page 2 has guard.ok=false, region_images
    has exactly pages 1 and 3, and their `page` numbers match the assembled body.
  - Orientation: a page with manifest orientation 6 is rotated; assert output
    dimensions swapped vs. a same page at orientation 1 (or assert the render path
    was called with the right matrix).
  - Frontmatter: `_format_frontmatter` emits valid YAML that `yaml.safe_load`
    round-trips with region_images as a list of dicts.
  - Idempotency: exporting twice leaves one image per page, not duplicates.
  - include_scans=False path is byte-identical to today's text-only output.

Manual (mirror the LudwigLang verification pattern already used this session):
  - Copy a real cleaned collection; export with include_scans into a SCRATCH
    LudwigLang data dir (never the live E:/LudwigLang-data). Point a throwaway
    launch.json entry at it (LUDWIGLANG_DATA=<scratch>), open /read/<collection>,
    confirm the facsimile strip renders, then drag a box and confirm a
    cursive_decode card is created and appears in /review. Tear the scratch down.


PHASING
--------

  Phase   Scope
  ------  ------------------------------------------------------------------
  1       export_region_images + frontmatter + direct-write; text-only path
          untouched. Facsimile + provenance visible in LudwigLang; MANUAL
          cropping works. (This handoff.)
  2       Model-assisted crop: "Transcribe this" sends a dragged crop to the
          vision model to propose the word (OCR_BRIDGE_PLAN.md Phase 2).
  3       Automatic word boxes (separate engine; OUT OF SCOPE here).


OPEN QUESTIONS FOR THE OWNER
-----------------------------

1. Direct-write into LudwigLang-data by default, or stage into
   `<output>/ludwiglang/` and copy manually? (Recommend direct-write, guarded to
   a scratch dir until validated.)
2. Where does per-page orientation live for non-Tropy collections? If a collection
   never came from Tropy, is orientation always 1 (accept and log), or should the
   dialog offer a manual rotate?
3. Confidence: is the confidence stage run often enough to rely on
   `ocr_confidence` in frontmatter, or ship provenance (archive_ref) first and add
   confidence later?


END OF HANDOFF

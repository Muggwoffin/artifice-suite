# Diff-and-Crop Arbitration — plan and assessment

**Status:** Proposal. Not started. Opinion + design; no code yet.
**Date:** 2026-08-26
**Depends on:** the Tesseract engine (#86) and the pre-processing work (#84).

> Verify premises against the code before building. This references work that is
> in flight (the Tesseract engine) and one capability the engine does **not** yet
> have (word bounding boxes — see "What has to be built first").

## The idea, in one line

Run Tesseract (deterministic, with coordinates) **and** a vision-language model
(fluent, but prone to hallucinating plausible words) on the same page; use a
deterministic diff to find where they disagree; and re-read **only those spots**
with a tightly-cropped, context-free VLM query — so the model transcribes pixels,
not context. A deterministic **referee** that decides *where* to look; the VLM as
a constrained *witness*.

## Verdict

**Feasible: yes, with one genuinely hard part. Desirable: yes, specifically for
this corpus.** This is a strong fit for 1930s degraded German resistance
mimeographs, where the high-value tokens — dates, pseudonyms, place-names — are
exactly the ones a fluent VLM will confidently invent, and exactly the ones a
historian must be able to cite honestly. It aligns with the suite's ethos:
auditable provenance, never a confident guess dressed as a reading.

It is **not** a general accuracy win to switch on for every document — it roughly
doubles the OCR cost and adds N cropped re-queries per page. It is a
**precision instrument for high-stakes pages**, opt-in, and it earns its cost on
exactly the material you describe.

One framing correction worth keeping: the *system* is deterministic in where it
looks and what it flags; the arbitration re-read is still a (better-constrained)
VLM call. So it is a deterministic **referee over a non-deterministic witness**,
not a fully deterministic transcriber. Say that plainly in the UI and the docs —
overclaiming determinism would be the one way this undermines the trust it exists
to build.

## Where it is genuinely hard (be honest before building)

1. **Alignment is the make-or-break.** Aligning Tesseract's token stream to the
   VLM's free-form Markdown is the crux, and it is hard precisely on degraded
   pages. The VLM reflows lines, imposes structure (headings, tables), may
   reorder multi-column text, and drops or invents whole spans. Word-index
   alignment breaks on all of these. `rapidfuzz`'s `editops`/`opcodes` over a
   normalised token sequence is a sound *start*, but it must be anchored (align
   on high-confidence matching runs first, then diff within the gaps) and must
   degrade gracefully when the two streams diverge structurally rather than
   producing garbage substitutions.

2. **Bounding boxes exist only for Tesseract tokens.** You can crop a divergence
   only where Tesseract detected *something* at known coordinates. Two
   consequences:
   - A VLM **pure hallucination with no Tesseract anchor** (the model invented a
     word in a spot Tesseract read as nothing) has no box to crop — it cannot be
     arbitrated this way, only flagged. Partial coverage by design.
   - On heavily degraded mimeographs Tesseract's own segmentation and coordinates
     are shaky, so a crop can land off-target. **This is why the pre-processing
     work matters here**: deskew + binarisation (Phase 2 of the pre-processing
     plan) materially improves Tesseract's box accuracy, which is the input this
     whole pipeline stands on. Build that first, or the crops wander.

3. **Reconciliation must not corrupt Markdown.** Splicing arbitrated text back by
   character span is fiddly around table pipes, emphasis, and headings. The right
   discipline: track `(start, end)` spans of *words* in the raw Markdown, and
   splice only within a word span, never across a syntax token. Re-validate the
   Markdown parses after each splice.

4. **Cost and latency.** Two full OCR passes plus N crop re-queries per page. The
   RTX 5070 Ti and `ThreadPoolExecutor` batching to Ollama make it viable as an
   **offline/batch** step, not interactive. Bound the concurrency to avoid
   thrashing VRAM.

## What has to be built first

- **Tesseract word data with coordinates.** The current `_tesseract.py` (#86)
  returns text via `tesseract … stdout`. Arbitration needs the per-word dict the
  prompt assumes (`text, x, y, w, h, conf`). Add a `get_tesseract_data(image)`
  that runs `tesseract … tsv` (or uses `pytesseract.image_to_data`) and parses
  the TSV. This is a small, self-contained addition to the existing engine.
- **A crop-query entry point.** The plan's `query_vlm_crop(image, prompt)` maps
  cleanly onto the existing vision path — `_encode_image` already turns an image
  into the base64 the backend wants; a thin wrapper that takes crop bytes + a
  fixed prompt and calls `_ocr_vision`'s client is most of it.
- **Pre-processing Phase 2** (deskew/binarise) for reliable Tesseract boxes.

## Proposed architecture (matches your five stages)

1. **Baselines.** `get_tesseract_data(image)` → word dicts with coords + conf;
   `get_vlm_markdown(image)` → full-page Markdown (olmOCR via Ollama, or the
   existing vision engine).
2. **Align & diff.** Tokenise the Markdown while recording each word's raw
   `(start, end)` char span. Normalise (strip Markdown, casefold, fold
   punctuation) into a comparison sequence. Anchor on matching runs, then use
   `rapidfuzz` editops within gaps. Flag substitutions and above-threshold
   divergences; **weight by Tesseract confidence** (high Tesseract conf + high
   divergence = strong hallucination signal; low Tesseract conf = distrust the
   referee too).
3. **Crop.** For each flagged, Tesseract-anchored divergence, crop the box from
   the *pre-processed* image with configurable padding (default 15px), clamped to
   image bounds. In-memory (`io.BytesIO`), never to disk.
4. **Arbitrate.** Concurrent (`ThreadPoolExecutor`, bounded) context-free crop
   queries with the strict "transcribe only what is visible; output [ILLEGIBLE]
   if you cannot" prompt.
5. **Reconcile.** Splice arbitrated text back into the raw Markdown by span,
   preserving surrounding syntax; re-validate the Markdown.

## Refinements worth adopting

- **Three outcomes, not two.** agree → trust; disagree-and-arbitrated → record;
  disagree-and-illegible or no-anchor → **surface to the historian** in the UI
  rather than silently choosing. This is the harness move: the tool adjudicates
  what it can and *shows its working* on what it cannot.
- **Provenance per arbitrated token.** Extend the page metadata (the `engine`
  field already records this kind of thing) with a list of arbitrated spans —
  original VLM word, Tesseract read, arbitrated result, confidence — so a methods
  section can cite exactly what was decided and how.
- **Confidence-gated scope.** Only arbitrate the token classes that matter
  (dates, capitalised proper nouns, digits) by default, to control cost; make the
  net widenable.
- **olmOCR caveat.** Confirm olmOCR actually runs under your Ollama setup and
  returns usable Markdown before committing to it; it is a specific model with
  its own prompt/format expectations. The pipeline should stay model-agnostic
  (any vision engine for the full-page pass and the crop pass), consistent with
  the suite's BYOM stance and its lean toward openly-provenanced models.

## Dependencies

- **`rapidfuzz`** — new dependency (small, C-backed, permissive licence). Fine.
- **Pillow** — already added (#84). Crop + in-memory buffer need nothing more.
- **No new binary** — reuses the Tesseract binary #86 already detects.

## Testing

- Alignment: deterministic unit tests on synthetic Tesseract-stream / Markdown
  pairs covering substitution, insertion, deletion, reflowed lines, and a table —
  the alignment is pure and must be tested hard, independently of any model.
- Crop math: bbox + padding clamping at every image edge; in-memory bytes are a
  valid image.
- Reconciliation: span-splice never breaks Markdown structure (round-trip parse).
- Arbitration and the VLM crop query: mocked — no live model in CI.
- Cost guard: assert concurrency is bounded.

## Phasing

- **Phase A** — `get_tesseract_data` (TSV + coords) and `query_vlm_crop`; the two
  primitives, fully tested. Small, and independently useful.
- **Phase B** — alignment + diff + flagging (the hard, pure, testable core).
- **Phase C** — crop + concurrent arbitration + reconciliation.
- **Phase D** — UI: opt-in toggle, the "surfaced for human review" list, and
  per-token provenance. Gate the whole feature behind pre-processing Phase 2 for
  reliable boxes.

## Open questions for the maintainer

1. Default token scope — arbitrate everything, or only high-entropy classes
   (dates/proper nouns/digits) to start?
2. When the arbiter returns `[ILLEGIBLE]` or there is no Tesseract anchor: keep
   the VLM's original word (flagged), blank it, or force human review?
3. Is olmOCR confirmed working under your Ollama, or should the full-page pass
   stay on the existing vision engine for now?

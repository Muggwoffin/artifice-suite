# Bringing ArtificeTranscribe in line with ArtificeOCR

**Date:** 2026-09-09
**Status:** Provisional audit. **Nothing here has been implemented.** No code was
changed to produce this document.
**Scope:** structural and process comparison of `apps/artifice-transcribe`
against `apps/artifice-ocr` as it stands at `ba9a861`, plus the transferable
lessons from the olmOCR-2 optimisation work (PR #101) and this session's CI/release
work (#102–#104).

## Why now

Per the 2026-09-09 pause decision, OCR and Transcribe are the two apps under active
development, and Transcribe is next once OCR stabilises. OCR has just been through a
full optimisation, review and release-hardening cycle; the cheapest way to start
Transcribe is to inherit what that cycle produced rather than rediscover it.

**A caution that applies to this whole document.** OCR's shape is the product of
its own failures — 275-page PDFs, a scan fed to the model upside-down, a context
window overflowing on a 4653×3445 image. Transcribe's failure modes are *not* the
same (long audio, speaker confusion, an ASR model that mishears rather than
hallucinates a loop). **Copy the patterns whose underlying problem Transcribe
actually has.** Several items below are explicitly marked as *not* worth copying,
and that list matters as much as the rest.

---

## 1. Verified structural differences

Every claim in this table was checked against the tree at `ba9a861`.

| Dimension | `artifice-ocr` | `artifice-transcribe` | Gap real? |
|---|---|---|---|
| Python modules under `src/` | 53 | 21 | Size difference is mostly legitimate scope, not neglect |
| `config.py` | 395 lines, `_DEFAULTS` dict + `PERSISTED_KEYS` + YAML/env layering | 100 lines, pydantic `BaseSettings` | **Different by design, not by drift** — see §3 |
| Shared private helpers | `_logging`, `_retry`, `_guard`, `_resolution`, `_backend`, `_normalise` | none of these exist | **Yes — the significant gap** |
| Freeze spec (`.spec`) | `artifice-ocr.spec` | **absent** | **Yes — but see §6, it is more tractable than it looks** |
| `build-exe.yml` coverage | yes | **not mentioned at all** | **Yes** |
| Optional-heavy-dependency split | none needed | `[asr]` extra + `AsrUnavailable` + `/capabilities` | **Transcribe is AHEAD of OCR here** |
| Live-interop tests | 3 files (`test_live_model_interop`, `test_live_ui_model_interop`, `test_tropy_live`) | **none** | **Yes** |
| Release gate coverage | `run-live-release-gate.sh` runs OCR only | **not covered** | **Yes** |
| UI stress harness | `tests/stress/` (seeded Playwright) | **absent** | Partly — see §6 |
| `model_harness` adoption | `_backend.py`, `_resolution.py`, `stages/title.py`, 3 web modules | `api/v1/routes.py`, `services/download.py`, `services/inference.py`, `web/routers/byom.py` | **Comparable — Transcribe is not behind here** |
| Web assets in-package | `web/static/` + no templates | `web/templates/` + `web/static/` | Conforms |
| Console entry points | `artifice-ocr`, `artifice-ocr-web` | `artifice-transcribe` only | Minor |

**The single clearest finding:** Transcribe has **no freeze spec and no
`build-exe.yml` entry**, so it cannot currently be shipped as a standalone
executable the way OCR, Draft, Graph and the Hub can. Given the Hub's stated job is
"installs, updates and launches the other four", this is a real functional hole, not
a stylistic one. **§6 sets out why this is far more tractable than the multi-gigabyte
CUDA bundle it first appears to require.**

**A correction to an earlier draft of this document.** The first version treated
"is a frozen Transcribe wanted?" as an open question on the grounds that
`[asr-cuda]` pulls a multi-gigabyte PyTorch stack. That framing was wrong: it
conflated two separate downloads (see §6), and it overlooked that the thin-core
split needed to avoid the problem **already exists and is deliberate**.

---

## 2. Lessons from PR #101 worth transferring

### 2a. Never let a fallback mask the real error — **transfer this**

OCR's `_ocr_single_image` originally caught a vision failure and fell through to
Tesseract, and a bug in the fallback then replaced the actionable original error
with `'NoneType' object has no attribute 'strip'`. The fix was explicit: if the
fallback produces nothing usable, **re-raise the original failure**.

Transcribe's `transcription.py` has the same shape at `_ensure_models` (lines 63–92)
and `_get_align_model` (97–142): `except Exception as exc: … raise`. Those currently
look correct — they log and re-raise. **Verify before changing anything**, but the
principle to hold is that a diarization failure must never be reported as an
alignment failure, and an out-of-memory model load must not surface as "model not
found".

### 2b. A degenerate-output guard, adapted — **transfer the idea, not the code**

`_guard.check_no_repetition_loop` catches a vision model looping on hallucinated
filler. **Whisper has a genuinely analogous failure**: it is well documented to loop
on the same phrase, and to hallucinate confident text over silence or music. The
detector's *shape* transfers (low unique-line ratio over a minimum length); the
thresholds do not — they were tuned on 9 real archive pages and mean nothing for a
transcript.

**Do not copy `_guard.py` wholesale.** Write a transcript-appropriate check, and
tune it against real audio before trusting it.

### 2c. Blank/silence short-circuit — **transfer, high value**

`_blank.py` skips the model entirely for a near-blank page, because a model never
trained on blank input hallucinates. **The audio equivalent is stronger, not
weaker**: near-silent segments are a documented Whisper hallucination trigger, and
oral-history recordings routinely contain long silences, room tone and tape hiss.
A cheap RMS/VAD threshold before the ASR call is the direct analogue of the
greyscale-variance check, and likely a bigger win here than it was for OCR.

### 2d. Domain instruction prompt — **partially transferable**

`ocr_prompt_instruction` was the largest measured accuracy win in the olmOCR-2
findings ([CENT] Table 4: field EMR 30.55% → 74.64%). Whisper has a direct
equivalent in its `initial_prompt` / `prompt` parameter, which measurably improves
proper-noun and domain-vocabulary accuracy — exactly the pain point for oral history
(place names, personal names, organisational acronyms).

**This is the highest-value single item in this document.** Same shape as OCR's:
a persisted Settings field, recorded in the run's sidecar for methods-section
citation.

### 2e. Measurement harness before optimisation — **transfer the discipline**

The olmOCR-2 findings doc called the absence of an accuracy harness "the blocker
under all of this", and `scripts/measure_ocr_accuracy.py` was built before any
tuning claim could be trusted. Transcribe has the same absence and needs the
equivalent: **WER/CER against a small fixed corpus** of real recordings with
verified transcripts, plus diarization error rate if speaker labels are to be
tuned. As with OCR, the corpus itself is the maintainer's to supply — it cannot be
generated.

**Do this before any Transcribe optimisation work**, not after, or every claim will
be a citation rather than a measurement.

### 2f. Load-bearing comments on non-obvious ordering — **transfer, nearly free**

`_ocr_vision` now carries an explicit comment that text-before-image order is
load-bearing, because a refactor could silently reverse it. Transcribe's pipeline
has the same class of hazard: `transcribe → align → diarize` is order-dependent, and
alignment before transcription is meaningless. One comment, near-zero cost.

---

## 3. What NOT to copy

Recording these explicitly, because "align with OCR" read literally would make
Transcribe worse.

- **Do not replace pydantic `BaseSettings` with OCR's `_DEFAULTS`/`PERSISTED_KEYS`
  dict.** Transcribe's config is *better* on this axis — typed, validated,
  env-aware, 100 lines against 395. If anything, OCR should eventually move toward
  Transcribe's approach, not the reverse. The genuine gap is that Transcribe has no
  settings-persistence story equivalent to `save_user_settings`, not that pydantic
  is wrong.
- **Do not copy `_guard.py`'s thresholds.** (See §2b.)
- **Do not copy `ocr_max_image_edge` / `ocr_temperature_ladder_*` reasoning.** They
  encode Qwen2.5-VL tiling behaviour and VLM decoding-loop escape. Whisper's decoding
  parameters (`beam_size`, `temperature` fallback, `compression_ratio_threshold`,
  `no_speech_threshold`) already implement their own escalation ladder internally —
  reimplementing OCR's on top would fight the library.
- **Do not add a `stages/` tree for its own sake.** OCR has six genuinely optional,
  independently resumable stages. Transcribe's pipeline is one largely non-optional
  sequence. `services/` is the honest shape for that.

---

## 4. Process lessons from this session (#101–#104)

These are about *how* the work ran, and they cost real time to learn.

1. **A dispatched agent's self-report is not evidence.** Two runs this session
   reported work complete that had not been committed, and one narrated an
   "authorization received" that never occurred. Every commit was independently
   re-verified (full diff + from-scratch test run) before being trusted. Keep doing
   that.
2. **`ocr-ui-stress` is flaky in CI, and now proven so.** The same seed failed on a
   docs-only PR (#103) that touched no OCR code whatsoever, and passed on re-run.
   One genuine race *was* found and fixed (`settings.js`'s uncancelled status-revert
   timer, `14f3417`), but a second timing failure mode remains. **Do not let a red
   `ocr-ui-stress` block a merge without first checking whether the PR could
   plausibly have caused it.** If Transcribe gains a stress harness, expect the same
   and budget for it.
3. **Lint gates fire on whole files, not just changed lines.** Both the ruff-format
   and dependency-audit gates flagged *pre-existing* issues the moment a PR touched
   the file. Run `uv run ruff format --check` and
   `uv run python scripts/check-dependency-audit.py` locally before pushing.
4. **A script imported via `sys.path.insert` reads as a "ghost import"** to the
   dependency-audit gate and needs an explicit `PYTEST_INTERNAL` allowlist entry
   (see `5bd4b2f`). Relevant if Transcribe gains a `scripts/measure_*.py` harness —
   it will hit this identically.
5. **The release gate needs a published `live-interop/release-gate` status** on the
   exact tagged commit, and that status does not carry across commits. It also
   currently covers **OCR only** — if Transcribe is meant to be release-gated too,
   `run-live-release-gate.sh` needs extending, which is a deliberate decision, not
   an oversight to fix silently.

---

## 5. Freezing strategy: a small executable that guides users to models

### The false dilemma

"Freeze Transcribe" reads as "ship a multi-gigabyte CUDA PyTorch bundle" — unsignable,
painful to download, and needing a rebuild every time torch moves. **That option should
be rejected, and it is not the only one**, because the architecture that avoids it is
already built.

### What already exists (verified at `ba9a861`)

`apps/artifice-transcribe/pyproject.toml` already splits core from ASR, with an
explanatory comment saying so in as many words:

- **Core dependencies**: `fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]`,
  `aiosqlite`, `pydantic`, `python-multipart`, `platformdirs`, `fpdf2`, `openai`,
  `jinja2`, `numpy`, and the four workspace packages. **No torch, no whisperx, no
  pyannote.**
- **`[asr]` / `[asr-cuda]` extras**: the entire heavy stack.

The runtime guarding is real, not aspirational:

- `AsrUnavailable` (`api/v1/routes.py:259`) is raised at 9 call sites and carries an
  install hint.
- `GET /api/v1/capabilities` reports `asr.available`, `asr.reason`, `asr.install_hint`.
- `tests/test_capabilities.py` covers available, unavailable, and **partial-install**
  (a half-installed stack must report unavailable, not crash).

Also already present, and directly relevant to "guides them to models":

- **Model-weight download with a consent step** — `POST /models/{key}/consent`,
  `/models/{key}/download`, `/models/{key}/download/cancel`.
- **Full transcript editing** — `PATCH /jobs/{id}/segments`, plus segment
  `split`, `merge`, per-segment `tags`, `PATCH /jobs/{id}/speakers`, and
  `PUT /dictionary`.

So the app already starts, serves its UI, accepts uploads, runs its database, and
performs cleanup/summarise **with no ASR stack installed at all**.

### The distinction that matters: two different downloads

An earlier draft blurred these. They have different owners:

| | What it is | Who handles it | Status |
|---|---|---|---|
| **Model weights** | Whisper / pyannote checkpoints | The app itself | **Already built** (consent + download + cancel) |
| **Python packages** | torch, whisperx, pyannote.audio | **The Hub** — a frozen app cannot pip-install into itself | Hub has `uv_backend.py` and a native CUDA hardware probe; wiring to Transcribe **not yet done** |

A frozen executable cannot install Python packages into its own bundled interpreter.
That is why the ASR stack must be the Hub's responsibility, and the Hub already has
the machinery.

### The one genuine gap for hand transcription

`POST /transcribe` (`routes.py:835`) **unconditionally** queues `_run_transcription`
as a background task. There is no way to create a job that skips ASR and hands back an
empty transcript to type into.

Everything downstream of that already works on segments regardless of how they were
produced — editing, split/merge, speaker labelling, dictionary, and the OHMS/TEI
exports. **The missing piece is job creation, not the editor.**

### Proposed shape

1. **Freeze core-only.** Add `artifice-transcribe.spec` excluding the ASR stack, plus
   a `build-exe.yml` entry. Follow `artifice-ocr.spec`'s structure.
2. **Add a manual-transcription mode.** A `mode=manual` parameter (or a sibling route)
   that creates the job and stores the uploaded audio but queues no ASR task, seeding
   one empty segment. Small change, reuses every existing editing route.
3. **Let the Hub own ASR installation.** Surface `capabilities`' `install_hint` as a
   Hub action rather than asking the user to run `uv sync --extra asr` by hand.
4. **First-launch UX.** `capabilities` already reports ASR unavailable; the UI offers
   three honest paths: transcribe by hand now, install the ASR stack via the Hub, or
   point at a remote transcription endpoint.

The result is a genuinely useful small executable: an audio player with a
synchronised, speaker-aware transcript editor and OHMS/TEI-compliant export, where
ASR is an **upgrade rather than a precondition**. For a historian transcribing a
single interview carefully by hand, that is arguably the better default.

### Measured — core-only freeze, 2026-09-10

Built via `apps/artifice-transcribe/artifice-transcribe.spec` (Item 2, this phase)
and measured directly: the `dist/artifice-transcribe/` onedir bundle is **~203 MB**
on Linux — smaller than OCR's ~249 MB, consistent with core Transcribe carrying no
PyMuPDF while OCR does. The built binary was started with `--no-window` and smoke-
tested over HTTP (`/`, `/api/v1/capabilities`, `/static/css/app.css`,
`/shared/tokens.css` all 200; the shared app-shell renders) — the ASR stack is
confirmed absent from the bundle (no torch/whisperx import errors are possible; the
spec `excludes`s them explicitly regardless of what is installed on the build
machine).

One packaging bug surfaced only by actually running the built binary, not by
writing or reading the spec: SQLAlchemy's async sqlite dialect
(`sqlalchemy.dialects.sqlite.aiosqlite`) loads the `aiosqlite` DBAPI module
dynamically by string name at `create_async_engine()` time, which PyInstaller's
static bytecode scan cannot see. Without an explicit `hiddenimports` entry for
`aiosqlite` and `sqlalchemy.dialects.sqlite.aiosqlite`, the frozen binary built and
looked correct, then crashed on first launch with
`ModuleNotFoundError: No module named 'aiosqlite'` — the exact "tests cannot see
packaging bugs" failure mode this file warns about elsewhere. Fixed in the spec;
recorded here as the reason that hidden-import pair exists.

---

## 6. Suggested sequencing

Ordered by (value × confidence) ÷ effort, mirroring how the olmOCR-2 plan was
sequenced. **Every item needs the maintainer's agreement before work starts** —
this is a proposal, not a plan.

| # | Item | Why first / notes | Decision needed? |
|---|---|---|---|
| 0 | **WER/CER measurement harness + a real corpus** | Nothing accuracy-shaped below can be honestly evaluated without it. Corpus is maintainer-supplied. | Yes — corpus |
| 1 | **Manual-transcription job mode** (§5) | The one genuine gap blocking a useful ASR-free executable; small, reuses every existing editing route | No |
| 2 | **Core-only freeze spec + `build-exe.yml` entry** (§5) | Closes a real shipping hole; the Hub claims to launch it. Measure the bundle size while doing it. | No |
| 3 | **Silence/near-silence short-circuit before ASR** | Direct `_blank.py` analogue; documented Whisper hallucination trigger; cheap | No |
| 4 | **`initial_prompt` domain vocabulary field** | Highest measured-analogue accuracy win; needs a Settings surface | Yes — UI |
| 5 | **Shared `_logging` / `_retry` helpers** | OCR's rotating-file logging (`d6d10af`) exists because a frozen build was undiagnosable. Transcribe hits this the moment item 2 ships. | No |
| 6 | **Hub-driven ASR stack install** (§5) | Turns `capabilities.install_hint` into a button; Hub already has `uv_backend.py` + CUDA probe | Yes — Hub scope |
| 7 | **Transcript degeneracy guard** | Real Whisper failure mode, but needs item 0 to tune thresholds honestly | No |
| 8 | **Live-interop test + release-gate coverage** | Makes Transcribe releasable to the same standard as OCR | Yes — scope |

Items 1, 2, 3 and 5 are self-contained and need no design decision. **Items 1 and 2
together are the shortest path to a shippable, genuinely useful executable** and do
not depend on item 0. Item 0 gates the credibility of anything accuracy-shaped
(items 3, 4, 7).

---

## 7. Parakeet (NeMo) backend dependency footprint — measured 2026-09-10

Item A of the Parakeet-backend phase adds a second ASR engine (`ParakeetEngine`,
CUDA-only, English-only) behind the `ASRBackend` protocol.  Because this repo has
twice shipped a spec/dependency claim that turned out wrong on the first real
build (the aiosqlite hidden-import bug, the lazy-torch-import regression), the
extra's footprint is recorded here from `uv sync --extra asr-parakeet --dry-run`
rather than asserted.

**Pinned version.** `nemo_toolkit[asr]>=2.7.3`, which resolves to **3.0.0**
(2026-08-07) as of this date.  Chosen because:

- `numpy>=1.22` with no upper bound — the historical `numpy<2` pin is lifted in
  the current 2.7.x/3.0.0 releases, so the extra resolves against the
  workspace's numpy 2.4.6/2.5.1 **unchanged**.  (NeMo still carries a numpy-2.x
  workaround in `numexpr<2.14.0` — "WAR for attempted use of nonexistent
  numpy.typing" — so numpy 2.x is metadata-compatible; runtime behaviour is not
  exercised here, no GPU in CI.)
- `EncDecRNNTBPEModel` + the TDT decoding submodules are still present in 3.0.0,
  so `ASRModel.from_pretrained("nvidia/parakeet-tdt-1.1b")` (the load path the
  model card documents) has its `target` class.  There is **no**
  `EncDecTDTModel` class — the model is an RNNT-BPE model with a TDT decoder, so
  nothing TDT-specific was removed.

**Notable side effect — two downgrades the lock had to accept.**  NeMo pins
`lightning<=2.4.0` and `omegaconf<=2.3`, while pyannote.audio 4.0.7 requires
`lightning>=2.4`.  The intersection is exactly `lightning==2.4.0` (and
`omegaconf==2.3.0`, pulled down from 2.3.1), so adding NeMo downgrades the
*WhisperX* path too.  This is accepted and validated-by-resolution (pyannote's
`>=2.4` is still satisfied at exactly 2.4.0), but it is the kind of cascade a
future maintainer should know about before "bumping" either extra.

**Resolved dependency list (new packages introduced by the extra; wheel-only
sizes).**  Total **~3.76 GB** of new wheels, dominated by:

| Package | Wheel size |
|---|---|
| pyarrow (via datasets) | 1.51 GB |
| llvmlite (via numba) | 1.04 GB |
| onnx | 329 MB |
| cytoolz | 285 MB |
| wandb | 195 MB |
| cuda-bindings | 126 MB |
| numba | 68 MB |
| sentencepiece | 61 MB |
| text2num | 33 MB |
| msgpack / ml-dtypes | ~20 MB each |
| nemo-toolkit 3.0.0 | 5 MB |

…plus ~45 smaller packages (aistore, lhotse, librosa, soundfile, sacrebleu,
whisper-normalizer, hydra-core 1.3.2, datasets 5.0.1, tensorboard, webdataset,
the `nv_one_logger_*` trio, and their transitive deps).  `torch` itself is
shared with the existing `asr`/`asr-cuda` extras (2.8.0); installing
`asr-parakeet` alone additionally pulls the plain-PyPI CPU torch, which the
CUDA check rejects at load time.

**System prerequisites (not pip-installable):** `libsndfile1` (NeMo decodes
audio via soundfile/librosa) and `ffmpeg` (already required by WhisperX).  Both
are documented in the `asr-parakeet` extra's comment in
`apps/artifice-transcribe/pyproject.toml`.

---

## Open questions for the maintainer

1. **Should Transcribe be release-gated like OCR?** Extending
   `run-live-release-gate.sh` means every release needs a working Whisper/pyannote
   stack plus real audio available locally — a heavier precondition than OCR's, and
   a real recurring cost.
2. ~~**Is a frozen Transcribe executable actually wanted?**~~ **Resolved during this
   audit — see §5.** The question rested on a false premise. A *core-only* freeze
   avoids the CUDA stack entirely, and the thin-core split that makes it possible is
   already built and tested. The live question is narrower: **should the manual
   transcription mode (§5, item 1) ship as a first-class feature, or only as the
   fallback shown when ASR is unavailable?** Shipping it first-class is the stronger
   claim — hand transcription is a legitimate scholarly method, not a degraded mode.
3. **Does the pyannote HF-token requirement belong in the same BYOM surface as model
   selection?** It is a credential, not a model choice, and currently lives in its
   own path (`_HF_TOKEN_FILE`).

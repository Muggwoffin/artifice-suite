# olmOCR-2 Optimisation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the inference-side fixes identified in `OLMOCR2_OPTIMISATION_FINDINGS.md` for `apps/artifice-ocr`'s vision-OCR call path, and build the accuracy-measurement harness needed to validate them, without regressing the resize fix already shipped on this branch.

**Architecture:** Each fix is a small, independently-testable change to `apps/artifice-ocr/src/artifice_ocr/stages/ocr.py` and its immediate collaborators (`_guard.py`, `_tesseract.py`, `_normalise.py`, `config.py`). No new heavyweight dependency, no retraining, no change to the harness architecture's `model_harness` contract (this app's vision call is a single structured request/response, already compliant). A new `apps/artifice-ocr/scripts/measure_ocr_accuracy.py` closes the "no accuracy harness" gap the findings doc calls the real blocker.

**Tech Stack:** Python 3.12, pytest, Pillow, PyMuPDF (`fitz`), pytesseract-free Tesseract subprocess wrapper (`_tesseract.py`), `uv` workspace.

## Global Constraints

- Follow `apps/artifice-ocr`'s existing module layout (`stages/`, top-level `_private.py` helpers) — do not introduce a new package layout.
- Every new/changed config key gets: a `_DEFAULTS` entry with a rationale comment (`config.py`), and, unless a task says otherwise, an entry in `PERSISTED_KEYS` (`config.py`) and `_CONFIG_KEYS` (`web/routers/settings.py`) — this is the established pattern for every existing OCR setting.
- Never resize on the Tesseract path (`_tesseract_from_image` must keep calling `_encode_image` with no `max_edge`) — already correct, do not touch it except where a task explicitly says to.
- A guard rejection (`_guard.check_no_repetition_loop`) has no source text to fall back to — treat `not result.ok` as a hard failure per page, never a silent revert to bad text.
- All file paths below are relative to the repo root `apps/artifice-suite` unless stated otherwise.
- SPDX header (`# SPDX-FileCopyrightText: 2026 Maurice Casey` / `# SPDX-License-Identifier: AGPL-3.0-or-later`) on every new Python file, matching every existing file in this package.
- Run the OCR app's test suite from `apps/artifice-ocr/`: `uv run pytest tests/ -x -q` (exclude `tests/stress/` and `tests/test_live_*` unless a task says to run them — those need a live model backend).

## Verified premises (read before starting)

Checked against `HEAD` on `test/ocr-ui-security-hardening`, not the `3e03668` baseline the findings doc cites — the branch has moved three commits since that doc was written.

- **§2 "No image resize" is STALE. This is already shipped** — commit `843a50c fix(ocr): cap vision images and stop the fallback masking the real error`. `_configured_max_image_edge()`, `_resize_to_max_edge()`, and the wired-through `max_edge` parameter all exist at `apps/artifice-ocr/src/artifice_ocr/stages/ocr.py:74-193`, default `1288`, correctly excluded from the Tesseract path (`ocr.py:249`), covered by `tests/test_ocr_image_budget.py`. **Do not create a task for this.** Table item "1. Resize to 1288px longest edge" is done.
- §0 (prompt order), §1 (temperature/ladder), §3 (prompt format / front matter), §4 (rotation), §5 (blank pages), §6a (configurable prompt) are all still accurate as described in the findings doc — verified directly against current `ocr.py`, `_guard.py`, `_retry.py`, `config.py`, `_tesseract.py`, `stages/preprocess.py`.
- `_guard.check_no_repetition_loop` (`_guard.py:199-246`) is unchanged: document-level only, called once in `perform()` on the full joined text, not per page.
- `_retry.py`'s `_DEFAULT_RETRYABLE` (`_retry.py:15`) is still `(ConnectionError, TimeoutError)` only — a repetition-loop is not a raised exception today, so `@retry` never sees it.
- Every backend's `chat()` (`_backend.py:282,379,454,498,563`) accepts `temperature: float` and threads it to the model, including the native Ollama path — a temperature ladder needs no backend change.
- `stages/preprocess.py` does **not** currently expose a reusable mean/variance stat — the findings doc's "which `stages/preprocess.py` already computes when enabled" is imprecise: the array exists transiently inside `_normalise_illumination` but is never returned, and preprocessing is off by default anyway. Task 4 below computes blank-detection independently, not by reusing preprocessing internals.

## Dispatch protocol: oh-my-opencode-slim, "go" preset

**Verified live**, not assumed, on 2026-09-09:

- The bespoke project fleet (`lead-engineer`, `tester`, etc. — `.opencode/agents/*.md`) is a **separate system** from `oh-my-opencode-slim`. Per the maintainer's instruction for this plan, **only the slim-preset roles are used below**; do not dispatch the bespoke fleet or reference `scripts/dispatch-opencode.sh <bespoke-agent>` for this work.
- `opencode agent list` (run from the repo root) shows the live roster: **`orchestrator` is the only `primary`-mode agent** the slim plugin registers. `oracle`, `librarian`, `explorer`, `designer`, `fixer`, `councillor` are all `subagent`-mode.
- **`scripts/dispatch-opencode.sh` needs no modification** — it is agent-name-agnostic (`opencode run --agent "$AGENT" "$(cat "$BRIEF")"` with no hardcoded whitelist), confirmed by reading it in full.
- **Confirmed by live smoke test:** `bash scripts/dispatch-opencode.sh explorer <brief> --foreground` does **not** run as `explorer`. It prints `agent "explorer" is a subagent, not a primary agent. Falling back to default agent`, then runs as `orchestrator · glm-5.2`, which correctly self-delegated to `@explorer` internally and returned its result.
- **Consequence: every dispatch in this plan targets `orchestrator`, never a subagent role name directly.** The brief tells `orchestrator` which of its own subagents to use (by `@name` mention) for which part of the task.
- Model mapping, preset `go` (`~/.config/opencode/oh-my-opencode-slim.json`): `orchestrator`=`glm-5.2` (max), `oracle`=`kimi-k3` (thinking, skill: simplify), `explorer`=`minimax-m2.7` (high), `librarian`=`deepseek-v4-flash` (high, mcp: context7+gh_grep), `designer`=`kimi-k2.7-code`, `fixer`=`deepseek-v4-pro` (high). `councillor` is live in `opencode agent list` but not in this preset's cached JSON — treat `opencode agent list` as ground truth over the JSON if they disagree at dispatch time.
- **Persona-bleed risk is real and specific to this plugin.** CLAUDE.md documents `lead-engineer` once reading the project's Claude-orchestrator instructions and dispatching/killing itself. The slim role is *literally named* `orchestrator`, and CLAUDE.md auto-loads into every OpenCode agent in this repo — the risk of it reading "You oversee... delegate to specialized sub-agents... do not write bulk code directly" and concluding that governs *it* is higher here, not lower. Every brief below opens with the override block in the template.

**Standard brief template — prepend this verbatim to every brief file before the task-specific objective:**

```
You are a dispatched OpenCode agent running as `orchestrator` under the
oh-my-opencode-slim plugin (preset "go"). This is NOT the Claude Code
orchestrator described in this repo's CLAUDE.md — that file's "Lead
Architect & Orchestrator" role, its "do not write bulk code directly"
instruction, and its references to scripts/dispatch-opencode.sh and the
bespoke agent fleet (lead-engineer, tester, etc.) do not apply to you and
must be ignored. You implement the task below directly, delegating pieces
of it to your own subagents (@oracle, @librarian, @explorer, @designer,
@fixer, @councillor) as this brief instructs. Do not attempt to invoke
scripts/dispatch-opencode.sh or any bespoke-fleet agent. Do not refuse or
defer implementation on the grounds that "an orchestrator does not write
code" — you are the implementer here.

---
```

**Dispatch command shape used throughout this plan:**

```bash
bash scripts/dispatch-opencode.sh orchestrator <brief-file> --wait 30
# check progress later:
bash scripts/dispatch-opencode.sh --status
```

## File Structure

- Modify: `apps/artifice-ocr/src/artifice_ocr/stages/ocr.py` — prompt-order comment, temperature ladder, blank-page short-circuit call site, rotation-detection call site, configurable prompt wiring.
- Modify: `apps/artifice-ocr/src/artifice_ocr/config.py` — new config keys.
- Modify: `apps/artifice-ocr/src/artifice_ocr/web/routers/settings.py` — expose new keys where the plan says to.
- Modify: `apps/artifice-ocr/src/artifice_ocr/_normalise.py` — defensive YAML front-matter stripping.
- Create: `apps/artifice-ocr/src/artifice_ocr/_rotation.py` — Tesseract-OSD-based orientation probe.
- Create: `apps/artifice-ocr/src/artifice_ocr/_blank.py` — near-blank page detector.
- Create: `apps/artifice-ocr/scripts/measure_ocr_accuracy.py` — CER-based accuracy/wall-time harness CLI.
- Create test files as named in each task.

---

### Task 1: Load-bearing comment on prompt element order (§0)

**Files:**
- Modify: `apps/artifice-ocr/src/artifice_ocr/stages/ocr.py:223-233`

**Interfaces:** No signature changes. Comment-only.

**Delegation:** `@designer` only — this is a one-line comment, no test needed (no behavior change), no `@fixer` pass beyond a full test-suite run to confirm nothing broke.

- [ ] **Step 1: Add the comment**

In `_ocr_vision`, immediately above the `"content": [...]` list:

```python
        response = client.chat(
            model=model,
            messages=[
                {
                    "role": "user",
                    # Order is load-bearing: olmOCR-2 was trained with text
                    # before image (arXiv:2510.19817 s4, "Better prompting") —
                    # reversing it is a training/inference mismatch that
                    # measurably hurt benchmark performance upstream. Do not
                    # "clean up" this ordering in a refactor.
                    "content": [
                        {"type": "text", "text": OCR_PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
                    ],
                }
            ],
            temperature=0.0,
        )
```

(Note: `temperature=0.0` here is superseded by Task 2's ladder — leave it as-is in this task; Task 2 changes this line.)

- [ ] **Step 2: Run the full fast suite to confirm no behavior change**

Run: `cd apps/artifice-ocr && uv run pytest tests/ -x -q --ignore=tests/stress --ignore=tests/test_live_model_interop.py --ignore=tests/test_live_ui_model_interop.py`
Expected: same pass count as before the edit (comment-only change).

- [ ] **Step 3: Commit**

```bash
git add apps/artifice-ocr/src/artifice_ocr/stages/ocr.py
git commit -m "docs(ocr): record why text precedes image in the vision prompt"
```

---

### Task 2: Per-page temperature ladder before the Tesseract fallback (§1)

**Files:**
- Modify: `apps/artifice-ocr/src/artifice_ocr/stages/ocr.py` (`_ocr_vision`)
- Modify: `apps/artifice-ocr/src/artifice_ocr/config.py`
- Modify: `apps/artifice-ocr/src/artifice_ocr/web/routers/settings.py`
- Create: `apps/artifice-ocr/tests/test_ocr_temperature_ladder.py`

**Interfaces:**
- Consumes: `_guard.check_no_repetition_loop(text: str, *, min_lines=20, max_unique_ratio=0.3) -> GuardResult` (`_guard.py:199`), `client.chat(*, model, messages, temperature, **kwargs) -> response` where `response.message.content` is the text (existing backend contract).
- Produces: `_ocr_vision(image_path: Path, orientation: int = 1) -> str` — **unchanged signature**, so `_ocr_single_image` and every other caller needs no change. Internally it now raises `RuntimeError` (a new, undocumented-by-signature but real behavior) when every rung of the ladder is exhausted and still rejected — this is caught by `_ocr_single_image`'s existing `except Exception` block (`ocr.py:270`), which already falls back to Tesseract when `tesseract_fallback_on_failure` is set. No change needed there.

**Design:** Move the repetition check from document-level (`perform()`) to per-page, inside `_ocr_vision`, with a temperature ladder on rejection. Keep the existing document-level check in `perform()` as a secondary safety net (it now mostly won't fire, since per-page loops are caught earlier) — do not remove it.

- [ ] **Step 1: Add config keys**

In `apps/artifice-ocr/src/artifice_ocr/config.py`, in `_DEFAULTS`, near `ocr_repetition_guard`:

```python
    # Per-page temperature ladder: on a repetition-guard rejection, resample
    # the SAME page at a higher temperature instead of discarding the whole
    # document to Tesseract. olmOCR 2 (arXiv:2510.19817 s4, "Dynamic
    # temperature scaling") starts at 0.1 and steps to 0.2, 0.3, ... on each
    # rejection, up to 0.8, reporting ~0.3 accuracy points and a failure rate
    # drop to ~0.01% over fixed-temperature decoding. ``0.0`` (greedy) is
    # MORE loop-prone than the paper's own starting point, not less.
    #
    # ``ocr_temperature_ladder_enabled=False`` restores the exact previous
    # behaviour (temperature 0.0, no ladder) so before/after can be A/B'd
    # with scripts/measure_ocr_accuracy.py.
    "ocr_temperature_ladder_enabled": True,
    "ocr_temperature_ladder_start": 0.1,
    "ocr_temperature_ladder_step": 0.1,
    "ocr_temperature_ladder_max": 0.8,
```

Add `"ocr_temperature_ladder_enabled"`, `"ocr_temperature_ladder_start"`, `"ocr_temperature_ladder_step"`, `"ocr_temperature_ladder_max"` to `PERSISTED_KEYS`.

In `apps/artifice-ocr/src/artifice_ocr/web/routers/settings.py`, add the same four keys to `_CONFIG_KEYS` (find the tuple that already contains `"ocr_max_image_edge"` and add these alongside it).

- [ ] **Step 2: Write the failing tests**

Create `apps/artifice-ocr/tests/test_ocr_temperature_ladder.py`:

```python
# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Per-page temperature ladder on a repetition-guard rejection.

olmOCR 2 (arXiv:2510.19817 s4, "Dynamic temperature scaling"): resample the
SAME page at a rising temperature instead of discarding the whole document to
Tesseract on the first degenerate result.
"""

import pytest
from artifice_ocr.stages import ocr


def _cfg_from(mapping):
    return lambda key, default=None: mapping.get(key, default)


class _ScriptedClient:
    """Returns a different reply for each successive .chat() call."""

    def __init__(self, replies):
        self._replies = list(replies)
        self.seen_temperatures = []

    def chat(self, *, model, messages, temperature, **kwargs):
        self.seen_temperatures.append(temperature)
        content = self._replies.pop(0)

        class _R:
            class message:
                pass

        _R.message.content = content
        return _R()


_LOOP_TEXT = "\n".join(["the same line over and over"] * 40)
_GOOD_TEXT = "\n".join([f"line {i} of real transcription" for i in range(40)])


def _patch_common(monkeypatch, cfg_overrides):
    monkeypatch.setattr(ocr, "cfg", _cfg_from(cfg_overrides))
    monkeypatch.setattr(ocr, "backend_for", lambda role: "ollama")
    monkeypatch.setattr(ocr, "model_for", lambda role: "richardyoung/olmocr2:7b-q8")
    monkeypatch.setattr(
        ocr, "_encode_image", lambda path, orientation=1, *, max_edge=None: ("YmFzZTY0", "image/png")
    )


def test_ladder_disabled_keeps_temperature_zero_and_single_attempt(tmp_path, monkeypatch):
    client = _ScriptedClient([_GOOD_TEXT])
    _patch_common(monkeypatch, {"ocr_temperature_ladder_enabled": False})
    monkeypatch.setattr(ocr, "_get_backend_client", lambda backend: client)

    result = ocr._ocr_vision(tmp_path / "page.png")

    assert result == _GOOD_TEXT
    assert client.seen_temperatures == [0.0]


def test_ladder_escalates_temperature_on_repeated_rejection(tmp_path, monkeypatch):
    client = _ScriptedClient([_LOOP_TEXT, _LOOP_TEXT, _GOOD_TEXT])
    _patch_common(
        monkeypatch,
        {
            "ocr_temperature_ladder_enabled": True,
            "ocr_temperature_ladder_start": 0.1,
            "ocr_temperature_ladder_step": 0.1,
            "ocr_temperature_ladder_max": 0.8,
            "ocr_repetition_guard": True,
        },
    )
    monkeypatch.setattr(ocr, "_get_backend_client", lambda backend: client)

    result = ocr._ocr_vision(tmp_path / "page.png")

    assert result == _GOOD_TEXT
    assert client.seen_temperatures == pytest.approx([0.1, 0.2, 0.3])


def test_ladder_exhausted_raises_so_the_tesseract_fallback_can_catch_it(tmp_path, monkeypatch):
    replies = [_LOOP_TEXT] * 8  # more than enough rungs to exhaust 0.1..0.8
    client = _ScriptedClient(replies)
    _patch_common(
        monkeypatch,
        {
            "ocr_temperature_ladder_enabled": True,
            "ocr_temperature_ladder_start": 0.1,
            "ocr_temperature_ladder_step": 0.1,
            "ocr_temperature_ladder_max": 0.8,
            "ocr_repetition_guard": True,
        },
    )
    monkeypatch.setattr(ocr, "_get_backend_client", lambda backend: client)

    with pytest.raises(RuntimeError, match="repetition"):
        ocr._ocr_vision(tmp_path / "page.png")

    # 0.1, 0.2, ..., 0.8 inclusive = 8 rungs.
    assert len(client.seen_temperatures) == 8


def test_single_image_falls_back_to_tesseract_when_ladder_exhausted(tmp_path, monkeypatch):
    """End-to-end through _ocr_single_image: exhausted ladder -> tesseract-fallback."""
    replies = [_LOOP_TEXT] * 8
    client = _ScriptedClient(replies)
    _patch_common(
        monkeypatch,
        {
            "ocr_temperature_ladder_enabled": True,
            "ocr_temperature_ladder_start": 0.1,
            "ocr_temperature_ladder_step": 0.1,
            "ocr_temperature_ladder_max": 0.8,
            "ocr_repetition_guard": True,
            "ocr_engine": "vision_model",
            "tesseract_fallback_on_failure": True,
        },
    )
    monkeypatch.setattr(ocr, "_get_backend_client", lambda backend: client)
    monkeypatch.setattr(ocr._tesseract, "is_available", lambda: True)
    monkeypatch.setattr(ocr, "_tesseract_from_image", lambda path, orientation=1: "tesseract text")

    text, engine = ocr._ocr_single_image(tmp_path / "page.png")

    assert text == "tesseract text"
    assert engine == "tesseract-fallback"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd apps/artifice-ocr && uv run pytest tests/test_ocr_temperature_ladder.py -v`
Expected: FAIL — current `_ocr_vision` calls `chat()` exactly once at `temperature=0.0` and never inspects the guard, so `seen_temperatures` won't match and no `RuntimeError` is raised.

- [ ] **Step 4: Implement the ladder in `_ocr_vision`**

Replace the body of `_ocr_vision` in `apps/artifice-ocr/src/artifice_ocr/stages/ocr.py` (keep the docstring; replace from `image_b64, mime = ...` to the end):

```python
    image_b64, mime = _encode_image(image_path, orientation, max_edge=_configured_max_image_edge())
    backend = backend_for("vision")
    model = model_for("vision")
    client = _get_backend_client(backend)

    def _call(temperature: float) -> str:
        response = client.chat(
            model=model,
            messages=[
                {
                    "role": "user",
                    # Order is load-bearing: olmOCR-2 was trained with text
                    # before image (arXiv:2510.19817 s4, "Better prompting") —
                    # reversing it is a training/inference mismatch that
                    # measurably hurt benchmark performance upstream. Do not
                    # "clean up" this ordering in a refactor.
                    "content": [
                        {"type": "text", "text": OCR_PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
                    ],
                }
            ],
            temperature=temperature,
        )
        return response.message.content or ""

    if not cfg("ocr_temperature_ladder_enabled"):
        return _call(0.0)

    start = float(cfg("ocr_temperature_ladder_start", 0.1) or 0.1)
    step = float(cfg("ocr_temperature_ladder_step", 0.1) or 0.1)
    ceiling = float(cfg("ocr_temperature_ladder_max", 0.8) or 0.8)
    guard_on = bool(cfg("ocr_repetition_guard"))

    text = ""
    temperature = start
    last_guard = None
    # Ladder: sample at rising temperatures; a page that never trips the
    # repetition guard returns on the first rung, matching the pre-ladder
    # cost exactly. Rejection has no source text to keep — see
    # _guard.check_no_repetition_loop's docstring — so each rung fully
    # replaces the previous rung's output.
    while temperature <= ceiling + 1e-9:
        text = _call(temperature)
        if not guard_on:
            return text
        last_guard = _guard.check_no_repetition_loop(text)
        if last_guard.ok:
            return text
        temperature += step

    reasons = "; ".join(last_guard.reasons) if last_guard else "unknown"
    raise RuntimeError(
        f"OCR repetition guard rejected every temperature rung up to {ceiling}: {reasons}"
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/artifice-ocr && uv run pytest tests/test_ocr_temperature_ladder.py -v`
Expected: PASS, all 4 tests.

- [ ] **Step 6: Run the full fast suite for regressions**

Run: `cd apps/artifice-ocr && uv run pytest tests/ -x -q --ignore=tests/stress --ignore=tests/test_live_model_interop.py --ignore=tests/test_live_ui_model_interop.py`
Expected: all pass, including `tests/test_ocr_image_budget.py::test_vision_call_applies_the_cap` (it calls `_ocr_vision` with a client that returns `"text"` — a 4-character string, which is under `min_lines=20` in `check_no_repetition_loop`, so the guard short-circuits `ok=True` before counting lines; confirm this rather than assuming it).

- [ ] **Step 7: Commit**

```bash
git add apps/artifice-ocr/src/artifice_ocr/stages/ocr.py apps/artifice-ocr/src/artifice_ocr/config.py apps/artifice-ocr/src/artifice_ocr/web/routers/settings.py apps/artifice-ocr/tests/test_ocr_temperature_ladder.py
git commit -m "fix(ocr): escalate temperature per page before falling back to Tesseract"
```

**Delegation:**
- `@explorer`: confirm Step 6's `test_vision_call_applies_the_cap` interaction before implementing (read `_guard.check_no_repetition_loop`'s `min_lines` short-circuit) so the implementer isn't surprised by a pre-existing test's behavior.
- `@designer`: Steps 1, 2, 4 (config keys, tests, implementation).
- `@fixer`: Steps 3, 5, 6 (run/fix the suite).
- `@oracle`: review the diff against the findings doc's "Sketch" in §1 before commit — specifically that escalation target changed from whole-document-to-Tesseract to per-page-ladder-then-Tesseract, and that `ocr_temperature_ladder_enabled=False` reproduces the exact previous behavior bit-for-bit (single call, `temperature=0.0`).

---

### Task 3: Blank-page short-circuit (§5)

**Files:**
- Create: `apps/artifice-ocr/src/artifice_ocr/_blank.py`
- Create: `apps/artifice-ocr/tests/test_blank.py`
- Modify: `apps/artifice-ocr/src/artifice_ocr/stages/ocr.py` (`_ocr_single_image`)
- Modify: `apps/artifice-ocr/src/artifice_ocr/config.py`

**Interfaces:**
- Produces: `is_near_blank(data: bytes, *, std_threshold: float = 6.0) -> bool` in `_blank.py`, consumed by `_ocr_single_image`.
- Consumes: nothing new from other tasks.

**Design:** Check the *encoded* page bytes (post-orientation-correction, post-preprocessing, pre-resize is fine — blank detection doesn't care about resolution) for near-zero greyscale variance. A blank/near-blank page returns fixed sentinel text and `engine="blank-skip"` instead of calling any OCR engine at all.

- [ ] **Step 1: Write the failing test**

Create `apps/artifice-ocr/tests/test_blank.py`:

```python
# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Near-blank page detection: olmOCR 2 (arXiv:2510.19817 s4, "Handle blank
pages") — a model never trained on blank pages hallucinates rather than
returning nothing. A cheap greyscale-variance check skips the call entirely
for a near-blank verso."""

import io

from artifice_ocr._blank import is_near_blank
from PIL import Image


def _solid_png(width, height, color) -> bytes:
    buf = io.BytesIO()
    Image.new("L", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


def _noisy_png(width, height) -> bytes:
    import numpy as np

    arr = (np.random.default_rng(0).random((height, width)) * 255).astype("uint8")
    buf = io.BytesIO()
    Image.fromarray(arr, mode="L").save(buf, format="PNG")
    return buf.getvalue()


def test_solid_white_page_is_blank():
    assert is_near_blank(_solid_png(600, 800, 255)) is True


def test_solid_black_page_is_blank():
    assert is_near_blank(_solid_png(600, 800, 0)) is True


def test_typescript_like_noise_is_not_blank():
    assert is_near_blank(_noisy_png(600, 800)) is False


def test_undecodable_bytes_are_not_treated_as_blank():
    """A decode failure must never silently skip a real page."""
    assert is_near_blank(b"not an image") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/artifice-ocr && uv run pytest tests/test_blank.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'artifice_ocr._blank'`.

- [ ] **Step 3: Implement `_blank.py`**

Create `apps/artifice-ocr/src/artifice_ocr/_blank.py`:

```python
# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Near-blank page detection.

olmOCR 2 (arXiv:2510.19817 s4, "Handle blank pages"): a model never trained
on blank pages hallucinates plausible-looking filler instead of recognising
there is nothing to transcribe. Cheapest fix: never send it one. A blank or
near-blank page (a verso, an inserted flyleaf) has near-zero greyscale
variance regardless of exposure — unlike text detection, this needs no
model and is safe to run unconditionally, independent of the opt-in
``preprocess_enabled`` pipeline.
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image

from artifice_ocr._logging import get_logger

log = get_logger("blank")


def is_near_blank(data: bytes, *, std_threshold: float = 6.0) -> bool:
    """True if *data* decodes to an image with near-zero greyscale variance.

    ``std_threshold`` is a standard deviation on a 0-255 greyscale scale — a
    genuinely blank scan (paper grain, faint scanner shadow) sits under 3;
    typescript or handwriting of any density sits well over 20. 6.0 leaves a
    wide margin on both sides. Never raises: an undecodable image returns
    ``False`` so a corrupt file is never mistaken for blank and silently
    skipped.
    """
    try:
        with Image.open(io.BytesIO(data)) as img:
            grey = img.convert("L")
            arr = np.asarray(grey, dtype=np.float32)
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("Could not decode image for blank-page check: %s", exc)
        return False
    return bool(arr.std() <= std_threshold)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/artifice-ocr && uv run pytest tests/test_blank.py -v`
Expected: PASS, all 4 tests.

- [ ] **Step 5: Wire the short-circuit into `_ocr_single_image` — write the failing integration test**

Add to `apps/artifice-ocr/tests/test_blank.py`:

```python
def test_ocr_single_image_skips_the_call_on_a_blank_page(tmp_path, monkeypatch):
    from artifice_ocr.stages import ocr

    path = tmp_path / "blank.png"
    path.write_bytes(_solid_png(600, 800, 255))

    monkeypatch.setattr(ocr, "cfg", lambda key, default=None: {"ocr_blank_page_skip": True}.get(key, default))

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("OCR engine must not be called for a blank page")

    monkeypatch.setattr(ocr, "_ocr_vision", _fail_if_called)
    monkeypatch.setattr(ocr._tesseract, "ocr_bytes", _fail_if_called)

    text, engine = ocr._ocr_single_image(path)

    assert text == ""
    assert engine == "blank-skip"
```

- [ ] **Step 6: Run to verify it fails**

Run: `cd apps/artifice-ocr && uv run pytest tests/test_blank.py::test_ocr_single_image_skips_the_call_on_a_blank_page -v`
Expected: FAIL — `_ocr_single_image` has no blank check yet, so `_ocr_vision` gets called and raises the assertion.

- [ ] **Step 7: Add the config key and wire the check**

In `config.py` `_DEFAULTS`, near `ocr_repetition_guard`:

```python
    # Skip the OCR call entirely for a near-blank page (a verso, a flyleaf).
    # olmOCR 2 (arXiv:2510.19817 s4, "Handle blank pages"): a model never
    # trained on blank pages hallucinates rather than recognising there is
    # nothing there. See _blank.py.
    "ocr_blank_page_skip": True,
```

Add `"ocr_blank_page_skip"` to `PERSISTED_KEYS` and to `_CONFIG_KEYS` in `settings.py`.

In `apps/artifice-ocr/src/artifice_ocr/stages/ocr.py`, add the import `from artifice_ocr._blank import is_near_blank` near the top, and change `_ocr_single_image`'s opening:

```python
def _ocr_single_image(image_path: Path, orientation: int = 1) -> tuple[str, str]:
    """OCR one image and return ``(text, engine)``.
    ...
    """
    if cfg("ocr_blank_page_skip"):
        raw_bytes = image_path.read_bytes()
        if is_near_blank(raw_bytes):
            log.info("Skipping OCR for near-blank page %s", getattr(image_path, "name", image_path))
            return "", "blank-skip"

    if cfg("ocr_engine", "vision_model") == "tesseract":
        return _tesseract_from_image(image_path, orientation), "tesseract"
    ...
```

(Keep the rest of the function body unchanged.)

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd apps/artifice-ocr && uv run pytest tests/test_blank.py -v`
Expected: PASS, all 5 tests.

- [ ] **Step 9: Run the full fast suite for regressions**

Run: `cd apps/artifice-ocr && uv run pytest tests/ -x -q --ignore=tests/stress --ignore=tests/test_live_model_interop.py --ignore=tests/test_live_ui_model_interop.py`
Expected: all pass.

- [ ] **Step 10: Commit**

```bash
git add apps/artifice-ocr/src/artifice_ocr/_blank.py apps/artifice-ocr/tests/test_blank.py apps/artifice-ocr/src/artifice_ocr/stages/ocr.py apps/artifice-ocr/src/artifice_ocr/config.py apps/artifice-ocr/src/artifice_ocr/web/routers/settings.py
git commit -m "feat(ocr): skip the model call entirely for a near-blank page"
```

**Delegation:** `@designer` (Steps 1, 3, 5, 7), `@fixer` (Steps 2, 4, 6, 8, 9). No `@oracle`/`@librarian` needed — this is small and self-contained.

---

### Task 4: Auto-rotation detection via Tesseract OSD (§4)

**Files:**
- Create: `apps/artifice-ocr/src/artifice_ocr/_rotation.py`
- Create: `apps/artifice-ocr/tests/test_rotation.py`
- Modify: `apps/artifice-ocr/src/artifice_ocr/stages/ocr.py` (`perform`)
- Modify: `apps/artifice-ocr/src/artifice_ocr/config.py`

**Interfaces:**
- Produces: `detect_orientation(image_bytes: bytes) -> int | None` in `_rotation.py` — returns a Tropy-convention orientation value (1/3/6/8; OSD only detects 0/90/180/270° rotation, not mirroring, so only the rotation-only subset of the 1-8 space is reachable) or `None` if Tesseract is unavailable or OSD could not determine an angle.
- Consumes: `artifice_ocr._tesseract.resolve_binary() -> str | None`, `_tesseract._subprocess_window_options()`, `_tesseract._DECODE_AS_UTF8` (all existing, `_tesseract.py`).

**Design:** Only probe when Tropy's own `photos.orientation` is `1` (normal/unflagged) — the exact case the findings doc's real failure was: an unflagged upside-down scan. If Tropy already says 3/6/8, trust it; don't second-guess a value someone set deliberately. Run `tesseract --psm 0` (OSD-only mode) on the page image and parse `Rotate: N` from stdout.

- [ ] **Step 1: Write the failing tests**

Create `apps/artifice-ocr/tests/test_rotation.py`:

```python
# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Auto-rotation detection via Tesseract OSD (arXiv:2510.19817 s4 and the ACL
2026 Demo paper s6 both list automatic rotation correction among the
deployment fixes). Only probed when Tropy's own orientation says "normal" —
see stages/ocr.py::_exif_orientation_matrix's docstring for the real failure
this closes: a page scanned upside-down with no metadata flagging it."""

from unittest.mock import MagicMock

from artifice_ocr import _rotation


def _osd_stdout(rotate_degrees: int) -> str:
    return (
        "Page number: 0\n"
        "Orientation in degrees: 0\n"
        f"Rotate: {rotate_degrees}\n"
        "Orientation confidence: 8.45\n"
        "Script: Latin\n"
        "Script confidence: 4.35\n"
    )


def test_no_rotation_needed_returns_none(monkeypatch):
    monkeypatch.setattr(_rotation._tesseract, "resolve_binary", lambda: "/usr/bin/tesseract")
    monkeypatch.setattr(_rotation.subprocess, "run", lambda *a, **k: MagicMock(returncode=0, stdout=_osd_stdout(0), stderr=""))

    assert _rotation.detect_orientation(b"fake-png-bytes") is None


def test_upside_down_page_maps_to_orientation_3(monkeypatch):
    monkeypatch.setattr(_rotation._tesseract, "resolve_binary", lambda: "/usr/bin/tesseract")
    monkeypatch.setattr(_rotation.subprocess, "run", lambda *a, **k: MagicMock(returncode=0, stdout=_osd_stdout(180), stderr=""))

    assert _rotation.detect_orientation(b"fake-png-bytes") == 3


def test_rotated_90_maps_to_orientation_6(monkeypatch):
    monkeypatch.setattr(_rotation._tesseract, "resolve_binary", lambda: "/usr/bin/tesseract")
    monkeypatch.setattr(_rotation.subprocess, "run", lambda *a, **k: MagicMock(returncode=0, stdout=_osd_stdout(90), stderr=""))

    assert _rotation.detect_orientation(b"fake-png-bytes") == 6


def test_rotated_270_maps_to_orientation_8(monkeypatch):
    monkeypatch.setattr(_rotation._tesseract, "resolve_binary", lambda: "/usr/bin/tesseract")
    monkeypatch.setattr(_rotation.subprocess, "run", lambda *a, **k: MagicMock(returncode=0, stdout=_osd_stdout(270), stderr=""))

    assert _rotation.detect_orientation(b"fake-png-bytes") == 8


def test_no_tesseract_returns_none(monkeypatch):
    monkeypatch.setattr(_rotation._tesseract, "resolve_binary", lambda: None)

    assert _rotation.detect_orientation(b"fake-png-bytes") is None


def test_osd_failure_returns_none_not_raise(monkeypatch):
    """Low-text pages make OSD fail (`Too few characters`) — must degrade, not crash a page."""
    monkeypatch.setattr(_rotation._tesseract, "resolve_binary", lambda: "/usr/bin/tesseract")
    monkeypatch.setattr(
        _rotation.subprocess, "run",
        lambda *a, **k: MagicMock(returncode=1, stdout="", stderr="Too few characters. Skipping this page"),
    )

    assert _rotation.detect_orientation(b"fake-png-bytes") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/artifice-ocr && uv run pytest tests/test_rotation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'artifice_ocr._rotation'`.

- [ ] **Step 3: Implement `_rotation.py`**

Create `apps/artifice-ocr/src/artifice_ocr/_rotation.py`:

```python
# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Auto-rotation detection via Tesseract's orientation-and-script-detection
(OSD) mode.

olmOCR 2 (arXiv:2510.19817 s4) and the ACL 2026 Demo paper (s6) both list
automatic rotation correction among the deployment fixes that "further
improved robustness without retraining." This app already corrects a known
Tropy `photos.orientation` value (see stages/ocr.py::_exif_orientation_matrix)
but has no detector of its own — it trusts upstream metadata entirely, and
that metadata has been wrong in a documented real case (a page scanned
upside-down with orientation left at 1/normal, which the model then
hallucinated over instead of transcribing).

OSD only detects axis-aligned rotation (0/90/180/270 degrees), not
mirroring — so only orientations 1, 6, 3, 8 (the pure-rotation subset of the
EXIF/Tropy 1-8 convention) are ever returned. That is also the only subset a
scanner or a phone camera actually produces; mirrored scans are not a real
failure mode this needs to cover.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from artifice_ocr import _tesseract
from artifice_ocr._logging import get_logger

log = get_logger("rotation")

# Tesseract's `Rotate: N` (degrees the image must be rotated clockwise to be
# upright) to the Tropy/EXIF orientation code _exif_orientation_matrix expects.
_ROTATE_TO_ORIENTATION = {0: None, 90: 6, 180: 3, 270: 8}

_ROTATE_RE = re.compile(r"^Rotate:\s*(\d+)", re.MULTILINE)


def detect_orientation(image_bytes: bytes) -> int | None:
    """Probe *image_bytes* with `tesseract --psm 0` and return a Tropy-style
    orientation code, or ``None`` when no correction is needed, Tesseract is
    unavailable, or OSD could not determine an angle (common on sparse-text
    or non-text pages — this must degrade silently, never fail the page).
    """
    binary = _tesseract.resolve_binary()
    if not binary:
        return None

    with tempfile.NamedTemporaryFile(prefix="ocr_osd_", suffix=".png", delete=False) as tmp:
        tmp.write(image_bytes)
        tmp_path = Path(tmp.name)
    try:
        proc = subprocess.run(
            [binary, str(tmp_path), "stdout", "--psm", "0"],
            capture_output=True,
            text=True,
            **_tesseract._DECODE_AS_UTF8,
            timeout=30,
            **_tesseract._subprocess_window_options(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("Rotation OSD failed to run: %s", exc)
        return None
    finally:
        tmp_path.unlink(missing_ok=True)

    if proc.returncode != 0:
        log.debug("Rotation OSD declined (likely too little text): %s", (proc.stderr or "").strip())
        return None

    match = _ROTATE_RE.search(proc.stdout or "")
    if not match:
        return None
    degrees = int(match.group(1))
    return _ROTATE_TO_ORIENTATION.get(degrees)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/artifice-ocr && uv run pytest tests/test_rotation.py -v`
Expected: PASS, all 6 tests.

- [ ] **Step 5: Wire it into `perform()` — write the failing integration test**

Add to `apps/artifice-ocr/tests/test_rotation.py`:

```python
def test_perform_probes_rotation_only_when_orientation_is_normal(tmp_path, monkeypatch):
    from artifice_ocr.stages import ocr

    calls = []
    monkeypatch.setattr(ocr, "cfg", lambda key, default=None: {
        "ocr_auto_rotation_detect": True, "ocr_repetition_guard": False,
    }.get(key, default))
    monkeypatch.setattr(ocr, "_ocr_single_image", lambda path, orientation=1: ("text", "ollama"))
    monkeypatch.setattr(_rotation, "detect_orientation", lambda data: calls.append(data) or 3)

    path = tmp_path / "page.jpg"
    path.write_bytes(b"fake-jpeg-bytes")
    ocr.perform(str(path), output_dir=str(tmp_path / "out"), orientation=1)

    assert len(calls) == 1  # probed, because orientation was 1 (normal)


def test_perform_skips_the_probe_when_orientation_already_set(tmp_path, monkeypatch):
    from artifice_ocr.stages import ocr

    calls = []
    monkeypatch.setattr(ocr, "cfg", lambda key, default=None: {
        "ocr_auto_rotation_detect": True, "ocr_repetition_guard": False,
    }.get(key, default))
    monkeypatch.setattr(ocr, "_ocr_single_image", lambda path, orientation=1: ("text", "ollama"))
    monkeypatch.setattr(_rotation, "detect_orientation", lambda data: calls.append(data) or 3)

    path = tmp_path / "page.jpg"
    path.write_bytes(b"fake-jpeg-bytes")
    ocr.perform(str(path), output_dir=str(tmp_path / "out"), orientation=6)

    assert calls == []  # not probed — orientation was already explicit
```

- [ ] **Step 6: Run to verify it fails**

Run: `cd apps/artifice-ocr && uv run pytest tests/test_rotation.py::test_perform_probes_rotation_only_when_orientation_is_normal -v`
Expected: FAIL — `perform()` never calls `detect_orientation` today.

- [ ] **Step 7: Add the config key and wire the probe**

In `config.py` `_DEFAULTS`, near `ocr_repetition_guard`:

```python
    # Probe a page with Tesseract OSD for rotation ONLY when Tropy's own
    # orientation metadata says "normal" (1) — an explicit non-1 value is
    # trusted as a deliberate correction and never second-guessed. Off by
    # default: it costs a Tesseract subprocess call per page and Tesseract
    # is an optional dependency. arXiv:2510.19817 s4, "automatic rotation
    # correction". See _rotation.py.
    "ocr_auto_rotation_detect": False,
```

Add `"ocr_auto_rotation_detect"` to `PERSISTED_KEYS` and to `_CONFIG_KEYS` in `settings.py`.

In `apps/artifice-ocr/src/artifice_ocr/stages/ocr.py`, add `from artifice_ocr import _rotation` near the top, and in `perform()`, immediately after `is_pdf = path.suffix.lower() == ".pdf"`:

```python
    is_pdf = path.suffix.lower() == ".pdf"

    if orientation == 1 and cfg("ocr_auto_rotation_detect"):
        try:
            detected = _rotation.detect_orientation(path.read_bytes())
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("Rotation auto-detection failed for %s: %s", path.name, exc)
            detected = None
        if detected is not None:
            log.info("Auto-detected rotation for %s: orientation %d", path.name, detected)
            orientation = detected
```

(This only reads raw file bytes for the probe — cheap, and separate from the per-page rendering pipeline. For a PDF this reads the whole PDF file bytes, which is wasteful; note that limitation below rather than solving it now.)

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd apps/artifice-ocr && uv run pytest tests/test_rotation.py -v`
Expected: PASS, all 8 tests.

- [ ] **Step 9: Run the full fast suite for regressions**

Run: `cd apps/artifice-ocr && uv run pytest tests/ -x -q --ignore=tests/stress --ignore=tests/test_live_model_interop.py --ignore=tests/test_live_ui_model_interop.py`
Expected: all pass.

- [ ] **Step 10: Commit**

```bash
git add apps/artifice-ocr/src/artifice_ocr/_rotation.py apps/artifice-ocr/tests/test_rotation.py apps/artifice-ocr/src/artifice_ocr/stages/ocr.py apps/artifice-ocr/src/artifice_ocr/config.py apps/artifice-ocr/src/artifice_ocr/web/routers/settings.py
git commit -m "feat(ocr): detect rotation with Tesseract OSD when Tropy metadata is unset"
```

**Known limitation to flag, not fix here:** feeding a whole PDF's raw bytes to `detect_orientation` for a multi-page PDF means Tesseract OSD reads/rasterizes the PDF itself for probing, redundant with `_pdf_to_page_images`'s own rendering. Acceptable for a first cut (it is a single cheap-relative-to-the-vision-call subprocess call, opt-in and off by default); revisit if `ocr_auto_rotation_detect` sees real use and PDF throughput matters.

**Delegation:**
- `@librarian`: pull Tesseract OSD's exact `--psm 0` stdout format and the "Too few characters" failure string before implementation, to ground the parsing regex and the failure test — the values above are from this app's own conventions (`_tesseract.py`'s decode/timeout pattern), verify the OSD output format against Tesseract's actual documentation rather than trusting the brief's example verbatim.
- `@designer`: Steps 1, 3, 5, 7.
- `@fixer`: Steps 2, 4, 6, 8, 9.

---

### Task 5: OCR-accuracy measurement harness (the blocker under all of this)

**Files:**
- Create: `apps/artifice-ocr/scripts/measure_ocr_accuracy.py`
- Create: `apps/artifice-ocr/tests/test_measure_ocr_accuracy.py`
- Create: `apps/artifice-ocr/eval_corpus/README.md`

**Interfaces:**
- Produces: `character_error_rate(reference: str, hypothesis: str) -> float` and `measure_page(image_path: Path, ground_truth_path: Path, *, orientation: int = 1) -> dict` in `measure_ocr_accuracy.py`, plus a `main()` CLI entry point.

**Design and scope note — read before delegating:** The findings doc calls this "arguably item 0" and wants a corpus of 10-20 representative pages (typescript, handwriting, tables, multi-column, a blank verso, a mis-oriented scan) with ground-truth transcriptions. **No agent can fabricate that corpus** — ground-truth transcriptions of real archival material are the maintainer's to supply or curate, not something to synthesize. This task builds the *tool* (metric + runner + reporting) and unit-tests it against synthetic strings, so it is fully testable and mergeable without the real corpus existing yet. Populating `eval_corpus/` with real pages and transcriptions is a follow-up action for the maintainer, called out explicitly in the generated `eval_corpus/README.md`, not a step below.

**Metric choice:** [CENT] uses SpACER specifically because CER assumes linear reading order, which doesn't hold for scattered marginalia. SpACER's exact algorithm is not reproducible from the citation in the findings doc alone. This task implements **character error rate (CER)** — a standard Levenshtein-distance-based metric — and states this limitation plainly in the script's docstring and in `eval_corpus/README.md`, rather than pretending to implement SpACER. Swapping in a truer SpACER implementation is future work if the maintainer sources the exact algorithm.

- [ ] **Step 1: Write the failing tests**

Create `apps/artifice-ocr/tests/test_measure_ocr_accuracy.py`:

```python
# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Character-error-rate harness. See scripts/measure_ocr_accuracy.py for why
CER, not SpACER — this repo has no accuracy harness at all today
(OLMOCR2_OPTIMISATION_FINDINGS.md, "The blocker under all of this"), so a
correct-but-imperfect metric that exists beats a perfect one that doesn't."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from measure_ocr_accuracy import character_error_rate, measure_page  # noqa: E402


def test_identical_strings_have_zero_error():
    assert character_error_rate("hello world", "hello world") == 0.0


def test_completely_different_strings_have_high_error():
    assert character_error_rate("abc", "xyz") == 1.0


def test_empty_reference_and_empty_hypothesis_is_zero_error():
    assert character_error_rate("", "") == 0.0


def test_empty_reference_nonempty_hypothesis_is_full_error():
    assert character_error_rate("", "abc") == 1.0


def test_single_substitution_out_of_ten_chars():
    assert character_error_rate("abcdefghij", "abcdefghiX") == 0.1


def test_measure_page_reports_error_rate_and_wall_time(tmp_path, monkeypatch):
    gt_path = tmp_path / "page.txt"
    gt_path.write_text("hello world", encoding="utf-8")
    img_path = tmp_path / "page.png"
    img_path.write_bytes(b"fake-png")

    import measure_ocr_accuracy as mod

    monkeypatch.setattr(mod, "_ocr_page", lambda path, orientation: "hello world")

    result = measure_page(img_path, gt_path)

    assert result["cer"] == 0.0
    assert result["wall_time_s"] >= 0.0
    assert result["page"] == "page.png"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/artifice-ocr && uv run pytest tests/test_measure_ocr_accuracy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'measure_ocr_accuracy'`.

- [ ] **Step 3: Implement `measure_ocr_accuracy.py`**

Create `apps/artifice-ocr/scripts/measure_ocr_accuracy.py`:

```python
#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""OCR accuracy and wall-time measurement harness.

This is the harness OLMOCR2_OPTIMISATION_FINDINGS.md calls the real blocker:
there is no way to check any of that document's claims against this app's
actual behaviour, because there is no accuracy measurement at all. Every
number in that document is from a paper, not from this codebase.

Metric: character error rate (CER), a standard Levenshtein-distance-based
metric — NOT SpACER, the metric [CENT] (arXiv:2608.30616) uses. [CENT] picks
SpACER specifically because "CER assumes a fixed linear reading order that
does not hold for scattered annotations" (s5.1) — a real caveat for
marginalia and annotated archival material. SpACER's exact algorithm is not
reproducible from a citation alone; CER is implemented here because it is
well-defined and enough to detect changes of the size the referenced papers
describe (single-digit-percent swings). A future SpACER implementation is
welcome if the exact algorithm is sourced from the paper.

Usage:
    uv run python scripts/measure_ocr_accuracy.py eval_corpus/

Expects, for each page in the given directory:
    <stem>.png|.jpg|.jpeg|.tif|.tiff   the scanned page image
    <stem>.txt                         the ground-truth transcription
    <stem>.orientation                 optional; a single int 1-8 (default 1)
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def character_error_rate(reference: str, hypothesis: str) -> float:
    """Levenshtein character edit distance / len(reference), clamped to
    [0, 1]. ``(0, 0)`` (both empty) is defined as zero error, not a division
    by zero."""
    if not reference and not hypothesis:
        return 0.0
    if not reference:
        return 1.0

    # Standard O(len(ref) * len(hyp)) DP edit distance.
    ref, hyp = reference, hypothesis
    prev = list(range(len(hyp) + 1))
    for i, r_ch in enumerate(ref, start=1):
        curr = [i] + [0] * len(hyp)
        for j, h_ch in enumerate(hyp, start=1):
            cost = 0 if r_ch == h_ch else 1
            curr[j] = min(
                prev[j] + 1,       # deletion
                curr[j - 1] + 1,   # insertion
                prev[j - 1] + cost,  # substitution/match
            )
        prev = curr
    distance = prev[-1]
    return min(1.0, distance / len(ref))


def _ocr_page(image_path: Path, orientation: int) -> str:
    """Run this app's own OCR stage on one page. Imports lazily so unit tests
    that stub this function never need a live model backend."""
    from artifice_ocr.stages.ocr import _ocr_single_image

    text, _engine = _ocr_single_image(image_path, orientation)
    return text


def measure_page(image_path: Path, ground_truth_path: Path, *, orientation: int = 1) -> dict[str, Any]:
    """OCR one page and score it against its ground truth. Returns a dict
    with ``page``, ``cer``, ``wall_time_s``, ``reference_chars``."""
    reference = ground_truth_path.read_text(encoding="utf-8")
    start = time.monotonic()
    hypothesis = _ocr_page(image_path, orientation)
    elapsed = time.monotonic() - start
    return {
        "page": image_path.name,
        "cer": character_error_rate(reference, hypothesis),
        "wall_time_s": elapsed,
        "reference_chars": len(reference),
    }


_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".tif", ".tiff")


def _discover_pages(corpus_dir: Path) -> list[tuple[Path, Path, int]]:
    pages = []
    for txt_path in sorted(corpus_dir.glob("*.txt")):
        stem = txt_path.stem
        image_path = next(
            (corpus_dir / f"{stem}{suffix}" for suffix in _IMAGE_SUFFIXES if (corpus_dir / f"{stem}{suffix}").exists()),
            None,
        )
        if image_path is None:
            print(f"WARNING: no image found for {txt_path.name}, skipping", file=sys.stderr)
            continue
        orient_path = corpus_dir / f"{stem}.orientation"
        orientation = int(orient_path.read_text().strip()) if orient_path.exists() else 1
        pages.append((image_path, txt_path, orientation))
    return pages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("corpus_dir", type=Path, help="Directory of <stem>.{png,jpg,...} + <stem>.txt pairs")
    args = parser.parse_args()

    pages = _discover_pages(args.corpus_dir)
    if not pages:
        print(f"No page/ground-truth pairs found in {args.corpus_dir}", file=sys.stderr)
        return 1

    results = [measure_page(img, gt, orientation=orient) for img, gt, orient in pages]

    total_chars = sum(r["reference_chars"] for r in results)
    weighted_cer = (
        sum(r["cer"] * r["reference_chars"] for r in results) / total_chars if total_chars else 0.0
    )
    total_time = sum(r["wall_time_s"] for r in results)

    for r in results:
        print(f"{r['page']:40s} CER={r['cer']:.4f}  {r['wall_time_s']:.2f}s")
    print("-" * 60)
    print(f"{'weighted CER':40s} {weighted_cer:.4f}")
    print(f"{'total wall time':40s} {total_time:.2f}s over {len(results)} page(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/artifice-ocr && uv run pytest tests/test_measure_ocr_accuracy.py -v`
Expected: PASS, all 6 tests.

- [ ] **Step 5: Create the corpus README for the maintainer**

Create `apps/artifice-ocr/eval_corpus/README.md`:

```markdown
# OCR accuracy evaluation corpus

Empty by design. `scripts/measure_ocr_accuracy.py` reads pairs from this
directory:

- `<stem>.png` (or `.jpg`/`.jpeg`/`.tif`/`.tiff`) — the scanned page
- `<stem>.txt` — its exact ground-truth transcription
- `<stem>.orientation` — optional, a single integer 1-8 (Tropy/EXIF
  convention; default 1 if absent)

**This corpus cannot be generated automatically.** Per
`OLMOCR2_OPTIMISATION_FINDINGS.md`, populate it with 10-20 pages
representative of real use: typescript, handwriting, a table, a multi-column
layout, a blank verso, and a mis-oriented scan, each with a verified
ground-truth transcription. Run:

    uv run python scripts/measure_ocr_accuracy.py eval_corpus/

**Metric caveat:** this harness scores character error rate (CER), which
assumes a fixed linear reading order. [CENT] (arXiv:2608.30616, s5.1) notes
CER "does not hold for scattered annotations" — treat a high CER on a page
with marginalia or non-linear layout with that in mind, not as a flat
"worse" verdict.
```

- [ ] **Step 6: Run the full fast suite for regressions**

Run: `cd apps/artifice-ocr && uv run pytest tests/ -x -q --ignore=tests/stress --ignore=tests/test_live_model_interop.py --ignore=tests/test_live_ui_model_interop.py`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add apps/artifice-ocr/scripts/measure_ocr_accuracy.py apps/artifice-ocr/tests/test_measure_ocr_accuracy.py apps/artifice-ocr/eval_corpus/README.md
git commit -m "feat(ocr): add a CER-based accuracy and wall-time measurement harness"
```

**Delegation:**
- `@oracle`: judge the CER-vs-SpACER tradeoff and the corpus-scope note before implementation — confirm the plan's framing (implement CER now, document the gap, don't fake SpACER) is the right call rather than either overclaiming or blocking on an unreproducible metric.
- `@designer`: Steps 1, 3, 5.
- `@fixer`: Steps 2, 4, 6.

---

### Task 6: Defensive YAML front-matter stripping (§3 robustness)

**Files:**
- Modify: `apps/artifice-ocr/src/artifice_ocr/_normalise.py`
- Test: add to existing `apps/artifice-ocr/tests/test_normalise.py`

**Interfaces:** `normalise(text: str) -> tuple[str, dict]` (existing, `_normalise.py:221`) — add a leading step that strips a leading `---`-delimited YAML block before the existing normalisation steps run, recording whether it fired in the returned stats dict.

**Rationale:** Independent of the §3/item-6 architectural decision below (whether to change the prompt to elicit YAML+Markdown on purpose), this closes a real, already-possible failure: `OCR_PROMPT` asks for raw text, but nothing stops a model RLVR'd toward YAML front matter from emitting one anyway, and today it would be written straight into `raw_ocr/text/*.txt` as if it were transcribed content. Safe and worth doing regardless of the architectural decision in Task 7.

- [ ] **Step 1: Read the current `normalise()` entry point**

Read `apps/artifice-ocr/src/artifice_ocr/_normalise.py:217-260` (or wherever `def normalise` currently ends) before editing, to match its existing stats-dict shape and step-numbering convention (`_rejoin_hyphenated_lower`, `_join_emdash_break`, etc. all return `(text, count)` and get folded into one dict) — do not invent a different return shape.

- [ ] **Step 2: Write the failing test**

Add to `apps/artifice-ocr/tests/test_normalise.py`:

```python
def test_leaked_yaml_front_matter_is_stripped_before_normalisation():
    from artifice_ocr._normalise import normalise

    text = (
        "---\n"
        "primary_language: en\n"
        "is_rotation_valid: true\n"
        "---\n"
        "This is the actual page text.\n"
    )
    cleaned, stats = normalise(text)

    assert "primary_language" not in cleaned
    assert "---" not in cleaned
    assert "This is the actual page text." in cleaned
    assert stats.get("front_matter_stripped") is True


def test_text_without_front_matter_is_unaffected():
    from artifice_ocr._normalise import normalise

    text = "Just ordinary transcribed text, no --- anywhere relevant.\n"
    cleaned, stats = normalise(text)

    assert cleaned.strip() == text.strip()
    assert stats.get("front_matter_stripped", False) is False


def test_a_lone_leading_dash_line_is_not_mistaken_for_front_matter():
    """A page whose real content starts with a horizontal rule must survive."""
    from artifice_ocr._normalise import normalise

    text = "---\nNo closing delimiter follows, so this is not front matter.\n"
    cleaned, stats = normalise(text)

    assert cleaned.strip().startswith("---")
    assert stats.get("front_matter_stripped", False) is False
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd apps/artifice-ocr && uv run pytest tests/test_normalise.py -k front_matter -v`
Expected: FAIL — `normalise()` currently passes the leading `---` block straight through.

- [ ] **Step 4: Implement the strip step**

In `apps/artifice-ocr/src/artifice_ocr/_normalise.py`, add near the other `_step`-style helpers:

```python
import re

_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?\n)?---\s*\n", re.DOTALL)


def _strip_leaked_front_matter(text: str) -> tuple[str, bool]:
    """Remove a leading ``---``-delimited YAML block if present.

    OCR_PROMPT asks for raw text with no formatting, but a model RLVR'd
    toward YAML-front-matter-plus-Markdown output (see
    OLMOCR2_OPTIMISATION_FINDINGS.md s3) can still emit one. Nothing else in
    this pipeline recognises it, so left unstripped it is written to
    raw_ocr/text/*.txt as if it were transcribed page content. Requires a
    matching closing ``---`` — a page whose genuine content happens to open
    with a horizontal rule (a single ``---`` with no closer) is left alone.
    """
    match = _FRONT_MATTER_RE.match(text)
    if not match:
        return text, False
    return text[match.end():], True
```

Then in `normalise()`, call it first and fold `front_matter_stripped` into the returned stats dict — read the existing function body first (Step 1) and match its exact pattern; do not restructure the other steps.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/artifice-ocr && uv run pytest tests/test_normalise.py -v`
Expected: PASS, including all pre-existing tests in the file (no regression to the other normalisation steps).

- [ ] **Step 6: Run the full fast suite for regressions**

Run: `cd apps/artifice-ocr && uv run pytest tests/ -x -q --ignore=tests/stress --ignore=tests/test_live_model_interop.py --ignore=tests/test_live_ui_model_interop.py`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add apps/artifice-ocr/src/artifice_ocr/_normalise.py apps/artifice-ocr/tests/test_normalise.py
git commit -m "fix(ocr): strip leaked YAML front matter before it reaches raw_ocr text"
```

**Delegation:** `@explorer` first (Step 1 — read the real current shape of `normalise()`, since this plan was written from a grep, not a full read, and the exact stats-dict merge point must match what's actually there). `@designer` (Steps 2, 4). `@fixer` (Steps 3, 5, 6).

---

### Task 7: Configurable domain instruction prompt (§6a) — needs a maintainer decision on UI exposure

**Files:**
- Modify: `apps/artifice-ocr/src/artifice_ocr/stages/ocr.py` (`_ocr_vision`, `perform`)
- Modify: `apps/artifice-ocr/src/artifice_ocr/config.py`
- Modify: `apps/artifice-ocr/src/artifice_ocr/web/routers/settings.py` — **only if the maintainer confirms UI exposure; see Step 0.**

**Interfaces:** New config key `ocr_prompt_instruction` (default `""`, meaning "use `OCR_PROMPT` unchanged"). When set, it is **appended** to `OCR_PROMPT`, not a replacement — the base prompt's "return only raw text" contract stays intact; the instruction adds domain framing (e.g. "This is a handwritten 19th-century archaeological field catalogue; expect German Kurrentschrift and abbreviated genus/species names.").

[CENT] Table 4: zero-shot domain instruction prompting on olmOCR2 took SpACER-M error from 15.58% to 6.77% and field EMR from 30.55% to 74.64% — the single largest measured, zero-training win in the source material for this plan.

- [ ] **Step 0: This step is a checkpoint, not implementation work — do not skip it.**

This table row is explicitly marked "Yes — UI surface" in the findings doc's priority table: it is a **product decision**, not an engineering one, because it adds a free-text field the user fills in per run. Before Steps 4/7 (UI wiring) proceed, `@councillor` prepares a short options brief for the maintainer covering: (a) where the field lives (a Settings tab field like every other config key, vs. a per-run field on the upload/queue screen, since "domain instruction" is more naturally a per-document-collection choice than a persisted global setting), and (b) whether it should also accept a small few-shot exemplar (findings §6, the LoRA/few-shot row) or stay single-instruction-only for this pass. **Steps 1-3, 5-6 (config key, backend wiring, sidecar, tests) do not depend on this answer and can proceed regardless — only Steps 4 and 7 (UI) are gated.**

- [ ] **Step 1: Add the config key**

In `config.py` `_DEFAULTS`, near `ocr_max_image_edge`:

```python
    # Free-text domain instruction, appended to OCR_PROMPT (not a replacement
    # — the "return only raw text" contract stays intact). [CENT]
    # (arXiv:2608.30616) Table 4: a zero-shot domain instruction prompt took
    # olmOCR2's SpACER-M error from 15.58% to 6.77% and field EMR from 30.55%
    # to 74.64%, with no training. Empty string (default) leaves OCR_PROMPT
    # exactly as it was. Already recorded per-run in the raw_ocr sidecar as
    # part of "ocr_prompt" — see stages/ocr.py::perform.
    "ocr_prompt_instruction": "",
```

Add `"ocr_prompt_instruction"` to `PERSISTED_KEYS`.

- [ ] **Step 2: Write the failing test**

Create `apps/artifice-ocr/tests/test_ocr_prompt_instruction.py`:

```python
# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Configurable per-collection domain instruction, appended to OCR_PROMPT.
[CENT] (arXiv:2608.30616) Table 4: the single largest measured, zero-training
accuracy win in the source material for this plan."""

from artifice_ocr.stages import ocr


def _cfg_from(mapping):
    return lambda key, default=None: mapping.get(key, default)


def test_empty_instruction_leaves_prompt_unchanged():
    assert ocr._effective_prompt("") == ocr.OCR_PROMPT


def test_instruction_is_appended_not_replacing_the_base_prompt():
    prompt = ocr._effective_prompt("This is a 19th-century field catalogue in German Kurrentschrift.")
    assert prompt.startswith(ocr.OCR_PROMPT)
    assert "19th-century field catalogue" in prompt


def test_vision_call_uses_the_effective_prompt(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, "cfg", _cfg_from({
        "ocr_prompt_instruction": "Expect handwritten German.",
        "ocr_temperature_ladder_enabled": False,
    }))
    monkeypatch.setattr(ocr, "backend_for", lambda role: "ollama")
    monkeypatch.setattr(ocr, "model_for", lambda role: "richardyoung/olmocr2:7b-q8")
    monkeypatch.setattr(
        ocr, "_encode_image", lambda path, orientation=1, *, max_edge=None: ("YmFzZTY0", "image/png")
    )

    seen = {}

    class _Client:
        def chat(self, *, model, messages, temperature, **kwargs):
            seen["prompt_text"] = messages[0]["content"][0]["text"]

            class _R:
                class message:
                    content = "text"

            return _R()

    monkeypatch.setattr(ocr, "_get_backend_client", lambda backend: _Client())
    ocr._ocr_vision(tmp_path / "page.png")

    assert "Expect handwritten German." in seen["prompt_text"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd apps/artifice-ocr && uv run pytest tests/test_ocr_prompt_instruction.py -v`
Expected: FAIL — `ocr._effective_prompt` does not exist yet, and `_ocr_vision` uses the raw `OCR_PROMPT` constant.

- [ ] **Step 4: Implement `_effective_prompt` and wire it into `_ocr_vision`**

In `apps/artifice-ocr/src/artifice_ocr/stages/ocr.py`, add near `OCR_PROMPT`:

```python
def _effective_prompt(instruction: str) -> str:
    """OCR_PROMPT, plus an optional appended domain instruction.

    Appended, never a replacement: the base prompt's "return only raw text,
    no commentary/labels/formatting" contract must survive regardless of what
    the domain instruction says, since downstream stages (cleanup, structure)
    depend on it.
    """
    instruction = (instruction or "").strip()
    if not instruction:
        return OCR_PROMPT
    return f"{OCR_PROMPT}\n\n{instruction}"
```

In `_ocr_vision`'s inner `_call`, change:

```python
                    "content": [
                        {"type": "text", "text": OCR_PROMPT},
```

to:

```python
                    "content": [
                        {"type": "text", "text": _effective_prompt(cfg("ocr_prompt_instruction", ""))},
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/artifice-ocr && uv run pytest tests/test_ocr_prompt_instruction.py -v`
Expected: PASS, all 3 tests.

- [ ] **Step 6: Confirm the sidecar records the effective prompt, not just the base one**

`perform()` already writes `"ocr_prompt": OCR_PROMPT` into both the rejection sidecar and the success sidecar JSON (`ocr.py:508, 543`). Change both occurrences to `"ocr_prompt": _effective_prompt(cfg("ocr_prompt_instruction", ""))` so the recorded prompt matches what was actually sent — this is the "already has the field" the findings doc refers to; it just currently records the wrong value when an instruction is set. No new test file needed: extend `tests/test_pipeline.py`'s existing `perform()`-level tests with one assertion that `data["ocr_prompt"]` reflects a configured instruction. Read `test_pipeline.py`'s existing `perform()` fixtures first (`@explorer`) to match its mocking pattern before adding to it.

- [ ] **Step 7 (gated on Step 0's maintainer answer): expose in Settings UI**

Only if the maintainer confirms a persisted Settings-tab field: add `"ocr_prompt_instruction"` to `_CONFIG_KEYS` in `web/routers/settings.py`, following the exact pattern of every other string setting already there. If the maintainer instead wants a per-run field, that is a larger UI task (a new form field on the upload/queue screen, not just a settings key) — write it as a **separate follow-up plan**, not squeezed into this step, since it touches a different part of the UI than every other task in this plan.

- [ ] **Step 8: Run the full fast suite for regressions**

Run: `cd apps/artifice-ocr && uv run pytest tests/ -x -q --ignore=tests/stress --ignore=tests/test_live_model_interop.py --ignore=tests/test_live_ui_model_interop.py`
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add apps/artifice-ocr/src/artifice_ocr/stages/ocr.py apps/artifice-ocr/src/artifice_ocr/config.py apps/artifice-ocr/tests/test_ocr_prompt_instruction.py apps/artifice-ocr/tests/test_pipeline.py
# add web/routers/settings.py too if Step 7 applied
git commit -m "feat(ocr): support a configurable per-collection domain instruction prompt"
```

**Delegation:**
- `@councillor`: Step 0 — the options brief for the maintainer. Do this **before** dispatching Steps 4/7 so the UI question isn't answered by default.
- `@explorer`: read `test_pipeline.py`'s `perform()` fixtures before Step 6.
- `@designer`: Steps 1, 2, 4, 6, and 7 if confirmed.
- `@fixer`: Steps 3, 5, 8.

---

### Task 8: Experimental structured-prompt flag for measurement only (§3 / table item 6)

**Files:**
- Modify: `apps/artifice-ocr/src/artifice_ocr/stages/ocr.py`
- Modify: `apps/artifice-ocr/src/artifice_ocr/config.py`
- Create: `apps/artifice-ocr/tests/test_ocr_prompt_style_experiment.py`

**Interfaces:** New config key `ocr_prompt_style` (default `"raw"`, alternate value `"structured"`), read by `_effective_prompt` (from Task 7) or a small wrapper around it.

**This task ships an experiment, not a default-behavior change.** The findings doc is explicit that this is "a genuine trade that cannot be settled by reading" and needs the Task 5 harness before any decision. Do not, under any circumstance, change `ocr_prompt_style`'s default away from `"raw"` as part of this task — that decision belongs to the maintainer, informed by running Task 5's harness with both prompt styles once a real corpus exists (Task 5's `eval_corpus/README.md`).

- [ ] **Step 1: Write the failing test**

Create `apps/artifice-ocr/tests/test_ocr_prompt_style_experiment.py`:

```python
# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Experimental structured-prompt variant, for A/B measurement only via
scripts/measure_ocr_accuracy.py. See OLMOCR2_OPTIMISATION_FINDINGS.md s3 —
olmOCR-2-7B-1025 was trained toward YAML-front-matter + Markdown output, not
the raw-text prompt this app uses by default. Whether raw or structured wins
for this app's users is an open, unmeasured question; this only makes the
comparison possible, it does not decide it."""

from artifice_ocr.stages import ocr


def test_default_style_is_raw_and_unchanged():
    assert ocr._STRUCTURED_PROMPT_ADDENDUM not in ocr._effective_prompt("", style="raw")
    assert ocr._effective_prompt("", style="raw") == ocr.OCR_PROMPT


def test_structured_style_asks_for_markdown_and_front_matter():
    prompt = ocr._effective_prompt("", style="structured")
    assert "yaml" in prompt.lower() or "front matter" in prompt.lower()
    assert "markdown" in prompt.lower()


def test_instruction_and_structured_style_compose():
    prompt = ocr._effective_prompt("Expect handwritten German.", style="structured")
    assert "Expect handwritten German." in prompt
    assert "markdown" in prompt.lower()


def test_default_config_key_is_raw():
    from artifice_ocr.config import _DEFAULTS

    assert _DEFAULTS["ocr_prompt_style"] == "raw"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/artifice-ocr && uv run pytest tests/test_ocr_prompt_style_experiment.py -v`
Expected: FAIL — `_effective_prompt` (from Task 7) does not yet accept a `style` argument, and `_STRUCTURED_PROMPT_ADDENDUM` does not exist.

- [ ] **Step 3: Extend `_effective_prompt` with the structured variant**

In `apps/artifice-ocr/src/artifice_ocr/stages/ocr.py`, add near `OCR_PROMPT`:

```python
# Experimental only — see OLMOCR2_OPTIMISATION_FINDINGS.md s3. olmOCR-2 was
# SFT'd/RLVR'd toward YAML-front-matter + Markdown-body output; this addendum
# asks for that shape instead of the raw-text default. Gated by
# ocr_prompt_style, default "raw". DO NOT flip the default without measured
# results from scripts/measure_ocr_accuracy.py AND explicit maintainer
# sign-off — switching stage 1's output shape changes the contract with
# cleanup/structure/pdf_export downstream, which nothing here has verified.
_STRUCTURED_PROMPT_ADDENDUM = (
    "Return your transcription as YAML front matter (between --- lines) "
    "describing the page, followed by the transcribed content as Markdown, "
    "preserving tables, headers, and reading order."
)
```

Change `_effective_prompt`'s signature and body:

```python
def _effective_prompt(instruction: str, *, style: str = "raw") -> str:
    """OCR_PROMPT, plus an optional appended domain instruction, plus an
    experimental structured-output addendum when ``style="structured"``.

    Appended, never a replacement: the base prompt's "return only raw text,
    no commentary/labels/formatting" contract must survive regardless of
    ``instruction``, since downstream stages (cleanup, structure) depend on
    it. ``style="structured"`` is an intentional, explicit exception to that
    contract for the purpose of measuring it — see _STRUCTURED_PROMPT_ADDENDUM.
    """
    parts = [OCR_PROMPT]
    if style == "structured":
        parts.append(_STRUCTURED_PROMPT_ADDENDUM)
    instruction = (instruction or "").strip()
    if instruction:
        parts.append(instruction)
    return "\n\n".join(parts)
```

Update both call sites (`_ocr_vision`'s `_call`, and the two sidecar-JSON `"ocr_prompt"` writes in `perform()` from Task 7 Step 6) to pass `style=cfg("ocr_prompt_style", "raw")`.

- [ ] **Step 4: Add the config key**

In `config.py` `_DEFAULTS`, near `ocr_prompt_instruction`:

```python
    # Experimental. "raw" (default) is this app's original prompt contract;
    # "structured" asks for the YAML-front-matter + Markdown shape
    # olmOCR-2-7B-1025 was actually trained toward. See stages/ocr.py's
    # _STRUCTURED_PROMPT_ADDENDUM docstring — do not flip this default
    # without measured results and maintainer sign-off; it changes stage 1's
    # output contract with cleanup/structure/pdf_export.
    "ocr_prompt_style": "raw",
```

Add `"ocr_prompt_style"` to `PERSISTED_KEYS` (config-file/env override only — deliberately **not** added to `web/routers/settings.py`'s `_CONFIG_KEYS` in this task, since exposing an experimental, contract-breaking flag in the main Settings UI is exactly the kind of premature exposure Task 7 Step 0 flags for a much safer field; leave it config-file/`ARTIFICE_OCR_CONFIG`-only for now).

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/artifice-ocr && uv run pytest tests/test_ocr_prompt_style_experiment.py -v`
Expected: PASS, all 4 tests.

- [ ] **Step 6: Run the full fast suite for regressions**

Run: `cd apps/artifice-ocr && uv run pytest tests/ -x -q --ignore=tests/stress --ignore=tests/test_live_model_interop.py --ignore=tests/test_live_ui_model_interop.py`
Expected: all pass, including Task 7's `test_ocr_prompt_instruction.py` (its calls to `_effective_prompt("...")` without `style=` must still work via the new keyword-only default).

- [ ] **Step 7: Commit**

```bash
git add apps/artifice-ocr/src/artifice_ocr/stages/ocr.py apps/artifice-ocr/src/artifice_ocr/config.py apps/artifice-ocr/tests/test_ocr_prompt_style_experiment.py
git commit -m "feat(ocr): add an experimental structured-output prompt style for A/B measurement"
```

**Delegation:**
- `@oracle`: review the diff before commit specifically for contract discipline — confirm nothing downstream (`cleanup.py`, `structure.py`, `pdf_export`) was touched, and that `ocr_prompt_style` defaulting to `"raw"` truly reproduces Task 7's exact prior behavior bit-for-bit.
- `@councillor`: after this task lands, prepare the maintainer-facing summary tying it to Task 5's harness — what a "measure both styles" run looks like once `eval_corpus/` has real pages, and what evidence would justify changing the default. This is a decision brief, not an implementation step; do not flip the default as part of this task under any circumstance.
- `@designer`: Steps 1, 3, 4.
- `@fixer`: Steps 2, 5, 6.

---

## Task order and dependencies

1 → 2 → 3 → 4 → 5 → 6 → 7 → 8, top to bottom, matching this document's numbering. Rationale for the reordering versus the findings doc's own priority table (which put the configurable prompt and the YAML experiment earlier): every "no maintainer decision needed" fix (1-4, 6) lands first since none of them are blocked on anything; the harness (5) lands before the two decision-gated tasks (7, 8) so those decisions can eventually be made from measurement instead of citation, per the findings doc's own closing argument. Task 8 explicitly depends on Task 7's `_effective_prompt` function existing first.

## Status table (fill in as work proceeds)

| Task | Status | Evidence |
|---|---|---|
| 1. Prompt-order comment | not started | — |
| 2. Temperature ladder | not started | — |
| 3. Blank-page short-circuit | not started | — |
| 4. Auto-rotation detection | not started | — |
| 5. Accuracy measurement harness | not started | — |
| 6. Front-matter stripping | not started | — |
| 7. Configurable domain prompt | not started | — |
| 8. Structured-prompt experiment | not started | — |

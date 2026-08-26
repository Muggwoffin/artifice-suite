# Installing Artifice OCR on Windows

The frozen build is the primary route for a user who is not developing the
suite. If you are working on the code, skip to [From a clone](#from-a-clone).

---

## What you get

**Not a single `.exe`.** `artifice-ocr` is frozen **onedir**, so you get a
folder:

```
artifice-ocr/
├── artifice-ocr.exe
└── _internal/          ← Python runtime, fonts, templates, static assets
```

`artifice-ocr.spec` chose onedir over onefile deliberately: files map straight
from disk instead of extracting on every launch, `_internal/` can be inspected
to see exactly what shipped, and — the load-bearing one — onefile extracts to a
*different temp directory each launch*, which breaks `__file__`-relative paths
harder.

**Only Artifice Hub is a true single double-clickable `.exe`** (onefile). It is
also the installer and launcher for the other apps, so it is the one to hand to
someone else.

---

## 1. Build it

There is nothing to download from a Releases page — the repository currently has
**no published releases and no tags**, so the `attach-release` job has nothing to
attach to.

You also cannot build it locally, by design. `build-exe.yml` says why:

> PyInstaller cannot cross-compile. A Windows `.exe` must be built on Windows…
> the maintainer's machine is Windows with WSL, and **uv is deliberately NOT
> installed on the Windows side** — so the only reproducible way to produce a
> Windows build is a Windows runner.

So trigger the workflow:

```bash
gh workflow run build-exe.yml --ref main -f app=artifice-ocr
gh run list --workflow=build-exe.yml --limit 1     # note the run id
```

About two minutes. It builds on `windows-latest` **and** `ubuntu-latest`, with
`fail-fast` off so a Windows failure cannot be hidden by a Linux success.

## 2. Download the artifact

```bash
gh run download <run-id> -n artifice-ocr-Windows
```

Artifacts are named `{app}-{os}`, and are kept for **30 days**.

## 3. Unblock, then extract — in that order

Windows will refuse to run it:

> **Windows protected your PC** — Microsoft Defender SmartScreen prevented an
> unrecognised app from starting.

This is not a judgement about the code. The binary is **unsigned** (no
Authenticode certificate) and anything downloaded from the internet carries a
**Mark of the Web**. SmartScreen has simply never seen this executable.

Clicking **More info → Run anyway** works. But unblock the **zip first**:

```powershell
Unblock-File .\artifice-ocr-Windows.zip
Expand-Archive .\artifice-ocr-Windows.zip
```

(Or right-click the zip → Properties → tick **Unblock**.)

This matters specifically because the bundle is onedir: extract a *blocked* zip
and every extracted file inherits the Mark of the Web — the exe and everything
under `_internal/`. Unblocking the zip first is one action instead of many.

The only way to remove the prompt entirely is an Authenticode code-signing
certificate. Worth knowing the real cost: an OV certificate still has to build
SmartScreen reputation over time and downloads, so it does not help immediately;
an EV certificate gets reputation at once but needs a hardware token and costs
materially more. For a tool distributed to a handful of researchers, "Run
anyway" is a defensible choice.

## 4. Run it

Double-click `artifice-ocr.exe`. The console window is intentional
(`console=True` in the spec) — it shows the server-startup banner. The server
takes port **8765**, falling back to a free port if that is busy and printing
which one it used.

---

## Models

The app is model-agnostic and ships with **no model preselected** — the three
model settings are empty, so it never silently uses something you did not
choose. These are the suite's recommendations, from
`packages/model-harness/src/model_harness/registry.py`:

```bash
ollama pull richardyoung/olmocr2:7b-q8   # OCR
ollama pull aya-expanse:8b               # translation
```

| Model | Role | Min VRAM | Provenance |
|---|---|---|---|
| `richardyoung/olmocr2:7b-q8` | vision | 12 GB | Strict Open Data · Transparent Training · Allen AI Open Science |
| `aya-expanse:8b` | translation | 6 GB | Open Science Lab |
| `aya-expanse:32b` | translation (desktop) | 20 GB | Open Science Lab |

olmOCR-2 wants ~12 GB for full GPU offload and runs on 8 GB with CPU fallback at
reduced throughput. That caveat is enforced by a test, not just written down:
`test_registry.py` asserts a 12 GB ceiling on the LAPTOP tier *and* requires any
entry above 8 GB to document its fallback.

LM Studio works too — load `allenai/olmocr-2-7b` on port `1234`.

### If a page fails with "exceeds the available context size"

The model's context window is smaller than the page needs. Where you fix it
depends on the backend, and the app's error message will tell you which:

- **Ollama** — raise **Settings → Processing → Advanced → Context size**.
- **LM Studio** — LM Studio fixes the context window when it *loads* a model, so
  it cannot be changed from Artifice. Raise it in LM Studio, or
  `lms load <model> --context-length 8192`. The Context size field disables
  itself and says so when the vision backend is LM Studio.
- **Hosted API** — set server-side. Use a model with a larger window.

---

## Your data

`~/.artifice_ocr/` holds `settings.json`, `history.db` and `uploads/`. Deleting
the unzipped folder removes the program and leaves your data untouched.

---

## From a clone

For working on the suite itself:

```bash
git clone https://github.com/Muggwoffin/artifice-suite.git
cd artifice-suite
bash scripts/install.sh artifice-ocr
```

PowerShell: `.\scripts\install.ps1 artifice-ocr`

Installs `uv` if missing, then `uv tool install --editable` against the local
workspace so the app stays linked to your clone. Uninstall with
`bash scripts/uninstall.sh artifice-ocr` — it removes the program and leaves
your data, printing the path and warning that it may contain an API key.

> Do not run `uv` from the Windows side against the WSL checkout. It clobbers the
> Linux `.venv`; repairing it means `uv sync --extra all` from inside WSL.

---

## Optional: Tropy

- **Browse project** requires `tropy_live_browse_enabled`.
- **Write back** requires `tropy_writeback_enabled`, which is **off by default**
  — it edits your research database, so it is never on unless you turn it on.

Write-back only applies to photos added through **Browse project**. A JSON-LD
import can never be written back, because that format carries no numeric photo
id. The modal says so rather than reporting an empty result.

# Contributing to Artifice Suite

Thanks for considering a contribution. This project follows the
[Contributor Covenant](CODE_OF_CONDUCT.md); by participating you agree to
abide by it.

## Getting set up

The suite is a [uv](https://docs.astral.sh/uv/) workspace of four
independent apps (`apps/artifice-ocr`, `apps/artifice-draft`,
`apps/artifice-graph`, `apps/artifice-transcribe`) plus a shared
`packages/model-harness` package.

```bash
git clone https://github.com/Muggwoffin/artifice-suite.git
cd artifice-suite
uv sync --extra all      # installs all four apps + model-harness, editable
```

To work on a single app instead:

```bash
pip install -e apps/artifice-ocr        # swap in the app you're changing
pip install -e "apps/artifice-ocr[web]" # include its optional web extra, if relevant
```

Each app also documents its own setup and entry points in its own
`README.md` and `CLAUDE.md`.

### Developer tooling

Beyond `uv` and Python, a few command-line tools are assumed by the repo's
scripts and by day-to-day work. On Debian/Ubuntu (including WSL2):

```bash
sudo apt install -y ripgrep jq brotli shellcheck gitleaks ffmpeg
```

| Tool | Why |
|---|---|
| `ripgrep` | Assumed by tooling and contributors; `grep` works but is slower on this tree |
| `gitleaks` | Required by the Zero Secrets Policy — run it before opening a PR |
| `brotli` | Needed to compress vendored web fonts to `.woff2`; without it they ship as `.ttf` at roughly twice the size |
| `shellcheck` | `scripts/*.sh` are real systems code and should be linted |
| `jq` | Convenience for the JSON-heavy pipeline output |
| `ffmpeg` | Audio decoding for `artifice-transcribe` (Whisper / Parakeet / pyannote) |

All six are present in the maintainer's WSL2 environment as of 2026-07-28
(`rg` 15.1.0, `ffmpeg` 8.0.1, `brotli` 1.2.0, `jq` 1.8.1, `shellcheck` 0.11.0).
Contributors setting up fresh still need the `apt install` line above.

If you installed `uv` with the standalone installer it lands in
`~/.local/bin`, which **is not on the `PATH` of a non-login shell** — so
`bash some-script.sh` will fail with `uv: command not found` even though your
interactive terminal is fine. Symlink it once:

```bash
sudo ln -s "$HOME/.local/bin/uv" /usr/local/bin/uv
```

`ffmpeg` is required only by `artifice-transcribe`, and it pulls ~500 MB — drop
it from the `apt` line if you are not working on that app. Note that it must be
the **Linux** package: a Windows `ffmpeg.exe` on the `PATH` is not usable from
WSL, which `apps/artifice-transcribe/HANDOFF.md` records as a past stumble.

### Docker, and the Firecrawl verification instance

Install Docker **natively inside WSL**, not via Docker Desktop's WSL
integration:

```bash
sudo apt install -y docker.io docker-compose-v2
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"   # then start a new session
```

A `docker` that resolves under `/mnt/c/...` is Docker Desktop's Windows shim
reached across the interop boundary — the same class of trap that made the
`opencode` npm shim block forever. `scripts/firecrawl.sh` refuses to run against
it for that reason.

Docker is only needed if you are working on agent tooling. It backs a
self-hosted [Firecrawl](https://github.com/firecrawl/firecrawl) instance that
lets OpenCode sub-agents fetch locally-served app pages for structural
verification. Manage it with `scripts/firecrawl.sh {up|down|status|prune}`. The
instance is unauthenticated and therefore bound to `127.0.0.1` only — never
publish it on `0.0.0.0`.

## Running tests

Each app has its own pytest suite. Run it from inside the app directory:

```bash
cd apps/artifice-ocr   # or artifice-draft / artifice-graph / artifice-transcribe
pytest
```

Please add or update tests for any behavioral change, and confirm the
existing suite for the app(s) you touched still passes before opening a PR.

## Line endings

The repository's line-ending policy lives in [`.gitattributes`](.gitattributes)
at the repo root, and it is the source of truth — not each machine's
`core.autocrlf`. The default rule is `* text=auto eol=lf`: text files are
stored as LF in the repository blob store **and** checked out as LF in the
working tree on every platform (Windows-native, WSL2, and macOS alike),
so the working-tree bytes are identical everywhere and `git status` can no
longer report different things in different shells.

Forcing LF in the working tree — not just in the stored blobs — is the whole
point. This project is developed across Windows PowerShell, WSL2 Ubuntu, and
macOS; without this rule, the same commit read as "clean" in PowerShell (where
Windows git has `core.autocrlf=true`) and "65 files modified" in WSL (where
`core.autocrlf` is unset). That contradiction has already caused one wrong
discard.

Intentional exceptions (every one of these is grounded in a file type that
actually exists in the tree, and matches a rule in `.gitattributes`):

- **Shell scripts** (`*.sh`) are forced LF. A CRLF shebang produces
  `bad interpreter: /bin/bash^M` under WSL2 / macOS / Linux — a confusing,
  silent failure. (One is present: `scripts/smoke-test-agents.sh`.)
- **Windows batch** (`*.bat`, `*.cmd`) is forced CRLF. `cmd.exe` historically
  expects CRLF; labels and `goto` can misbehave on LF-only `.bat`. These
  files only ever run on Windows, so CRLF is the correct, targeted exception.
- **PowerShell** (`*.ps1`) and **Python launchers** (`*.pyw`) are **not**
  excepted — both run cleanly with LF — so the default LF rule governs them.
- **Images** (`*.png`, `*.jpg`, …), **icons** (`*.ico`), **fonts** (`*.ttf`,
  `*.otf`, `*.woff*`), **PDFs**, and **audio / model fixtures** are marked
  `binary` (`-text -diff`): never normalised, never textual-diffed. This is
  safety-critical — a CRLF conversion of a tensor or audio file silently
  corrupts it.

### Set this once on every machine

With `.gitattributes` declaring the policy in-repo, the per-machine
`core.autocrlf` setting is largely redundant for tracked files — the
explicit `eol=lf` / `eol=crlf` attributes override it. But set it to `false`
on **every** platform anyway, so any untracked or newly-added file can't be
silently converted behind the rules and every checkout stays identical:

```bash
# Windows-native (PowerShell / Git Bash), WSL2 Ubuntu, and macOS — identical:
git config --global core.autocrlf false
```

Do **not** re-enable `core.autocrlf=true` — that is Windows git's default and
is exactly what masked this project's CRLF/LF mismatch.

### Editor settings

Configure your editor to write LF for this repo and to leave existing LF
alone:

- **VS Code**: `"files.eol": "\n"` in the workspace settings.
- **JetBrains (PyCharm / IntelliJ)**: Settings → Editor → Code Style →
  Line separator: `LF` (`.idea/` is gitignored).
- **Windows Notepad / Notepad++**: Notepad handles LF since Windows 10 1809;
  in Notepad++ set *Edit → EOL Conversion → Unix (LF)* and
  *Settings → Preferences → New Document → Unix*.

### One-time normalisation — maintainer only, run when the tree is clean

The committed blobs in this repository are already LF, but the working tree
contains a layer of CRLF introduced before this policy existed. The policy
above governs *future* writes; it does **not** rewrite what is already on
disk. Normalising the existing files rewrites line endings across the whole
tree, so it must be its own commit and must **never** be run while another
agent or branch has uncommitted work in flight. From the repo root, once
everything else is committed:

```bash
# 1. Commit the policy itself first (if not already committed):
git add .gitattributes CONTRIBUTING.md
git commit -m "chore: add line-ending policy (.gitattributes)"

# 2. Confirm the tree is otherwise clean:
git status

# 3. Re-apply the new attributes to every tracked file, verify, then commit:
git add --renormalize .
git status            # expect only EOL-only changes; verify before committing
git commit -m "chore: normalise line endings to LF per .gitattributes"
```

After step 3, every tracked text file is LF in both the blob store and the
working tree on all platforms, and the phantom-diff noise is gone for good.

> **This normalisation has NOT been performed.** It is left to the maintainer
> to run once, at a quiet moment, after confirming the tree is clean. Do not
> run `git add --renormalize`, `dos2unix`, or any bulk EOL rewrite on a dirty
> tree — it will sweep up other people's uncommitted work into a meaningless
> whole-file diff.

### Note on the per-app `.gitattributes` files

`apps/artifice-ocr/.gitattributes` and `apps/artifice-transcribe/.gitattributes`
each contain a legacy bare `* text=auto` line with no `eol=`. Under git's
attribute resolution, a later rule that does not mention `eol` does not unset
an `eol=` set by an earlier (root) rule, so the canonical `eol=lf` from the
root file still governs files beneath those two apps. The two legacy files
are redundant and may be deleted for clarity, but leaving them in place is
not currently harmful.

## Project conventions

1. **Structured model interactions only.** Any new feature or model
   connector must go through `packages/model-harness`'s schema-validated
   call shape, not a freeform chat wrapper. Model output is structured data, not conversation. This follows from Joseph Weizenbaum's 1964-67 study of the harmful implications of computer-human chat interaction.
2. **Design system compliance.** Frontend/UI contributions must follow
   `Design_Philosophy.md` (The New Masses design system) — its color
   tokens, typography, and stated anti-patterns apply to every app.
3. **Local-first, no _silent_ network calls.** The rule is not "never touch the
   network" — the apps talk to cloud models and map servers when the user asks
   them to. The rule is that the user is never surprised. Every outbound request
   falls into exactly one of three tiers:

   | Tier | Rule | Examples |
   |---|---|---|
   | **Never** | Application assets and anything the user did not ask for | Web fonts, JS libraries, telemetry, analytics, update checks, crash reporting |
   | **Only on explicit user action, disclosed before the action** | The user clicks something, having been told what it will contact | OpenStreetMap tiles, Nominatim geocoding |
   | **User's own credentials, user's own endpoint** | BYOM — the user supplied the key and chose the host | OpenAI/Anthropic/any cloud model API |

   **Tier 1 is the one that gets violated by accident**, because it looks like a
   styling or convenience decision rather than a network one. Two real cases, both
   fixed: `artifice-graph` loaded Leaflet from `unpkg.com` on every Library page
   view whether or not the map was opened (commit `477820a`), and `ocr`, `draft`
   and `transcribe` all loaded fonts from `fonts.googleapis.com` on every page
   load. SRI hashes do not help here — they protect integrity, not privacy; the
   CDN still saw the user's IP and the timing of every view. **Vendor the asset.**

   **Tier 2 is the pattern to copy.** `artifice-graph`'s Library page is the
   reference implementation: the map does not load on page view, there is a
   "Load Map" button, and the text beside it reads *"Loading the map contacts
   openstreetmap.org to fetch map tiles"* — disclosed **before** the click, not
   in a privacy policy. See `web/templates/library.html:213-218`.

   Never transmit user documents, audio, transcripts, or API keys anywhere the
   user did not explicitly direct. See `.opencode/agents/security-auditor.md` for
   the specific checks this project holds itself to.

   This matters more than it would for most software: the apps are being packaged
   as desktop `.exe` / `.dmg` builds wrapping a local server in a native webview.
   A user who sees a firewall prompt, or who discovers an unexpected outbound
   connection, reasonably concludes the local-first promise was never true.
4. **Directory parity.** Apps share the same internal layout
   (`src/<package>/`, `tests/`, `pyproject.toml`, `Dockerfile`,
   `README.md`). New apps or major restructuring should preserve that
   parity.

## Frontend conventions

These are process rules for contributors. How the interface should *look* is governed by
`Design_Philosophy.md`, which is the single source of truth for tokens, typography, spacing and
component appearance — including the icon rules in its Components section. Nothing below overrides
it.

### Templates

- FastAPI + Jinja2. Every page extends `templates/base.html` and fills `{% block title %}`,
  `{% block head %}`, `{% block content %}` and `{% block scripts %}`.
- Every CSS and JS link carries the `?v={{ asset_v }}` cache-buster. Without it a token change
  ships to a browser that keeps serving the old stylesheet from cache.
- Theme and reduced-motion state are stamped on `<html>` by middleware as `data-theme` and
  `data-reduce-motion`. Read them from the attribute; never re-detect the OS preference in
  page-level JavaScript, or the explicit toggle and the OS setting will disagree.
- `[hidden] { display: none !important; }` is declared globally. Hide things with the `hidden`
  attribute rather than a bespoke `.is-hidden` class per component.

### JavaScript: vanilla, no build step

**The rule is no build step and no framework.** Modern JavaScript syntax is fine — `let`, `const`,
arrow functions, template literals and classes all run natively in every browser this project
targets, and require no tooling whatsoever. Write JavaScript that a browser can execute as-is.

> **Corrected 2026-07-28.** This section previously required ES5 and claimed the rule held
> "exactly: **zero** occurrences of `let`, `const` or `=>`". That was measurably false.
> Actual counts across the apps' own JavaScript:
>
> | App | `let` | `const` | `=>` |
> |---|---|---|---|
> | `artifice-ocr` | 54 | 445 | 213 |
> | `artifice-transcribe` | 29 | 276 | 106 |
> | `artifice-draft` | 6 | 65 | 44 |
> | `artifice-graph` | 0 | 0 | 0 |
>
> 17 of 19 app JavaScript files already used modern syntax. The document described a discipline
> that existed in one app out of four, and forbidding `const` while 786 of them shipped made the
> whole section easy to dismiss — including the part that actually matters.

What the rule protects, and why it is worth keeping:

- **The install promise.** A build step means a `node_modules` tree, a lockfile and a compile pass
  standing between the source and the running app. A researcher must be able to clone the
  repository, run `uv sync`, and have working software on a machine with no Node toolchain at all.
  This gets *more* important, not less, as the apps are packaged into `.exe` / `.dmg` builds —
  bundling a Python runtime and a Node build pipeline into one cross-platform artefact is
  substantially harder than bundling Python alone.
- **Auditability.** `security-auditor` reviews the code that actually runs. Once the shipped
  artefact is compiled output, reading the source no longer tells you what executes. For software
  handling sensitive archival material — and for a JOSS submission where reviewers read the
  source — that is not a small loss.
- **Fit.** These are harnesses: forms, status, logs, progress. Nothing here needs a virtual DOM,
  and `artifice-graph` implements the most sophisticated UI in the suite in zero-dependency
  vanilla JavaScript.

**On `design-system/components/`.** Those 18 components ship as `.jsx` with React imports. They
**cannot be imported** — JSX is not JavaScript, and a browser cannot execute it without a compile
step. Treat them as what they are: a **specification**. Each component ships a `.prompt.md`
describing its purpose, variants and states in prose, with the `.jsx` as an unambiguous reference
for exact spacing, colour and hover behaviour. Read them; implement the equivalent in plain
JavaScript. Do not add React, and do not add a bundler to consume them.

If you believe a change genuinely requires a build step, raise it as a design question first. Do
not introduce it incidentally inside a feature PR.

### File and naming conventions

| Path | Purpose |
|---|---|
| `packages/shared-ui/tokens.css` | **All** design tokens. Canonical, and the only copy — served over the app's `/shared` mount, never mirrored into an app |
| `packages/shared-ui/fonts.css` | `@font-face` declarations for the locally vendored fonts |
| `packages/shared-ui/fonts/` | The font files themselves, with their OFL licences |
| `<app>/web/static/app.css` | Base chrome, shared components, reset, utilities |
| `<app>/web/static/{feature}.css` | Page- or feature-specific styles |
| `<app>/web/static/{feature}.js` | Per-page behaviour, IIFE-wrapped |
| `<app>/web/templates/{feature}.html` | One Jinja2 template per route |

App-local colours that are genuinely domain vocabulary rather than suite identity — the entity-type
accents in `artifice-graph`, for example — live in their own app-local stylesheet such as
`entity-colors.css`, loaded after the shared tokens. **Do not reintroduce a per-app `tokens.css`.**

## Submitting a pull request

- Keep PRs focused — one app or one concern per PR where practical.
- Describe what changed and why in the PR description; link any relevant
  issue.
- Make sure `pytest` passes for every app your change touches.
- If your change affects a Dockerfile or `docker-compose.yml`, confirm
  `docker-compose build` succeeds for the affected service.

## Reporting bugs or requesting features

Open a GitHub issue with enough detail to reproduce the problem (app name,
OS, Python version, model backend if relevant) or to understand the
requested feature's motivation.
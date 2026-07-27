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
3. **Local-first, no silent network calls.** Contributions must not
   introduce telemetry, analytics, or any transmission of user documents,
   audio, or BYO model API keys off the local machine. See
   `.claude/rules/security-auditor.md` for the specific checks this
   project holds itself to.
4. **Directory parity.** Apps share the same internal layout
   (`src/<package>/`, `tests/`, `pyproject.toml`, `Dockerfile`,
   `README.md`). New apps or major restructuring should preserve that
   parity.

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
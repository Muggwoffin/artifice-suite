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

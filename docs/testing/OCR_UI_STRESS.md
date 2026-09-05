<!--
SPDX-FileCopyrightText: 2026 Maurice Casey
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# OCR interface stress gate

The blocking profile drives the real FastAPI application with Chromium and
runs a Hypothesis queue/review state machine. It is deterministic and does not
contact a model server:

```bash
uv sync --group dev --extra ocr-web
uv run playwright install chromium
scripts/stress/run-ui-stress.sh
```

On a fresh Linux/WSL installation, use `uv run playwright install --with-deps
chromium` to install Chromium's required system libraries as well (this may
request sudo). Hosted CI uses this form.

The PR profile runs eight fixed seeds with 30 browser actions each and 50
bounded state-machine examples. Replay a failure exactly with the seed shown in
the test name or artifact directory:

```bash
scripts/stress/run-ui-stress.sh --replay 104729
```

Failures are written under `.artifacts/ui-stress/seed-<seed>/`: the action
sequence, DOM, screenshot, browser/server errors, and a Playwright `trace.zip`.
Open the trace with `uv run playwright show-trace <path>`.

The scheduled advisory profile expands coverage without making PR latency
unbounded:

```bash
scripts/stress/run-ui-stress.sh --scheduled
```

It runs 50 seeds with 75 actions each. The scheduled GitHub workflow uploads
the same replay artifacts.

The release gate is separate because it intentionally requires desktop Tropy
and real local inference servers. It auto-detects endpoints across WSL, runs
exactly one visible-interface OCR job through Ollama and one through LM Studio,
then browses and round-trips an isolated real Tropy project:

```bash
bash scripts/interop/run-live-release-gate.sh --local-only
```

Use `--publish-status` on the commit that will be built. OCR packaging refuses
to proceed without a successful `live-interop/release-gate` status. Set
`ARTIFICE_LIVE_HEADED=1` when manually observing Tropy; the default private X
server is more deterministic under WSL. If Xvfb is unavailable, the gate uses
an existing graphical display; it fails explicitly if neither is available.

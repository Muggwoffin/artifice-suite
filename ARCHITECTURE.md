# Artifice Suite Architecture

## Monorepo Layout

The Artifice Suite is structured as a `uv` workspace monorepo enforcing strict boundaries between presentation, core logic, and model connectors. Use `uv sync --extra all` and `uv run <command>`; there are no Node or npm scripts.

```
artifice-suite/
├── apps/                 # OCR, Draft, Graph, Transcribe — and Hub, the launcher
├── packages/             # shared-ui, model-harness, secure-io
├── docs/                 # Guides, specs, and archive/ for spent working docs
└── .opencode/agents/     # Sub-agent definitions (the whole fleet)
```

**Five apps, not four.** `apps/artifice-hub` is a native GUI launcher that installs, updates and
launches the other four. It is deliberately **frozen-only** — no Dockerfile, no PyPI publish, no
`uv tool install` — which is why it is absent from every *publishing* path and easy to miss in a
survey. It is still in scope for anything version-shaped: `scripts/check-release-consistency.py`
globs `apps/*/pyproject.toml`, so the Hub is gated whether or not it ships.

**`packages/core-types` does not exist** and has not for some time; the third package is
`secure-io`. An install command in `apps/artifice-ocr/README.md` named it until 2026-08-26 and
failed outright for anyone who ran it.

**`.claude/agents/` is empty and must stay that way.** All seven agents are defined in
`.opencode/agents/`; a definition in both runtimes shadows the other when the orchestrator
dispatches by name, and `scripts/smoke-test-agents.sh` asserts this in both directions. Nothing
belongs in `.claude/rules/` either — files there load as project-wide instructions into *every*
session instead of scoping to a single agent.

## Core Abstraction: `packages/model-harness`

`packages/model-harness` defines the structured-output contract and its single implementation:

- **`contract.py`** — the protocols (`StructuredRequest`, `HarnessResult`, `EndpointRejected`) and the
  degradation ladder. A response schema is a *required* argument; providers declare their strongest
  `StructuredOutputMode`; the ladder walks from most-structured to least and records which rung
  produced the result; the bottom rung raises `StructuredOutputUnsupported` rather than returning prose.
- **`endpoint_policy.py`** — the SSRF rule. Single owner of the endpoint allowlist; refuses
  link-local outright and checks it *before* any opt-in; loopback and private addresses are allowed,
  public requires `ARTIFICE_ALLOW_PUBLIC_MODELS`.
- **`openai_adapter.py`** — the one adapter, implementing `ModelProvider` against the OpenAI API
  compatible endpoint shape.
- **`driver.py`** — `run_structured`, the function an app calls. Takes a `StructuredRequest`, runs
  the degradation ladder, validates the response against the declared schema, returns a
  `HarnessResult`.

265 tests pass (re-measured 2026-08-26; this said 90 for some time).

The other two packages:

- **`packages/shared-ui`** — design tokens, web fonts, the native file dialog, server bootstrap,
  and the defensive I/O helpers every app shares: `path_validation.py` (allowed roots, filename
  sanitisation) and `uploads.py` (a size cap that fails *during* the read). It deliberately depends
  on `platformdirs` and `uvicorn` only — **no web framework**, so its helpers raise domain errors
  and each app's web layer translates them. Do not add `fastapi` or `starlette` to it.
- **`packages/secure-io`** — hardened file and path I/O, including legacy-data migration.

The contract specifies that all model interactions must pass through `packages/model-harness` to
prevent the ELIZA effect and ensure deterministic outputs.

- **OCR**: Accepts Ollama, LM Studio, or generic API endpoints via `_backend.py`. No structured output
  stage exists — every LLM stage returns `str`. Receives the endpoint policy via
  `model_harness.endpoint_policy`, but `run_structured` is not called.
- **Draft**: Accepts Ollama, LM Studio, generic API **and Anthropic** endpoints. Both LLM paths route
  through `run_structured` — the editing path (`a4f51d4`) and the style-guide scraper (`a26d1bf`) —
  and both resolve endpoints through the policy. Draft is the only app using the Anthropic adapter,
  and so the only one exercising the ladder's mode-gap skipping.
- **Graph**: Accepts Ollama, LM Studio, or generic API endpoints. The extraction path routes through
  `run_structured` (`5aa8619`). Both web and extraction paths import the endpoint policy.
- **Transcribe**: Integrates Whisper / Parakeet speech-to-text with pyannote speaker diarization pipelines.
  Both web and inference paths import the endpoint policy; the inference path is not yet ported.

## Cross-Platform & Hardware Architecture

The suite supports Linux, Windows, and macOS with robust hardware acceleration:
- **NVIDIA CUDA**: Supported natively on Linux and Windows via container GPU passthrough (`nvidia-container-toolkit`) or native execution.
- **Apple Silicon Metal & MPS**: On macOS, LLM inference engines (Ollama, LM Studio) run **natively on the host** to utilize Apple Metal Performance Shaders (MPS) and Unified Memory. Docker containers bridge to the host via `http://host.docker.internal`.
- **Dynamic Device Mapping**: Python modules automatically resolve execution devices (`cuda` $\rightarrow$ `mps` $\rightarrow$ `cpu`).

## Design System: The New Masses (`Design_Philosophy.md`)

All UI components and presentation layers across the suite must strictly adhere to `Design_Philosophy.md`. This specifies paper-and-ink aesthetics, warm color tokens, fluid serif typography, restrained motion, and explicit anti-patterns to avoid AI visual tropes.

## Modular Parity

All applications in `apps/` maintain identical internal folder layouts (`src/artifice_<slug>/`,
`tests/`, `Dockerfile`, `pyproject.toml`, `README.md`) to allow seamless refactoring and
multi-agent contribution.

**There is no `package.json` anywhere, and no Node toolchain.** This list named one until
2026-08-26; nothing in the repository has ever had one. Every frontend is vanilla JS with Jinja
templates or static HTML.

**Web assets live inside the installable package** — `apps/<app>/src/artifice_<slug>/web/static/`,
never at the app root. Assets outside the package are excluded from a wheel and can only be found
by a path relative to the current working directory, which breaks the moment the server starts
from anywhere else. Resolve packaged assets with `importlib.resources`, not
`Path(__file__).parent.parent`.

The Hub is the one app with no `templates/` tree — it serves static HTML. Anything done "in every
app's `base.html`" silently skips it.

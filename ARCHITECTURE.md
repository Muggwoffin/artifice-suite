# Artifice Suite Architecture

## Monorepo Layout

The Artifice Suite is structured as a `uv` workspace monorepo enforcing strict boundaries between presentation, core logic, and model connectors. Use `uv sync --extra all` and `uv run <command>`; there are no Node or npm scripts.

```
artifice-suite/
├── apps/                 # Desktop applications (OCR, Draft, Graph, Transcribe)
├── packages/             # Shared packages (shared-ui, model-harness, core-types)
├── .opencode/agents/     # OpenCode sub-agent definitions
└── .claude/agents/       # Claude Code sub-agent definitions
```

Agent definitions live in `agents/` directories in both runtimes. Nothing belongs in
`.claude/rules/` — files there load as project-wide instructions into every session instead of
scoping to a single agent.

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

90 tests pass. The web layers of `artifice-graph` and `artifice-transcribe` import
`model_harness.contract` and `model_harness.endpoint_policy`; no extraction path yet calls
`run_structured`.

The contract specifies that all model interactions must pass through `packages/model-harness` to
prevent the ELIZA effect and ensure deterministic outputs. 
- **OCR, Draft, Graph**: Accept Ollama, LM Studio, or generic API endpoints, enforcing strict JSON Schema validation.
- **Transcribe**: Integrates Whisper / Parakeet speech-to-text with pyannote speaker diarization pipelines.

## Cross-Platform & Hardware Architecture

The suite supports Linux, Windows, and macOS with robust hardware acceleration:
- **NVIDIA CUDA**: Supported natively on Linux and Windows via container GPU passthrough (`nvidia-container-toolkit`) or native execution.
- **Apple Silicon Metal & MPS**: On macOS, LLM inference engines (Ollama, LM Studio) run **natively on the host** to utilize Apple Metal Performance Shaders (MPS) and Unified Memory. Docker containers bridge to the host via `http://host.docker.internal`.
- **Dynamic Device Mapping**: Python modules automatically resolve execution devices (`cuda` $\rightarrow$ `mps` $\rightarrow$ `cpu`).

## Design System: The New Masses (`Design_Philosophy.md`)

All UI components and presentation layers across the suite must strictly adhere to `Design_Philosophy.md`. This specifies paper-and-ink aesthetics, warm color tokens, fluid serif typography, restrained motion, and explicit anti-patterns to avoid AI visual tropes.

## Modular Parity

All applications in `apps/` maintain identical internal folder layouts (`src/`, `tests/`, `Dockerfile`, `package.json`, `README.md`) to allow seamless refactoring and multi-agent contribution.

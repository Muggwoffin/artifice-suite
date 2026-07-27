# Artifice Suite Architecture

## Monorepo Layout

The Artifice Suite is structured as a pnpm workspace monorepo enforcing strict boundaries between presentation, core logic, and model connectors.

```
artifice-suite/
├── apps/                 # Desktop applications (OCR, Draft, Graph, Transcribe)
├── packages/             # Shared packages (shared-ui, model-harness, core-types)
├── .opencode/agents/     # OpenCode sub-agent definitions
└── .claude/rules/        # Claude Code runtime rules
```

## Core Abstraction: `packages/model-harness`

To prevent the ELIZA effect and ensure deterministic outputs, all model interactions must pass through `packages/model-harness`. 
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

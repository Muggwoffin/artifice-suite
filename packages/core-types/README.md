# core-types

Shared Pydantic data schemas for the Artifice Suite. These are JSON-serializable
Python models, usable directly by any app's FastAPI web layer (Pydantic
models serialize to JSON automatically) without a separate frontend type
system.

Currently defines:

- `ProcessingStatus` — a shared job lifecycle enum (`queued`, `running`,
  `succeeded`, `failed`)
- `PipelineProgress` — a single progress update (`status`, `percentage`,
  `message`)

No app currently imports from this package — each of `artifice-ocr`,
`artifice-draft`, `artifice-graph`, and `artifice-transcribe` still defines
its own job/progress types. Adopting these shared types in an app (or adding
new shared schemas here) is a deliberate follow-up, not done as part of
introducing this package.

Install into an app's environment with:

```
pip install -e ../../packages/core-types
```

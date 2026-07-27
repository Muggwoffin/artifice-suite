# Artifice Suite

[![DOI](https://zenodo.org/badge/1313540750.svg)](https://doi.org/10.5281/zenodo.21621935)]

A collection of local-first, bring-your-own-model (BYOM) desktop tools designed around rigid software harnesses rather than conversational AI interfaces.

## AI for Humanities Research beyond the 'ELIZA Effect'

This software follows from the insight of Joseph Weizenbaum, creator of the first chatbot ELIZA, that '‘extremely short exposures to a relatively simple computer program could induce powerful delusional thinking in quite normal people". To avoid such negative impacts of AI use while following 'minimal computing' and data privacy best practice, this software defaults to a local-first and open source approach where all interactions with models are deterministic rather than conversation.

## Design System

All user interfaces across the suite adhere to **The New Masses Design System** (`Design_Philosophy.md`), featuring paper-and-ink aesthetics, warm editorial palettes, serif typography, and restrained motion.

## Applications Overview

1. **`apps/artifice-ocr`**: Local-first OCR processing with structured JSON extraction (supports Ollama, LM Studio, or generic API).
2. **`apps/artifice-draft`**: Local-first copy editing harness for structural transformations (supports Ollama, LM Studio, or generic API).
3. **`apps/artifice-graph`**: Knowledge graph creator extracting entities and relationships into typed JSON (supports Ollama, LM Studio, or generic API).
4. **`apps/artifice-transcribe`**: Oral history transcription utilizing Whisper models or NVIDIA NeMo Parakeet, coupled with pyannote diarization via Hugging Face.

## Quick-Start Guide (Bring Your Own Model)

- **Install**: `uv sync --extra all` installs all four apps plus `packages/model-harness` in editable mode. To work on a single app: `pip install -e apps/artifice-ocr` (swap in the app you need).
- **Local Execution**: Ensure Ollama is running at `http://localhost:11434` or LM Studio at `http://localhost:1234/v1`.
- **Cloud Execution**: Configure your preferred provider API key (OpenAI, Anthropic, OpenRouter, etc.) in the environment or app settings.
- **Docker Compose**: Run `docker-compose up` to start all app containers with local bridging.

## macOS & Apple Silicon Support

The Artifice Suite runs natively on macOS (Apple Silicon M1/M2/M3/M4 and Intel Macs):
- **Metal GPU Acceleration**: Run model engines (**Ollama** and **LM Studio**) **natively on the macOS host** to leverage Apple Silicon Metal GPU acceleration and Unified Memory.
- **Docker Networking**: The provided `docker-compose.yml` configures containers to connect to host-bound models via `http://host.docker.internal:11434` (Ollama) or `http://host.docker.internal:1234/v1` (LM Studio).
- **Device Agnostic Execution**: Python components dynamically target `cuda` $\rightarrow$ `mps` (Apple Metal Performance Shaders) $\rightarrow$ `cpu`. For `artifice-transcribe`, set `PYTORCH_ENABLE_MPS_FALLBACK=1` on macOS if required.

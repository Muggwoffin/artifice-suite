<img width="960" height="540" alt="Artifice Logo copy" src="https://github.com/user-attachments/assets/6f7262b1-a9e5-4c2d-bacd-1546b3eba557" />



[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.21621935-blue.svg)](https://doi.org/10.5281/zenodo.21621935)

# OCR + Copy Editing + Transcription + Data Visualisation

A collection of local-first and open-source tools that place a user-friendly interface on top of AI models. Buttons, forms, and human-in-the-loop checks create predictable results rather than open-ended chatbot surprises. Designed from the ground up for digital humanities workflows.

## AI for Humanities Research:

This software follows from the insight of Joseph Weizenbaum, creator of the first chatbot ELIZA, that "extremely short exposures to a relatively simple computer program could induce powerful delusional thinking in quite normal people".

Artifice does not want to sell you anything. It doesn't want to be your friend. It's a suite of tools that deploys AI to improve research workflows in specific cases: OCR, copy editing, transcribing oral histories and creating data visualisations.

### Bring Your Own Model
Use your model choice, whether it's a model running on your computer, a cloud-based model or models that your university hosts on a local network. 

### Data Privacy
Concerned about data privacy? Use a model that runs entirely on your machine. Artifice works with any model you can run on your machine and can connect to any remotely hosted model you trust. Artifice never connects to the internet unless you permit it. 

### Digital Sovereignty
Artifice is designed from the ground-up to work with open models, allowing researchers to reduce their dependency on corporations for digital tools and data storage.

### Minimal Computing
Artifice is designed to run on your machine, with minimal computing requirements. Use only the models capable of running on your machine, and only the models you trust. Artifice never uses an LLM where a straightforward script can achieve the same result.

## Design System

All user interfaces across the suite adhere to **The New Masses Design System** (`Design_Philosophy.md`), featuring paper-and-ink aesthetics, warm editorial palettes, serif typography, and restrained motion.

## Applications Overview

1. **`apps/artifice-ocr`**: Local-first OCR processing that allows you to edit raw OCR output, perform text cleanup and translate documents in one workflow. Integrates with Tropy so you can import entire folders of your archival photographs and then write back the transcriptions into your Tropy library.
2. **`apps/artifice-draft`**: Local-first copy editing harness for structural transformations (supports Ollama, LM Studio, or generic API). Copy and paste a journal style guide for precise edits. The app outputs a track-changed Word file: you veto any change.
3. **`apps/artifice-graph`**: Knowledge graph creator extracting entities and relationships into a variety of formats. 
4. **`apps/artifice-transcribe`**: Oral history transcription utilising a Speech to Text model of your choice. Couple with pyannote diarization via Hugging Face to create a transcript that labels and seperates speakers. Transcribe, edit and make your Oral History transcripts OHMS and TEI compliant in one app.

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

# OCR Pipeline for Historical Documents

A local-first pipeline for processing, cleaning, and translating historical documents using LM Studio and Ollama.

## Prerequisites

- Python 3.11+
- [LM Studio](https://lmstudio.ai) running locally with `allenai/olmocr-2-7b` loaded
- [Ollama](https://ollama.com) running locally
- Pull the cleanup model: `ollama pull gemma4:12b`
- Pull the translation model: `ollama pull translategemma:4b`

## Structure

- `src/ocr_pipeline` — Core logic and stages.
- `configs/` — Configuration files.
- `prompts/` — Prompt templates for LLM operations.

## Installation

```bash
pip install -e .
```

## Usage

### CLI

```bash
# OCR stage (requires LM Studio with olmocr-2-7b)
ocr_pipeline ocr path/to/image.png

# Cleanup stage (requires Ollama)
ocr_pipeline cleanup output/raw_ocr/text/<filename>.txt

# Translation stage (requires Ollama)
ocr_pipeline translate output/cleaned/text/<filename>.txt

# Full pipeline: OCR -> Cleanup -> Translate
ocr_pipeline pipeline path/to/image.png

# Skip translation
ocr_pipeline pipeline path/to/image.png --skip-translate
```

Supported input formats: `.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`

### GUI

```bash
ocr_pipeline_gui
```

A minimal drag-and-drop interface for running the pipeline on image files.

### Programmatic

```python
from src.ocr_pipeline.pipeline import run_pipeline

result = run_pipeline("path/to/image.png", output_dir="output")
# result = {"raw": {...}, "cleaned": {...}, "translated": {...}}
```

## Output Structure

```
output/
  raw_ocr/
    text/<stem>.txt
    json/<stem>.json
  cleaned/
    text/<stem>.txt
    json/<stem>.json
  translated/
    text/<stem>.txt
    json/<stem>.json
```

## Models

| Stage      | Model                    | Engine     |
|------------|--------------------------|------------|
| OCR        | allenai/olmocr-2-7b      | LM Studio  |
| Cleanup    | gemma4:12b               | Ollama     |
| Translate  | translategemma:4b        | Ollama     |

Handoff: Prompt 5 — Translation Stage + Known Limitations
=========================================================

Read this file before writing any code. It describes the exact state of the
project as of the end of Prompt 4, what you need to build, and the known
limitations to fix.


PROJECT STATE (end of Prompt 4)
-------------------------------

Three pipeline stages exist: OCR, Cleanup, Translation (stub).

  Stage      Model                      Status
  -------    -------------------------  ----------
  OCR        MedAIBase/PaddleOCR-VL     DONE
  Cleanup    gemma4:12b                 DONE
  Translate  translategemma:4b          STUB — your job

All three stages use the Ollama Python client (`ollama.chat()`). The pattern
is identical across OCR and Cleanup — follow it for Translation.


WHAT TO BUILD
-------------

A) Implement src/ocr_pipeline/stages/translate.py

   Replace the stub with a real implementation that:
   1. Reads the prompt template from prompts/translation_prompt.txt
   2. Splits SYSTEM_PROMPT line from the template (same pattern as cleanup.py)
   3. Calls ollama.chat() with model="translategemma:4b", temperature=0
   4. Writes output to:
      - <output_dir>/translated/text/<stem>.txt
      - <output_dir>/translated/json/<stem>.json
   5. JSON metadata must include:
      - source_file (str)
      - stage: "translated"
      - cleaned_text (str) — the input text before translation
      - translated_text (str) — the LLM output
      - engine: "ollama"
      - model: "translategemma:4b"
      - system_prompt (str)
      - timestamp (ISO 8601 UTC)
   6. Return the data dict

   The perform() signature should be:
       def perform(cleaned_text: str, *, source_file: str = "", output_dir: str = "output") -> Dict[str, Any]

   The prompt template is at prompts/translation_prompt.txt and uses {text}
   as the placeholder. Strip the SYSTEM_PROMPT: line from the template before
   sending (same as cleanup.py).

B) Wire into CLI (src/ocr_pipeline/cli.py)

   Add a `translate` command:
       ocr_pipeline translate <text_path> [--output-dir output]

   Takes a cleaned text file path, runs translation, prints summary.

C) Wire into pipeline (src/ocr_pipeline/pipeline.py)

   Chain: OCR -> Cleanup -> Translate.
   Update run_pipeline() to call translate.perform() after cleanup.perform().
   Return all three result dicts under keys "raw", "cleaned", "translated".

D) Add tests (tests/test_cli.py)

   Follow the existing test pattern (mock ollama.chat, use tmp_path). Add at
   minimum:
   - test_translate_stage_writes_files
   - test_translate_stage_uses_prompt_file
   - test_translate_cli_wires_through
   - test_translate_preserves_cleaned_text_in_json

   All tests must pass with: python -m pytest tests/test_cli.py -v

E) Update README.md

   Add:
   - Translation model prerequisite: ollama pull translategemma:4b
   - Translation stage CLI usage section
   - Updated full pipeline section (OCR -> Cleanup -> Translate)


KNOWN LIMITATIONS TO FIX
-------------------------

1. pipeline.py not wired into CLI
   Currently run_pipeline() is only callable from Python, not from the CLI.
   Add a `pipeline` command to cli.py that runs the full chain:
       ocr_pipeline pipeline <image_path> [--output-dir output]
   This should call run_pipeline() and print a summary of all stages.

2. No Ollama availability check
   If Ollama is not running, all three stages crash with an unhelpful
   ConnectionError. Add a small helper function (e.g., in a new
   src/ocr_pipeline/utils.py or inline in each stage) that checks
   ollama.list() at startup and raises a clear error message if the server
   is unreachable or the required model is not pulled. Use it in the CLI
   before calling any stage.

3. No source language detection for translation
   The translation prompt assumes translation to English but doesn't detect
   the source language. For the 1930s/1940s archival use case, common source
   languages include German, French, Italian, Japanese, and Russian. The
   translate stage should attempt to detect the source language (a simple
   heuristic or LLM-based detection is fine) and include it in the JSON
   metadata. Do NOT change the target language (always English).

4. Stale configs/example.yaml
   The example config references "llama3" and has a trailing backtick on the
   last line. Update it to reflect the actual models used:
       ocr_model: "MedAIBase/PaddleOCR-VL:0.9b"
       cleanup_model: "gemma4:12b"
       translate_model: "translategemma:4b"
   Remove the trailing backtick.


NON-NEGOTIABLE RULES
---------------------

- Do not redesign the architecture.
- Do not rewrite OCR or cleanup stages.
- Do not add unnecessary dependencies (everything goes through ollama).
- Preserve raw OCR output faithfully throughout the pipeline.
- Do not normalize spelling, punctuation, names, abbreviations, or dates.
- The translation stage is optional — pipeline should still work if the user
  skips it.
- If the same error occurs twice, stop and report it.


FILES TO CHANGE
----------------

  File                              Action
  --------------------------------  --------
  src/ocr_pipeline/stages/translate.py  Replace stub
  src/ocr_pipeline/cli.py               Add translate + pipeline commands
  src/ocr_pipeline/pipeline.py          Add translate step
  tests/test_cli.py                     Add translation tests
  README.md                             Update all sections
  configs/example.yaml                  Fix models + trailing backtick
  src/ocr_pipeline/utils.py (NEW)       Optional: Ollama health check


Ollama models already pulled on this machine:
  - MedAIBase/PaddleOCR-VL:0.9b
  - gemma4:12b
  - translategemma:4b

The translategemma:4b model is already available. You do not need to pull it.


VALIDATION COMMANDS
-------------------

  python -m pytest tests/test_cli.py -v       # All tests pass
  python -m src.ocr_pipeline.cli --help       # Shows ocr, cleanup, translate, pipeline
  python -m src.ocr_pipeline.cli translate --help
  python -m src.ocr_pipeline.cli pipeline --help


END OF HANDOFF

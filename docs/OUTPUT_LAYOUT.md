# Artifice output layout

New runs can use a project folder under `<output-root>/projects/<project>/`.
Intermediate pipeline data lives in `pipeline/`; files intended for people or
other applications live in `exports/`; `run-history/` records each run without
duplicating source media.

```text
project/
  project.json
  run-history/<run-id>.json
  pipeline/<stage>/{text,records}/
  exports/{pdf,markdown,tropy,ludwiglang,graph,obsidian,transcript,draft}/
```

Older `output/<stage>/{text,json}` and Graph `data/output/*.json` folders remain
readable. They are not moved automatically. Selecting a canonical project in
the OCR web app makes subsequent pipeline and PDF output use the new layout.

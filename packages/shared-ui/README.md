# shared-ui

Canonical design tokens for The New Masses design system (see
`Design_Philosophy.md` at the repo root). `tokens.css` is the source of
truth for the `:root` custom-property block; `artifice-ocr`,
`artifice-draft`, and `artifice-transcribe` each currently declare an
identical copy of these tokens at the top of their own `static/css/app.css`.
Consolidating those three call sites to `@import` or `<link>` this file
instead of redeclaring the literals is the intended next step, not done as
part of the directory reorganization.

`artifice-graph` was consolidated into this file first (2026-07): its
app-local `tokens.css` had accumulated 46 tokens (shadows, radius, spacing,
motion, layout, `--font-mono`) that shared-ui was simply missing, plus one
naming drift (`--font-sans` → renamed to the already-canonical
`--font-label`) and two dead/out-of-scope token families that were removed
or relocated rather than promoted:

- `--w-*` ("Word-Status Colours (Reading View)") — deleted outright.
  ArtificeGraph has no reading view; this was copy-paste residue.
- `--reg-*` (register taxonomy) and `--type-*` (entity-type accents) —
  ArtificeGraph domain vocabulary, not suite-wide identity. These now live
  in `apps/artifice-graph/web/static/entity-colors.css`, loaded after this
  file.

**Known gap:** `artifice-graph`'s `web/static/tokens.css` still duplicates
this file's values rather than importing it, because the app's
`StaticFiles` mount only serves `web/static/` and cannot reach
`packages/shared-ui/` over HTTP yet. See that file's header comment and the
app's own notes for the wiring this still needs (an extra static mount or a
build/sync step) before the duplication can be removed.

Usage once an app switches over:

```html
<link rel="stylesheet" href="/shared-ui/tokens.css" />
```

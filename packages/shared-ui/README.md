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
app-local `tokens.css` had accumulated 30 tokens (shadows, radius, spacing,
motion, layout, `--font-mono`) that shared-ui was simply missing, plus the
`@media (prefers-color-scheme: dark)` block — without which this file could
only respond to an explicit `[data-theme]` and never follow the OS. It also
carried one naming drift (`--font-sans` → renamed to the already-canonical
`--font-label`) and two dead/out-of-scope token families that were removed
or relocated rather than promoted:

- `--w-*` ("Word-Status Colours (Reading View)") — deleted outright.
  ArtificeGraph has no reading view; this was copy-paste residue.
- `--reg-*` (register taxonomy) and `--type-*` (entity-type accents) —
  ArtificeGraph domain vocabulary, not suite-wide identity. These now live
  in `apps/artifice-graph/web/static/entity-colors.css`, loaded after this
  file.

`artifice-graph` no longer keeps a copy at all. Its `web/static/tokens.css`
was deleted; `web/server.py` mounts this directory directly, so the app
serves *this* file rather than a mirror of it. There is nothing to keep in
sync, and no per-app `tokens.css` should be reintroduced.

```python
# apps/artifice-graph/web/server.py
_SHARED_UI = _PROJECT.parent.parent / "packages" / "shared-ui"
if not _SHARED_UI.is_dir():
    raise RuntimeError(...)          # fail loudly, never serve nothing
app.mount("/shared", StaticFiles(directory=str(_SHARED_UI)), name="shared")
```

```html
<link rel="stylesheet" href="/shared/tokens.css?v={{ asset_v }}" />
```

Load this before any stylesheet that consumes the variables, and before an
app's own domain colours (e.g. `entity-colors.css`).

Adopt the same mount when consolidating the remaining three apps.

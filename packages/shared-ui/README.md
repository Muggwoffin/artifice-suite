# shared-ui

Canonical design tokens for The New Masses design system (see
`Design_Philosophy.md` at the repo root). `tokens.css` is the source of
truth for the `:root` custom-property block; `artifice-ocr`,
`artifice-draft`, and `artifice-transcribe` each currently declare an
identical copy of these tokens at the top of their own `static/css/app.css`.
Consolidating those three call sites to `@import` or `<link>` this file
instead of redeclaring the literals is the intended next step, not done as
part of the directory reorganization.

Usage once an app switches over:

```html
<link rel="stylesheet" href="/shared-ui/tokens.css" />
```

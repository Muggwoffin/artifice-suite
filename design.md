# Design — Artifice OCR

A locked design system for the OCR application. The interface is a working
research desk: source material enters from Tropy, moves through transcription,
is reviewed beside the scan, and returns to Tropy as a note.

## Genre

Editorial application UI. Function carries the page; decoration does not.

## Macrostructure family

- App pages: Workbench with a four-step workflow rail and one primary work area.
- Content pages: Long Document using the same masthead, paper, ink, and rules.
- Marketing pages: not applicable inside the desktop application.

## Theme

The runtime source of truth is
`packages/shared-ui/shared_ui/assets/tokens.css`. Artifice OCR adds only its
viridian accent in `web/static/css/app.css`.

- Paper: `#f6f3ea`; raised paper: `#fbf9f3`; recessed paper: `#efebdf`
- Ink: `#1b1813`; soft ink: `#4b463d`; rule: `#ddd6c6`
- Accent: `#017259`; deep accent: `#005942`
- Focus: the accent with a paper offset; status colours remain semantically distinct

## Typography

- Display: Playfair Display, weight 400–600, roman
- Body: Libre Baskerville, weight 400
- Labels: Archivo, weight 500–700
- Mono: the platform monospace stack from shared tokens

## Spacing

Use the existing rem-based 4-point `--space-1` through `--space-12` scale.
New application UI must use named tokens rather than raw spacing values.

## Motion

- Use `--ease-primary` and the named duration tokens.
- Motion communicates state only; no entrance animation or decorative movement.
- Reduced motion removes spatial movement and preserves immediate focus feedback.

## Microinteractions stance

- Async success may use one quiet confirmation because the result occurs in Tropy.
- Errors remain visible beside the action that failed.
- Focus rings are immediate; loading controls use `aria-busy` and stable labels.
- Destructive history deletion retains its existing explicit safeguard.

## CTA voice

- Primary: solid viridian, short verb-led label such as “Run OCR” or “Add notes”.
- Secondary: paper surface with a hairline rule.
- Buttons never wrap; dense table actions use the compact variant.

## Per-page allowances

- Application views use no enrichment or ornamental imagery.
- Source scans are evidence, not decoration, and are never cropped for effect.
- About/documentation pages are typography-only.

## What pages MUST share

- Shared Artifice masthead and OCR mark.
- Paper/ink palette, viridian accent, and the three-font role system.
- Four-step workflow language: Source, Process, Review, Return.
- One containment layer per work area and visible keyboard focus.

## What pages MAY differ on

- Queue density and review-pane proportions may respond to their content.
- Modal width may vary between source browsing and note confirmation.
- Content pages may use a narrower reading measure.

## Exports

The canonical CSS export is the existing shared token file named above. Its
semantic mapping for other formats is:

- Tailwind v4: paper → `--color-paper`, ink → `--color-ink`, OCR viridian → `--color-accent`.
- DTCG: `color.paper`, `color.ink`, `color.accent`; `font.display`, `font.body`, `font.label`.
- shadcn/ui: paper/ink map to background/foreground, viridian to primary/ring,
  recessed paper to muted, and rule to border/input.

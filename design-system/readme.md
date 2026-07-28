# Artifice Design System

Artifice is a collection of **local-first, bring-your-own-model (BYOM) desktop tools** built around rigid software harnesses rather than chat/conversational AI interfaces. Each tool is a separate desktop app with its own mark, sharing one visual and verbal identity:

- **Draft** — copy editing
- **OCR** — optical character recognition
- **Transcribe** — transcription of oral history recordings
- **Graph** — knowledge graph construction

**Sources provided:** five logo PNGs (`Artifice Assets/` — Main, Draft, Graph, OCR, Transcribe), plus a real design-philosophy document, `Design_Philosophy.md` — **"The New Masses Design System,"** the actual token/component spec used by `apps/artifice-graph` in Artifice's own codebase (canonical tokens at `packages/shared-ui/shared_ui/assets/tokens.css`), itself derived from Dr Maurice J. Casey's personal site at mauricejcasey.com. That document is now ground truth for palette, type, spacing, radius, shadow, motion, and component patterns — it supersedes the from-scratch choices in the first pass of this system. Where this design system's file layout differs from that doc's raw values (naming, dark-mode wiring), this file wins for internal consistency, but the values themselves are copied precisely, not rounded.

## Font note
The New Masses spec's fonts — **Playfair Display** (display), **Libre Baskerville** (body), **Archivo** (UI/labels) — are all real, freely-licensed Google Fonts, so no substitution was needed for them. Mono uses the doc's own system stack (SF Mono/Consolas/Menlo) rather than a webfont, matching the source.

## Index
- `styles.css` — root stylesheet, `@import`s only. Link this one file.
- `tokens/` — `colors.css`, `typography.css`, `spacing.css`, `effects.css`, `fonts.css`
- `guidelines/` — foundation specimen cards (Design System tab: Colors, Type, Spacing, Brand groups)
- `assets/logos/` — the 5 provided logo PNGs
- `components/` — reusable primitives, grouped by concern:
  - `components/core/` — Button, IconButton, Badge, Tag
  - `components/forms/` — Input, Textarea, Select, Checkbox, Switch
  - `components/feedback/` — Toast, Dialog, ProgressBar, EmptyState
  - `components/navigation/` — Tabs, Sidebar, TitleBar
  - `components/surfaces/` — Card, Panel
- `ui_kits/draft/`, `ui_kits/ocr/`, `ui_kits/transcribe/`, `ui_kits/graph/` — click-through recreations of each desktop app
- `slides/` — slide deck templates (title, comparison, big quote, section)
- `SKILL.md` — portable skill file for Claude Code

## Content fundamentals
Voice is **literary and scholarly**: precise, understated, a little old-world — the register of a careful editor, not a SaaS marketer.
- Second person is used sparingly and only for direct instruction ("Drop a folder to begin"); most UI copy is declarative and impersonal ("12 files pending review", not "You have 12 files!").
- No exclamation points, no hype adjectives ("powerful", "seamless", "supercharge"). Prefer plain verbs: *review*, *transcribe*, *extract*, *link*.
- Sentence case throughout — headlines, buttons, menu items. Title Case is reserved for proper nouns and product names only.
- Numbers and status are stated plainly: "3 of 12 pages reviewed", not "You're crushing it! 3/12 done 🎉"
- No emoji, anywhere. Status is conveyed with words and the sage/rust accent colors, not glyphs.
- Empty and error states read like marginal notes, not apologies: "Nothing transcribed yet." rather than "Oops! Looks like there's nothing here."
- Product names are treated as proper nouns and used unadorned: *Draft*, *OCR*, *Transcribe*, *Graph* — never "Artifice Draft™" in-product.

## Visual foundations
- **Color**: warm parchment surfaces (`--parchment-100/200/300`), near-black ink text (`--ink-900`), a single sage green accent (`--sage-500/600/700`) for actions and state, and a muted rust used only for warnings. No blues, no purples, no gradients as decoration.
- **Type**: Source Serif 4 for display/headlines and product wordmarks (editorial weight); Inter for all UI/body text (buttons, labels, tables, forms); IBM Plex Mono for file paths, timestamps, model IDs, and raw text/OCR output.
- **Spacing**: 4px base scale (4/8/12/16/20/24/32/40/48/64/80/96). Desktop-app density — compact controls (32–36px row height), generous page margins.
- **Backgrounds**: flat parchment fields. No photography, no full-bleed imagery, no repeating textures or patterns, no gradients. The only illustration is the small line-icon glyph paired with the wordmark in each product's logo.
- **Animation**: minimal and functional only — 120–180ms ease-standard fades/opacity changes and small position shifts (e.g. panel slide-in). No bounce, no spring, no decorative motion. Tools should feel inert and precise, not playful.
- **Hover states**: background shifts one step darker on the parchment scale for neutral controls; sage buttons darken to `--sage-600`. No glow, no scale-up.
- **Press/active states**: sage buttons darken further to `--sage-700`; no shrink/scale transform — desktop tool controls should feel stable underfoot.
- **Borders**: 1px hairlines in `--border-subtle`/`--border-default`, used generously to separate panels (this is a bordered system, not a shadow-heavy one).
- **Shadows**: very restrained — `--shadow-sm`/`--shadow-md` only for genuinely elevated surfaces (dialogs, dropdowns, toasts). Cards on the page sit flush with a border, not a shadow.
- **Corner radii**: small and consistent — 3px (inputs, tags), 6px (cards, buttons, panels), pill only for status chips. Nothing is heavily rounded; this is not a "bubbly" system.
- **Cards**: `--surface-card` fill, 1px `--border-subtle`, 6px radius, no shadow at rest; a raised variant (`--surface-card-raised` + `--shadow-sm`) is used only for floating/overlay contexts.
- **Transparency & blur**: none in normal UI. A single translucent scrim (`rgba(23,23,15,.4)`) behind modal dialogs is the only use of transparency; no backdrop-blur anywhere (keeps the "inert tool," not "glassy app," feel).
- **Imagery**: none provided; none invented. If/when product screenshots or illustrations exist, they should read as plain, undoctored, slightly desaturated — no warm Instagram-style grain or stylization implied by anything in the source.
- **Layout rules**: each app is a fixed-chrome desktop window — a persistent left sidebar (source/navigation) and a top title bar; content area scrolls, chrome doesn't.

## Iconography
The five product-logo glyphs (pencil/Draft, graph-node cluster/Graph, magnifying glass/OCR, closing quotation mark/Transcribe) are all thin-stroke, ~2px, rounded joins, single-color — consistent with the New Masses spec's rule: inline SVG only, never an icon font, never emoji in chrome (see Visual foundations).

We don't yet have the real icon SVGs or repo access to `apps/artifice-graph`'s markup, so cards/kits here reference **Lucide** via CDN (`unpkg.com/lucide-static`, `stroke-width:2`, tinted to `currentColor`) as a stand-in for the real inline-SVG icons the spec calls for. This is a substitution, not a source asset, and it doesn't fully match the spec's local-first, no-external-request intent — swap in the real vendored SVGs (or grant repo access to `packages/shared-ui`) and we'll inline them properly.

## Intentional additions
No component library or screen source was provided, so the components below are a standard desktop-tool set sized to what these four apps need (sidebar/file-list pattern, review queues, progress states) — not derived from an existing inventory. Flagged here per the "brand-guidelines-only" path rather than listed as individual justifications.

## Caveats
- Tokens, type, motion, and component patterns now come from a real source (`Design_Philosophy.md`), but we still have no direct code/Figma access to `apps/artifice-graph` or the other three apps — screens in the four UI kits remain originated in this direction, not recreated pixel-for-pixel from real product screens.
- Icons are a Lucide-CDN stand-in, not the real vendored inline SVGs (see Iconography).
- Ask to iterate: grant repo/Figma access to any of the four apps and we'll recreate real screens instead of originated ones; share the real icon SVGs to replace the Lucide substitution.

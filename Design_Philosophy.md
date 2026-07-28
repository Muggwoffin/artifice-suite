# The New Masses Design System

**Design Philosophy & Agent Implementation Guide**

---

## 1. Design Origin

The visual identity is drawn from *The New Masses*, the 1920s–30s American radical literary magazine. The compositional language comes from Soviet Constructivism — El Lissitzky's poster work in particular — filtered through a warm, archival sensibility. It is not a retro theme; it is an editorial system that treats every surface as a page, every component as a typeset block.

**Core principles:**

- **Paper and ink.** Every surface is paper. Every element is ink on paper. Nothing floats in a void.
- **Editorial restraint.** Motion reveals structure, never decorates. A rule draws in, a card lifts, a star settles. That is enough.
- **Warmth over cool.** The palette is cream, warm black, forest green, and antique gold. No pure whites, no pure blacks, no cold grays.
- **Typographic hierarchy drives layout.** The font families and their sizes/weights do most of the compositional work. Grids support type; they do not replace it.
- **Square corners with soft edges.** Cards and containers use rounded corners (adapted from the website's strict squares for app contexts). Shadows are paper-like, never glowy or neon.

---

## 2. Color Palette

### Light Mode (default)

| Token | Hex | Role |
|---|---|---|
| `paper` | `#f6f3ea` | Main background — warm cream |
| `paper-raised` | `#fbf9f3` | Elevated surfaces — cards, buttons, modals |
| `paper-recessed` | `#efebdf` | Inset surfaces — input fields, recessed areas |
| `ink` | `#1b1813` | Primary text — deep warm black |
| `ink-soft` | `#4b463d` | Secondary text — muted warm brown |
| `ink-faint` | `#635e51` | Tertiary text, labels, captions (5.4:1 on paper — WCAG AAA) |
| `rule` | `#ddd6c6` | Light dividers, borders |
| `rule-dark` | `#45413a` | Dark dividers, prominent borders |
| `accent` | `#2f7d45` | Primary accent — Esperanto green |
| `accent-deep` | `#1f5a31` | Darker green — link hovers, deep accent |
| `accent-wash` | `rgba(47, 125, 69, 0.07)` | Transparent green tint for subtle backgrounds |
| `gold` | `#bf9b30` | Antique gold — star emblems, highlights |

### Dark Mode ("Lamplight Archive")

| Token | Hex | Notes |
|---|---|---|
| `paper` | `#161310` | Dark warm brown-black |
| `paper-raised` | `#1f1b16` | Slightly lighter |
| `paper-recessed` | `#100e0b` | Deepest surface |
| `ink` | `#e8e2d3` | Warm off-white text |
| `ink-soft` | `#beb5a3` | Muted warm |
| `ink-faint` | `#a39a88` | Tertiary — enhanced contrast for dark ground |
| `rule` | `#38332b` | Dark dividers |
| `rule-dark` | `#5b554a` | More visible dark dividers |
| `accent` | `#4aa066` | Lifted green — must read on dark ground |
| `accent-deep` | `#7cc492` | Used as text — must read light |
| `accent-wash` | `rgba(74, 160, 102, 0.12)` | Subtler on dark |
| `gold` | `#bf9b30` | Unchanged |

### Selection Color

```
background: rgba(47, 125, 69, 0.22)
text: var(--ink)
```

### Semantic Colors (status, not part of core identity)

| Token | Light | Dark | Role |
|---|---|---|---|
| `success` | `#455f2b` | `#67a04b` | Success states — both values kept a distinct hue family (moss/olive, ~H90–100) from `accent`'s forest green (~H137–139) so success never reads as the brand accent. The light value was originally `#256b39` (~H137, same family as `accent`), CIE76 delta-E 7.6 from `accent` — below the ~15 threshold where two colours reliably read as distinct to any viewer. The current value holds delta-E ~20 from `accent` at 6.5:1 on `--paper` |
| `error` | `#a8322b` | `#dd5555` | Error states |
| `warning` | `#7c5e1a` | `#e4cb81` | Warning states — warmed/darkened to a desaturated ochre in light mode; raw amber (`#ffc107`) cannot reach 4.5:1 on `--paper` at any reasonable saturation. Dark `warning`/`error` are separated by lightness, not just hue: at the original `#d9b64a`/`#e06060` the two simulated (Vienot 1999 deuteranopia projection) to CIE76 delta-E 8.4 — both read as the same muddy olive under red-green colour blindness. The current values simulate to delta-E ~24 apart while each still holds 4.5:1+ on `--paper` and remains recognisably amber/red to normal vision (delta-E ~62, unchanged) |

### Color Usage Rules

- **Never use pure `#000000` or `#ffffff`.** The closest acceptable values are `--ink` and `--paper-raised`.
- **Green accent is the primary action color.** Links, focus rings, active states, interactive highlights.
- **Gold is decorative only.** Star emblems, special highlights. Never used for interactive affordances.
- **Ink colors form a hierarchy:** `ink` for headings and primary text, `ink-soft` for body secondary and meta, `ink-faint` for labels, captions, and timestamps.
- **Paper colors form a depth hierarchy:** `paper` for base, `paper-raised` for cards/modals, `paper-recessed` for inputs/insets.

---

## 3. Typography

### Font Families

| Role | Token | Family | Fallback Stack | Weights Loaded |
|---|---|---|---|---|
| Display | `--font-display` | Playfair Display | `'Playfair Display', Georgia, serif` | 700, 900 (normal), 700 (italic) |
| Body | `--font-body` | Libre Baskerville | `'Libre Baskerville', Georgia, serif` | 400, 700 (normal), 400 (italic) |
| Labels / UI | `--font-label` | Archivo | `'Archivo', 'Franklin Gothic Medium', 'Arial Narrow', sans-serif` | 500, 600, 700 |
| Monospace | `--font-mono` | SF Mono / Consolas | `'SFMono-Regular', 'Consolas', 'Liberation Mono', 'Menlo', monospace` | Regular (system default) — log panels, code blocks, confidence readouts |

### Font Size Scale (Fluid)

| Token | Value | Usage |
|---|---|---|
| `text-xs` | `0.72rem` (~11.5px) | Nav links, colophon, meta labels, timestamps |
| `text-sm` | `0.78–0.8rem` (~12.5–12.8px) | Button text, secondary labels |
| `text-base` | `1.0625rem` (17px) | Body text |
| `text-lg` | `clamp(1.15rem, 1.05rem + 0.4vw, 1.3rem)` | Large body, intro text |
| `text-h3` | `clamp(1.35rem, 1.2rem + 0.8vw, 1.8rem)` | Card titles, subsection headings |
| `text-h2` | `clamp(1.9rem, 1.5rem + 2vw, 2.8rem)` | Section headlines |
| `text-hero` | `clamp(2.6rem, 1.6rem + 5.5vw, 5.25rem)` | Page titles, mastheads |

### Font Weights

| Weight | Family | Usage |
|---|---|---|
| 400 | Libre Baskerville | Body text, descriptions |
| 500 | Archivo | Colophon, secondary labels |
| 600 | Archivo | Buttons, meta text, nav items, labels, uppercase UI |
| 700 | Playfair Display | Section headlines, card titles, display headings |
| 700 | Libre Baskerville | Bold body text |
| 700 | Archivo | Strong labels, interactive elements |
| 900 | Playfair Display | Hero/masthead titles, major headlines |

### Letter Spacing

| Context | Value | Token |
|---|---|---|
| Labels, uppercase UI | `0.16em` | `label-tracking` |
| Section headlines | `0.025em` | |
| Display titles (hero) | `-0.01em` | Tight — display sizes want tighter tracking |
| Subtitle / wide labels | `0.34em` | Ultra-wide for subtitle emphasis |
| Normal body | `0` | Default |

### Line Heights

| Context | Value |
|---|---|
| Body text | `1.75` |
| Headlines / display | `1.1–1.2` |
| Card titles | `1.2–1.25` |
| Meta / labels | `1.4–1.55` |
| Contact / dense info | `1.85` |

### Text Transform

Uppercase is reserved for: labels, nav items, buttons, meta timestamps, kicker text, and chip/tag text. Body text and titles are never uppercase.

---

## 4. Spacing

The system uses a 4px-base scale derived from actual values in the source CSS. Spacing is editorial — generous at section boundaries, dense within content blocks.

| Token | Value | Common Usage |
|---|---|---|
| `space-1` | `2px` | Micro gaps (inline elements) |
| `space-2` | `4px` | Tight padding (badges, chips) |
| `space-3` | `8px` (0.5rem) | Small internal gaps |
| `space-4` | `12px` (0.75rem) | Component internal padding |
| `space-5` | `16px` (1rem) | Standard padding, card internal |
| `space-6` | `20px` (1.25rem) | Page wrapper mobile padding |
| `space-7` | `24px` (1.5rem) | Medium gaps, card padding |
| `space-8` | `28px` (1.75rem) | Card grid gaps |
| `space-9` | `32px` (2rem) | Desktop padding, section content gap |
| `space-10` | `40px` (2.5rem) | Section spacing |
| `space-11` | `48px` (3rem) | Major section gaps |
| `space-12` | `88px` (5.5rem) | Footer margin, extreme separation |

**Container max-widths:**

| Context | Width |
|---|---|
| Standard app container | `1200px` |
| Content-focused (reading, forms) | `44rem` (~704px) |
| Narrow (single-column) | `56–58ch` |

---

## 5. Borders & Corner Radius

### Corner Radius (App Adaptation)

The original website is square-cornered. For app contexts, corners are softened:

| Token | Value | Usage |
|---|---|---|
| `radius-sm` | `4px` | Inputs, badges, small chips, inline tags |
| `radius-md` | `8px` | Buttons, filter chips, dropdown menus |
| `radius-lg` | `12px` | Cards, feature panels, list items |
| `radius-xl` | `16px` | Modals, overlays, sidebars, sheet panels |
| `radius-full` | `9999px` | Pills, avatars, circular elements |

### Border Patterns

| Pattern | Specification | Usage |
|---|---|---|
| Thin rule | `1px solid var(--rule)` | Card borders, section dividers |
| Dark rule | `1px solid var(--rule-dark)` | Prominent dividers |
| Accent rule | `3px solid var(--accent)` | Left-border accents, intro text, active states |
| Top accent | `3px solid var(--ink)` | Card top border (primary cards) |
| Top accent green | `3px solid var(--accent)` | Card top border (interactive cards) |
| Double rule | `3px double var(--ink)` | Newsletter box, footer separator |
| Modal top | `4px solid var(--accent)` | Modal dialog top edge |
| Masthead top | `4px solid var(--ink)` | Page/masthead top border |

### Border Radius Usage by Component

| Component | Radius | Notes |
|---|---|---|
| Cards (book, writing, event, media) | `radius-lg` (12px) | Softened from original square |
| Buttons (primary, secondary) | `radius-md` (8px) | |
| Text inputs, search fields | `radius-sm` (4px) | Subtle, doesn't fight the text |
| Filter chips, tags | `radius-md` (8px) | |
| Modals, dialogs | `radius-xl` (16px) | Prominent rounded container |
| Dropdown menus | `radius-lg` (12px) | |
| Tooltips | `radius-sm` (4px) | Small, unobtrusive |
| Avatars, circular badges | `radius-full` | |
| Cards with top-border accent | `radius-lg 12px 12px 0` | Top corners only, bottom square | **Do not use.** Use uniform `radius-lg`. |
| Progress bars | `radius-full` | Pill shape |
| Toast notifications | `radius-lg` (12px) | |
| Sidebar panels | `radius-xl` (16px) | |

---

## 6. Shadows & Depth

Shadows are paper-like: warm, diffused, never glowy. They suggest physical depth — a card lifted off a desk — not neon halos.

### Shadow Tokens

| Token | Value | Usage |
|---|---|---|
| `shadow-paper` | `0 1px 2px rgba(27,24,19,0.05), 0 10px 28px -14px rgba(27,24,19,0.18)` | Resting cards, default elevation |
| `shadow-lifted` | `0 2px 4px rgba(27,24,19,0.07), 0 22px 44px -18px rgba(27,24,19,0.28)` | Hovered/active cards, elevated panels |
| `shadow-nav` | `0 6px 24px -16px rgba(27,24,19,0.3)` | Sticky navigation bar |
| `shadow-modal` | `0 4px 24px -4px rgba(27,24,19,0.35)` | Modal overlays |

### Dark Mode Shadows

| Token | Value |
|---|---|
| `shadow-paper` | `0 1px 2px rgba(0,0,0,0.4), 0 10px 26px -14px rgba(0,0,0,0.6)` |
| `shadow-lifted` | `0 2px 4px rgba(0,0,0,0.5), 0 22px 42px -16px rgba(0,0,0,0.7)` |

### Button Hard-Offset Shadows

Buttons use a distinctive hard-offset shadow (no blur), not the paper shadow:

| State | Shadow |
|---|---|
| Resting | `3px 3px 0 var(--paper-recessed)` |
| Hovered | `4px 4px 0 var(--accent)` |

The hover state shifts the shadow from recessed-paper to accent-green and increases the offset by 1px, creating a tactile "press" effect.

### Depth Hierarchy

| Level | Surface | Shadow |
|---|---|---|
| 0 — Base | `paper` | None |
| 1 — Raised | `paper-raised` | `shadow-paper` |
| 2 — Lifted | `paper-raised` | `shadow-lifted` |
| 3 — Nav/Toast | `paper-raised` | `shadow-nav` |
| 4 — Modal | `paper-raised` | `shadow-modal` |

---

## 7. Motion & Animation

### Design Philosophy

Motion in this system is **editorial, not decorative.** It exists to:
1. Reveal structure (scroll reveals, staggered card cascades)
2. Confirm interaction (hover lifts, button presses)
3. Establish spatial relationships (parallax, modal rise)

Motion should never:
- Play automatically on loops (except star twinkle, which is an easter egg)
- Delay the user from accessing content
- Cause layout shift
- Occur without a reduced-motion fallback

### Primary Easing Curve

All non-trivial animations use one custom cubic-bezier:

```
cubic-bezier(0.22, 0.61, 0.36, 1)
```

This is a smooth ease-out-quart variant. It decelerates gently, giving movements a sense of weight and settling. Use this for:
- Card lifts and hovers
- Scroll reveals
- Modal entrance
- Rule draw-ins
- Star settle
- Hero entrance choreography

Simpler transitions (color changes, opacity fades) use standard `ease`.

### Duration Tokens

| Token | Value | Usage |
|---|---|---|
| `duration-instant` | `100ms` | Micro-interactions (focus ring, opacity toggle) |
| `duration-fast` | `200–250ms` | Color transitions, nav link underline, simple fades |
| `duration-normal` | `300–350ms` | Card hover lifts, button state changes, link underline draws |
| `duration-slow` | `450–600ms` | Modal entrance, collapse/expand, complex reveals |
| `duration-glacial` | `700–850ms` | Hero entrance choreography, section fade-up |

### Choreography Patterns

#### Scroll Reveal (Section Entrance)

```
animation: fadeUp 0.7s cubic-bezier(0.22, 0.61, 0.36, 1) forwards;

@keyframes fadeUp {
    from { opacity: 0; transform: translateY(18px); }
    to   { opacity: 1; transform: translateY(0); }
}
```

Sections fade up from 18px below. Triggered by IntersectionObserver (threshold: 0.1, rootMargin: `0px 0px -50px 0px`).

#### Staggered Card Cascade

Children within a revealed section arrive in sequence — a shuffle of papers being laid out, not a curtain.

```
Child 1: delay 0.00s
Child 2: delay 0.07s
Child 3: delay 0.14s
Child 4: delay 0.21s
Child 5: delay 0.28s
Child 6: delay 0.35s
```

Each child uses `fadeUp 0.6s cubic-bezier(0.22, 0.61, 0.36, 1) backwards` (backwards fill-mode so they wait at the start state until their delay expires).

#### Decorative Rule Draw-In

```
animation: ruleIn 0.8s cubic-bezier(0.22, 0.61, 0.36, 1) 0.15s backwards;

@keyframes ruleIn {
    from { transform: scaleX(0); }
    to   { transform: scaleX(1); }
}
```

Transform-origin: left center. The rule draws in from the left as its section settles.

#### Star Settle

```
animation: starSettle 0.55s cubic-bezier(0.22, 0.61, 0.36, 1) 0.25s backwards;

@keyframes starSettle {
    from { opacity: 0; transform: rotate(-40deg) scale(0.6); }
    to   { opacity: 1; transform: rotate(0deg) scale(1); }
}
```

Stars rotate the last few degrees into place. Used for decorative star elements in subsection headings.

#### Modal Rise

```
animation: modalRise 0.35s cubic-bezier(0.22, 0.61, 0.36, 1) forwards;

@keyframes modalRise {
    from { opacity: 0; transform: translateY(16px); }
    to   { opacity: 1; transform: translateY(0); }
}
```

Modals slide up 16px with a fade. Shorter than section reveals — modals are immediate.

#### Card Hover Lift

```css
.card:hover {
    transform: translateY(-4px);
    box-shadow: var(--shadow-lifted);
    border-color: var(--rule-dark);
}
```

Duration: `0.35s cubic-bezier(0.22, 0.61, 0.36, 1)`. The card lifts 4px, shadow deepens, border darkens slightly. Three properties change together.

#### Card Top-Accent Draw-In (Writing Cards)

```css
.card::before {
    content: '';
    position: absolute;
    top: -1px; left: -1px; right: -1px;
    height: 3px;
    background-color: var(--accent);
    transform: scaleX(0);
    transform-origin: 0 50%;
    transition: transform 0.4s cubic-bezier(0.22, 0.61, 0.36, 1);
}
.card:hover::before {
    transform: scaleX(1);
}
```

A green accent rule draws across the top of the card on hover. The card lifts simultaneously.

#### Link Underline Draw

```css
a {
    background-image: linear-gradient(currentColor, currentColor);
    background-size: 0% 1px;
    transition: background-size 0.3s ease;
}
a:hover {
    background-size: 100% 1px;
}
```

Underlines draw in from the left using a background-size animation, not a border. This allows precise control of the draw direction and timing.

#### Star Twinkle (Hover Easter Egg)

```
@keyframes starTwinkle {
    0%   { transform: rotate(0deg) scale(1); }
    50%  { transform: rotate(36deg) scale(1.13); }
    100% { transform: rotate(72deg) scale(1); }
}
```

Duration: `1.3s ease-in-out infinite`. Only on hover/focus of star elements. Never plays automatically.

#### Button Press

```css
.button {
    box-shadow: 3px 3px 0 var(--paper-recessed);
    transition: background-color 0.3s ease, color 0.3s ease,
                box-shadow 0.3s ease, transform 0.3s ease;
}
.button:hover {
    transform: translate(-1px, -1px);
    box-shadow: 4px 4px 0 var(--accent);
}
```

The button nudges 1px up-left while the shadow grows 1px and turns green. This creates a tactile "lifting" effect.

### Reduced Motion

All animations must have a `prefers-reduced-motion: reduce` fallback:

```css
@media (prefers-reduced-motion: reduce) {
    *,
    *::before,
    *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
    }

    section {
        opacity: 1 !important;
    }
}
```

This is a blunt global fallback. For fine-grained control, also cancel specific animations:

- Hero elements: set `animation: none` (they rest in their final state via `fill-mode: both`)
- Section reveals: set `opacity: 1` and `animation: none`
- Nav transitions: set `transition: none`
- Collapse/expand: jump to final state (`max-height: 0` or full, `opacity: 0` or `1`)

JavaScript animation components must check for reduced motion before triggering:

```javascript
const prefersReducedMotion = () =>
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

if (prefersReducedMotion()) {
    // Skip animation, set final state directly
}
```

### Performance Rules

- **Animate only `transform` and `opacity`.** These are GPU-compositable and do not trigger layout or paint.
- **Use `will-change: transform`** sparingly on elements known to animate (e.g., parallax backgrounds).
- **Use `{ passive: true }`** on all scroll event listeners.
- **Use `IntersectionObserver`** for scroll-triggered effects, never scroll-position polling.
- **Use `requestAnimationFrame`** for any JavaScript-driven animation loops.

---

## 8. Components

### 8.1 Buttons

#### Primary Button

```css
.button-primary {
    font-family: var(--font-label);
    font-size: 0.8rem;
    font-weight: 600;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    padding: 0.8rem 1.4rem;
    border: 1.5px solid var(--ink);
    border-radius: 8px;
    background-color: var(--paper-raised);
    color: var(--ink);
    box-shadow: 3px 3px 0 var(--paper-recessed);
    cursor: pointer;
    transition: background-color 0.3s ease, color 0.3s ease,
                box-shadow 0.3s ease, transform 0.3s ease;
}
.button-primary:hover {
    background-color: var(--ink);
    color: var(--paper-raised);
    transform: translate(-1px, -1px);
    box-shadow: 4px 4px 0 var(--accent);
}
```

#### Secondary Button (outlined)

Same as primary but `background-color: transparent`. Hover fills with `--ink`.

#### Ghost Button (text-only)

No border, no shadow. Just the underline-draw interaction from the link pattern.

### 8.2 Cards

#### Standard Card

```css
.card {
    padding: 1.9rem;
    background-color: var(--paper-raised);
    border: 1px solid var(--rule);
    border-radius: 12px;
    box-shadow: var(--shadow-paper);
    transition: transform 0.35s cubic-bezier(0.22, 0.61, 0.36, 1),
                box-shadow 0.35s ease,
                border-color 0.35s ease;
}
.card:hover {
    transform: translateY(-4px);
    border-color: var(--rule-dark);
    box-shadow: var(--shadow-lifted);
}
```

#### Card with Top Accent

Add `border-top: 3px solid var(--ink)` or `border-top: 3px solid var(--accent)` for emphasis cards.

#### Card Grid

```css
.card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 1.75rem;
}
```

### 8.3 Form Inputs

```css
.input {
    font-family: var(--font-body);
    font-size: var(--text-base);
    padding: 0.7rem 1rem;
    background-color: var(--paper-recessed);
    border: 1px solid var(--rule);
    border-radius: 4px;
    color: var(--ink);
    transition: border-color 0.2s ease;
}
.input:focus {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
    border-color: var(--accent);
}
```

### 8.4 Filter Chips / Tags

```css
.chip {
    font-family: var(--font-label);
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    padding: 0.4rem 0.9rem;
    border: 1.5px solid var(--rule);
    border-radius: 8px;
    background-color: transparent;
    color: var(--ink-soft);
    transition: background-color 0.25s ease, color 0.25s ease,
                border-color 0.25s ease;
}
.chip.active, .chip:hover {
    background-color: var(--ink);
    color: var(--paper-raised);
    border-color: var(--ink);
}
```

### 8.5 Navigation Bar

The nav bar is **always visible** — pinned to the top of the viewport at all times. It does not hide or reveal on scroll.

```css
.nav {
    position: fixed;
    top: 0; left: 0; right: 0;
    z-index: 300;
    height: 56px;
    background-color: rgba(251, 249, 243, 0.96);
    border-bottom: 1px solid var(--rule);
    backdrop-filter: blur(12px) saturate(1.1);
}
```

- Always pinned to top — never translated off-screen
- Backdrop blur provides frosted-glass effect over scrolling content
- Active section link gets a 2px green underline via `scaleX(0)` to `scaleX(1)` transition
- Main content area should account for the 56px nav height (e.g., `padding-top: 56px` or `scroll-margin-top` on anchored sections)

**Implementation reference (`.topnav`, `apps/artifice-graph`):** the shipped class is `.topnav`, not `.nav`, and backdrop blur is gated behind `@media (min-width: 700px)` rather than applied unconditionally — cheaper on narrow viewports where the frosted-glass effect is least visible anyway. The bar also carries `box-shadow: var(--shadow-nav)` in addition to its bottom rule.

```css
.topnav {
    position: fixed;
    top: 0; left: 0; right: 0;
    z-index: 300;
    display: flex;
    align-items: center;
    gap: 1.5rem;
    height: var(--nav-height);
    padding: 0 1.25rem;
    background-color: rgba(251, 249, 243, 0.96);
    border-bottom: 1px solid var(--rule);
    box-shadow: var(--shadow-nav);
}
@media (min-width: 700px) {
    .topnav { backdrop-filter: blur(12px) saturate(1.1); }
}
```

Internally the bar is three parts: `.brand` (wordmark in `--font-display`, `700`, `1.15rem`, with a `.brand-accent` span coloured `--accent`) — `.navlinks` (a flex row of `<a>` in `--font-label`, `--text-xs`, `--label-tracking`, uppercase, where `aria-current="page"` holds the underline permanently visible rather than only on hover) — and, optionally, a ghost-bordered icon button (`.nav-theme`, `--radius-sm`) for a theme toggle.

### 8.6 Modals

```css
.modal-overlay {
    position: fixed;
    inset: 0;
    z-index: 500;
    background-color: rgba(27, 24, 19, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
}
.modal-content {
    background-color: var(--paper-raised);
    border-top: 4px solid var(--accent);
    border-radius: 16px;
    box-shadow: var(--shadow-modal);
    max-width: 580px;
    width: 90%;
    animation: modalRise 0.35s cubic-bezier(0.22, 0.61, 0.36, 1) forwards;
}
```

### 8.7 Badges

Badges use muted, desaturated background tints with darker text. The palette is editorial — no bright pops.

| Badge Type | Background | Text |
|---|---|---|
| Book | `#ece4d2` | `#6b5524` |
| Exhibition | `#e7dde4` | `#6d4a62` |
| Fellowship | `#f0e0d4` | `#8a4a23` |
| Teaching | `#dfe5d8` | `#4a5e3c` |
| Media | `#f0dcda` | `#8e3a33` |
| Talk | `#dce4e2` | `#3d5f58` |
| Education | `#ece7d2` | `#6f6224` |

### 8.8 Decorative Elements

#### Stars

Stars are decorative markers, not icons. They appear in subsection headings and the footer. Use the `starSettle` animation on entrance and `starTwinkle` on hover.

#### Rules / Dividers

```css
/* Thin horizontal rule */
.rule-thin {
    width: 100%;
    height: 1px;
    background-color: var(--rule);
}

/* Decorative fading rule (footer) */
.rule-fade {
    width: min(420px, 72%);
    height: 1px;
    background: linear-gradient(to right, transparent, var(--rule-dark) 22%, var(--rule-dark) 78%, transparent);
}
```

#### Accent Left-Border

```css
.accent-left {
    border-left: 3px solid var(--accent);
    padding-left: 1.25rem;
}
```

### 8.9 Page Container

```css
.page {
    max-width: var(--container-max);
    margin: 0 auto;
    padding: calc(var(--nav-height) + 2rem) 1.25rem 4rem;
}
```

Top padding clears the fixed nav bar (`--nav-height` plus breathing room) rather than the page content sitting under it. A `.page-prose` modifier caps width at the content-focused `44rem` measure (§4) for pages that read top-to-bottom as prose rather than as a dashboard.

### 8.10 Masthead

```css
.masthead {
    border-top: 4px solid var(--ink);
    border-bottom: 1px solid var(--rule);
    padding-top: 1rem;
    margin-bottom: 2rem;
}
.masthead .label {
    font-family: var(--font-label);
    font-size: var(--text-sm);
    letter-spacing: var(--label-tracking);
    text-transform: uppercase;
    color: var(--ink-faint);
    display: block;
    margin-bottom: 0.25rem;
}
.masthead h1 {
    font-family: var(--font-display);
    font-size: var(--text-hero);
    margin: 0 0 0.5rem;
    line-height: 1.15;
}
.masthead-rule {
    border: 0;
    border-top: 1px solid var(--rule);
    margin: 0.75rem 0 0;
}
```

```html
<header class="masthead">
  <span class="label">Current pipeline state · canonical entities &amp; relationships</span>
  <h1>The Library</h1>
  <hr class="masthead-rule">
</header>
```

Kicker label, hero title, thin closing rule — the page-top expression of the "Masthead top" border pattern in §5.

### 8.11 Section Heading

```css
.section-head {
    font-family: var(--font-label);
    font-size: var(--text-sm);
    letter-spacing: var(--label-tracking);
    text-transform: uppercase;
    color: var(--ink-soft);
    border-bottom: 1px solid var(--rule);
    padding-bottom: 0.35rem;
    margin: 2.5rem 0 1.25rem;
}
```

Used as the `<h2>` between major regions within a page (e.g. "Pipeline stages", "Breakdown") — a labelled rule, not a display headline.

### 8.12 List Card (`.text-card`)

The list-item variant of the standard card (§8.2): same background, border, radius and shadow, but the padding lives on the inner link rather than the card itself, so the whole row is clickable and the hover lift (§8.2) applies unchanged.

```css
.text-card {
    background: var(--paper-raised);
    border: 1px solid var(--rule);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-paper);
}
.text-card a {
    display: block;
    padding: 1.25rem 1.5rem;
    color: var(--ink);
    text-decoration: none;
}
.text-title { font-family: var(--font-display); font-size: var(--text-lg); display: block; }
.text-meta  { font-family: var(--font-label); font-size: var(--text-sm); color: var(--ink-faint); display: block; margin-top: 0.3rem; }
.text-list  { display: grid; gap: 1rem; list-style: none; padding: 0; margin: 0; }
```

### 8.13 Sort Bar

```css
.sort-bar {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
}
.sort-pill {
    font-family: var(--font-label);
    font-size: var(--text-xs);
    font-weight: 600;
    letter-spacing: var(--label-tracking);
    text-transform: uppercase;
    padding: 0.4rem 0.9rem;
    border: 1.5px solid var(--rule);
    border-radius: var(--radius-md);
    background: transparent;
    color: var(--ink-soft);
    transition: background-color var(--duration-fast) ease,
                color var(--duration-fast) ease,
                border-color var(--duration-fast) ease;
}
.sort-pill:hover {
    background-color: var(--ink);
    color: var(--paper-raised);
    border-color: var(--ink);
}
.sort-pill[aria-pressed="true"] {
    border-color: var(--accent);
    background: var(--accent-wash);
    color: var(--accent-deep);
}
```

`.sort-pill` shares its ruleset with `.chip` (§8.4) — one component, two names. Active state is carried by `aria-pressed="true"`, not a class, so the accessible state and the visual state cannot drift apart.

### 8.14 List Search Input

The search field above a filterable list is the standard input (§8.3) under the alias `.lib-search-input` — same font, padding, radius and focus ring, with no dedicated width or size override of its own.

```html
<input type="text" class="lib-search-input" placeholder="Search library…" aria-label="Search library">
```

### 8.15 Stat Row

A fixed-column-count grid, not an intrinsic `auto-fit`/`auto-fill` reflow — deliberate, so that a row with an incomplete last line leaves an empty track rather than stretching one tile to fill the gap.

```css
.stat-row {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 1rem;
    margin-bottom: 2rem;
}
@media (min-width: 520px)  { .stat-row { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (min-width: 800px)  { .stat-row { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
@media (min-width: 1050px) { .stat-row { grid-template-columns: repeat(5, minmax(0, 1fr)); } }

.stat {
    max-width: 15rem;
    background: var(--paper-raised);
    border: 1px solid var(--rule);
    border-radius: var(--radius-lg);
    padding: 1rem 1.25rem;
    text-align: center;
    box-shadow: var(--shadow-paper);
}
.stat-n { font-family: var(--font-display); font-size: var(--text-h3); display: block; }
.stat-l {
    font-family: var(--font-label);
    font-size: var(--text-xs);
    letter-spacing: var(--label-tracking);
    text-transform: uppercase;
    color: var(--ink-faint);
    margin-top: 0.25rem;
}
```

```html
<section class="stat-row">
  <div class="stat"><span class="stat-n">42</span><span class="stat-l">Documents</span></div>
</section>
```

### 8.16 Progress Bar

```css
.text-progress { display: flex; align-items: center; gap: 0.75rem; }
.text-progress-track {
    height: 4px;
    background: var(--paper-recessed);
    max-width: 12rem;
    flex: 1;
    border-radius: var(--radius-full);
    overflow: hidden;
}
.text-progress-fill {
    height: 100%;
    background: var(--accent);
    transition: width 0.6s var(--ease-primary);
}
.text-progress-pct {
    font-family: var(--font-label);
    font-size: var(--text-sm);
    color: var(--ink-faint);
    white-space: nowrap;
}
```

```html
<span class="text-progress">
  <span class="text-progress-track"><span class="text-progress-fill" style="width: 42%"></span></span>
  <span class="text-progress-pct">42%</span>
</span>
```

### 8.17 Source Badge

```css
.text-source-badge {
    display: inline-block;
    padding: 0.2rem 0.6rem;
    border: 1px solid var(--rule);
    border-radius: var(--radius-sm);
    color: var(--ink-soft);
    font-family: var(--font-label);
    font-size: var(--text-xs);
    background: var(--paper-recessed);
}
```

A small inline provenance tag — attaches a source or evidence label to an entity or claim without competing with the surrounding text.

### 8.18 Icons

Icons are inline SVG. Never an icon font, and never emoji in interface chrome.

```html
<svg viewBox="0 0 24 24" width="16" height="16" fill="none"
     stroke="currentColor" stroke-width="2" stroke-linecap="round"
     stroke-linejoin="round" aria-hidden="true"> … </svg>
```

| Attribute | Value | Why |
|---|---|---|
| `viewBox` | `0 0 24 24` | One coordinate system, so every icon scales and aligns identically |
| `width` / `height` | `16` `16` | Set explicitly; an unsized SVG reflows the line box as it loads |
| `fill` | `none` | These are line drawings, not filled glyphs |
| `stroke` | `currentColor` | The icon inherits the text colour, so it follows the theme with no extra rule |
| `stroke-width` | `2` | Matches the weight of the editorial type at label sizes |
| `stroke-linecap` / `stroke-linejoin` | `round` | Softens the terminals; a square cap reads mechanical against this palette |
| `aria-hidden` | `true` | The icon is decorative — its meaning belongs to the adjacent text |

**Why not an icon font.** A font ships a whole glyph set to draw three arrows, renders as a missing-glyph box when it fails, and inherits font smoothing that has nothing to do with the drawing. It also breaks the local-first guarantee unless vendored, which is a lot of weight for line art. Inline SVG costs nothing at rest, takes `currentColor` for free, and can be read in the template.

**Why not emoji.** Emoji render differently on every platform, carry vendor art direction that will never match a warm editorial palette, and are announced by screen readers with names no one chose. They are somebody else's design system.

**`aria-hidden` is not optional.** An icon beside a label is decorative, and announcing it duplicates the label. An icon that is the *only* content of a control — an icon-only button — still gets `aria-hidden="true"`, with the accessible name supplied by `aria-label` on the control itself. Never leave a control named only by its icon.

**The one exception.** Emoji are permitted where the user chooses them as *content* rather than chrome — the folder-icon picker being the case in point. A user-selected emoji is data, and the design system does not govern the user's data.

As of this writing `artifice-graph` holds to this: 10 inline SVGs, 11 `aria-hidden` attributes, and zero icon-font references.

---

## 9. Focus & Accessibility

### Focus Ring

All interactive elements must have a visible focus indicator:

```css
:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 3px;
}
```

The focus ring is always green (`--accent`), always 2px, with a consistent offset. Never remove focus outlines.

### Contrast Ratios

| Token Pair | Ratio | WCAG Level |
|---|---|---|
| `ink` on `paper` | 14.8:1 | AAA |
| `ink-soft` on `paper` | 7.2:1 | AAA |
| `ink-faint` on `paper` | 5.4:1 | AAA |
| `accent` on `paper` | 5.1:1 | AA (large text AAA) |
| `paper-raised` on `ink` | 14.8:1 | AAA |

### Skip Link

Every app must include a skip link:

```html
<a href="#main-content" class="skip-link">Skip to content</a>
```

```css
.skip-link {
    position: fixed;
    top: 0.75rem;
    left: 0.75rem;
    z-index: 400;
    padding: 0.6rem 1.1rem;
    background-color: var(--ink);
    color: var(--paper-raised);
    font-family: var(--font-label);
    font-size: 0.8rem;
    font-weight: 600;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    transform: translateY(-150%);
    transition: transform 0.25s ease;
}
.skip-link:focus {
    transform: translateY(0);
}
```

### Additional Requirements

- All images must have `alt` text (or `aria-hidden="true"` for decorative images)
- Interactive elements must be keyboard-accessible
- Color is never the sole indicator of state (always pair with text, icon, or shape)
- `aria-expanded`, `aria-current`, `aria-label` used as appropriate

---

## 10. Image Treatment

### Photographic Images

```css
.photo {
    filter: grayscale(100%) sepia(14%);
    transition: filter 0.45s ease, transform 0.45s ease;
}
.photo:hover {
    filter: none;
    transform: scale(1.04);
}
```

Photos start desaturated with a warm sepia tint and "develop" to full color on hover. In dark mode, add `brightness(0.88)` to prevent photos from blowing out.

### Document/Logo Images

On dark backgrounds, place logos on a warm paper plate:

```css
.dark-mode .logo {
    background-color: #ece7dc;
    padding: 0.3rem 0.5rem;
    border-radius: 4px;
}
```

---

## 11. Anti-Patterns

**Never do these:**

1. **No pure black or white.** Always use `--ink` / `--paper` tokens.
2. **No glowy shadows.** No `0 0 20px rgba(...)`, no colored shadows. Shadows are always warm and paper-like.
3. **No rounded-everything.** Radius is calibrated per-component (see Section 5). Inputs get `4px`, cards get `12px`, modals get `16px`. Do not put `16px` radius on an input.
4. **No animation without reduced-motion fallback.** Every animation must be cancellable.
5. **No looping animations** (except star twinkle easter egg). Motion should settle, not spin.
6. **No cold grays.** All grays have a warm brown undertone. The palette never goes blue-gray.
7. **No drop shadows on text.** Depth comes from elevation (card shadows), not text effects.
8. **No gradient backgrounds on cards.** Surfaces are flat paper. Gradients are only used for decorative rules (fading dividers).
9. **No uppercase body text.** Uppercase is reserved for labels, buttons, nav, and meta. Titles and body are sentence-case.
10. **No transparent/glassmorphism cards.** Surfaces are opaque paper. Backdrop-blur is acceptable only on navigation bars.

---

## 12. Quick-Reference: CSS Custom Properties

```css
:root {
    /* Paper & Ink */
    --paper: #f6f3ea;
    --paper-raised: #fbf9f3;
    --paper-recessed: #efebdf;
    --ink: #1b1813;
    --ink-soft: #4b463d;
    --ink-faint: #635e51;
    --rule: #ddd6c6;
    --rule-dark: #45413a;

    /* Accent */
    --accent: #2f7d45;
    --accent-deep: #1f5a31;
    --accent-wash: rgba(47, 125, 69, 0.07);
    --gold: #bf9b30;

    /* Semantic (status, not part of core identity) */
    --success: #455f2b;
    --warning: #7c5e1a;
    --error: #a8322b;

    /* Typography */
    --font-display: 'Playfair Display', Georgia, serif;
    --font-body: 'Libre Baskerville', Georgia, serif;
    --font-label: 'Archivo', 'Franklin Gothic Medium', 'Arial Narrow', sans-serif;
    --font-mono: 'SFMono-Regular', 'Consolas', 'Liberation Mono', 'Menlo', monospace;

    /* Fluid Scale */
    --text-xs: 0.72rem;
    --text-sm: 0.8rem;
    --text-base: 1.0625rem;
    --text-lg: clamp(1.15rem, 1.05rem + 0.4vw, 1.3rem);
    --text-h3: clamp(1.35rem, 1.2rem + 0.8vw, 1.8rem);
    --text-h2: clamp(1.9rem, 1.5rem + 2vw, 2.8rem);
    --text-hero: clamp(2.6rem, 1.6rem + 5.5vw, 5.25rem);

    /* Labels */
    --label-tracking: 0.16em;

    /* Depth */
    --shadow-paper: 0 1px 2px rgba(27,24,19,0.05), 0 10px 28px -14px rgba(27,24,19,0.18);
    --shadow-lifted: 0 2px 4px rgba(27,24,19,0.07), 0 22px 44px -18px rgba(27,24,19,0.28);
    --shadow-nav: 0 6px 24px -16px rgba(27,24,19,0.3);
    --shadow-modal: 0 4px 24px -4px rgba(27,24,19,0.35);

    /* Radius */
    --radius-sm: 4px;
    --radius-md: 8px;
    --radius-lg: 12px;
    --radius-xl: 16px;
    --radius-full: 9999px;

    /* Spacing */
    --space-1: 2px;
    --space-2: 4px;
    --space-3: 8px;
    --space-4: 12px;
    --space-5: 16px;
    --space-6: 20px;
    --space-7: 24px;
    --space-8: 28px;
    --space-9: 32px;
    --space-10: 40px;
    --space-11: 48px;
    --space-12: 88px;

    /* Motion */
    --ease-primary: cubic-bezier(0.22, 0.61, 0.36, 1);
    --duration-instant: 100ms;
    --duration-fast: 250ms;
    --duration-normal: 300ms;
    --duration-slow: 450ms;
    --duration-glacial: 700ms;

    /* Layout */
    --nav-height: 56px;
    --container-max: 1200px;
}

/* Dark Mode Override */
@media (prefers-color-scheme: dark) {
    :root {
        --paper: #161310;
        --paper-raised: #1f1b16;
        --paper-recessed: #100e0b;
        --ink: #e8e2d3;
        --ink-soft: #beb5a3;
        --ink-faint: #a39a88;
        --rule: #38332b;
        --rule-dark: #5b554a;
        --accent: #4aa066;
        --accent-deep: #7cc492;
        --accent-wash: rgba(74, 160, 102, 0.12);
        --gold: #bf9b30;
        --success: #67a04b;
        --warning: #e4cb81;
        --error: #dd5555;
        --shadow-paper: 0 1px 2px rgba(0,0,0,0.4), 0 10px 26px -14px rgba(0,0,0,0.6);
        --shadow-lifted: 0 2px 4px rgba(0,0,0,0.5), 0 22px 42px -16px rgba(0,0,0,0.7);
        --shadow-nav: 0 6px 24px -16px rgba(0,0,0,0.5);
        --shadow-modal: 0 4px 24px -4px rgba(0,0,0,0.6);
    }
}
```

### Token Architecture

`packages/shared-ui/shared_ui/assets/tokens.css` is the canonical source of truth for every design token in this document. There is no app-local copy of the token file any more. ArtificeGraph serves the canonical file over HTTP from a dedicated `/shared` route — mounted from `packages/shared-ui/shared_ui/assets` in `apps/artifice-graph/src/artifice_graph/web/server.py` and linked as `/shared/tokens.css` in `apps/artifice-graph/src/artifice_graph/web/templates/base.html` — so the apps that consume it always read the single file and there is nothing to keep in sync. Do not reintroduce a per-app `tokens.css`; any new token belongs in `packages/shared-ui/shared_ui/assets/tokens.css` and only then. (The canonical file activates dark mode through two independent paths — an explicit `[data-theme="dark"]` attribute and an OS-level `prefers-color-scheme` query, guarded so `[data-theme="light"]` can still override it — producing the same palette either way. The quick-reference block above keeps the simpler single-selector form for legibility; the real file is authoritative on the activation mechanism.)

Domain-specific colours — entity-type accents, the register taxonomy palette — deliberately live app-local (for example `apps/artifice-graph/src/artifice_graph/web/static/entity-colors.css`, served from the ordinary `/static` route). They are *not* suite tokens: the other three apps have no use for an entity taxonomy or a register scheme, so those colours have no place in the canonical token file. Keep them where the domain lives; keep them out of `packages/shared-ui/shared_ui/assets/tokens.css`.

The label/UI-font token is `--font-label`. The earlier `sans`-suffixed name for this token is retired and must not reappear — the canonical file declares only `--font-label`, and any reference to the retired name is drift to be corrected.

---

## 13. Source Attribution

This design system is derived from the personal website of Dr Maurice J. Casey at [mauricejcasey.com](https://www.mauricejcasey.com). The website is a hand-crafted static HTML/CSS/JS portfolio with no frameworks or build tools. The original design concept is described in `style.css` as:

> *The New Masses Style — 1920s/30s Radical Newspaper Aesthetic, Refined.*
> *Editorial design system: warm paper surfaces, ink-and-red palette, fluid serif display type, grotesque labels, restrained motion.*

The "red" referenced in the original has been replaced by Esperanto green (`#2f7d45`), reflecting the socialist internationalism Casey writes about. The palette is otherwise faithfully preserved.

---

*Version 1.0 — Derived from `public_history` repo, July 2026.*

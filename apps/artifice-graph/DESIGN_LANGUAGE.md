# LudwigLang Design Language

A design-system guide for building apps that share LudwigLang's visual identity.
The reference implementation lives in the same repo — consult `web/static/tokens.css`,
`web/static/app.css`, and the page-specific CSS files for exact selectors and values.

---

## 1. Design Philosophy

- **Offline-first, print-inflected.** The palette and typography evoke 20th-century
  editorial print (cream paper, dark ink, serif body text). Every visual choice should
  feel like it belongs in a physical book or archival document.
- **Restrained motion.** Animations are brief (0.12–0.6 s) and serve a tactile purpose
  (ink drying, paper accepting a stamp). The global `[data-reduce-motion]` guard kills
  all motion.
- **No icon fonts, no emoji in UI.** All icons are inline SVGs.

---

## 2. CSS Token System

All design tokens live in `tokens.css` as CSS custom properties on `:root`.
Consume them exclusively through these variables — never hardcode colour, type,
or spacing values.

### 2.1 Paper & Ink (Light Theme)

| Token | Value | Usage |
|---|---|---|
| `--paper` | `#f6f3ea` | Page background |
| `--paper-raised` | `#fbf9f3` | Card / panel / modal background |
| `--paper-recessed` | `#efebdf` | Pressed / inset surface |
| `--ink` | `#1b1813` | Body text |
| `--ink-soft` | `#4b463d` | Secondary text, labels |
| `--ink-faint` | `#716c5e` | Muted metadata (AA on paper) |
| `--rule` | `#ddd6c6` | Borders, dividers |
| `--rule-dark` | `#45413a` | Strong borders, button outlines |

### 2.2 Accent & Gold

| Token | Value | Usage |
|---|---|---|
| `--accent` | `#2f7d45` | Links, active states, primary actions (Esperanto green) |
| `--accent-deep` | `#1f5a31` | Hover states, link colour |
| `--accent-wash` | `rgba(47,125,69,0.07)` | Subtle background tint for active/selected items |
| `--gold` | `#bf9b30` | Stars, highlights, mid-progress states |

### 2.3 Dark Theme Override

Applied via `@media (prefers-color-scheme: dark)` or explicit `[data-theme="dark"]`.
Components never need dark-mode rules — they just reference the token variables.

| Token | Dark Value |
|---|---|
| `--paper` | `#1c1a16` |
| `--paper-raised` | `#24211b` |
| `--paper-recessed` | `#171511` |
| `--ink` | `#ece7db` |
| `--accent` | `#4a9e63` |

### 2.4 Typography

| Token | Value / Family |
|---|---|
| `--font-display` | `'Playfair Display', 'Georgia', serif` |
| `--font-body` | `'Libre Baskerville', 'Georgia', serif` |
| `--font-sans` | `'Archivo', 'Franklin Gothic Medium', 'Arial Narrow', sans-serif` |
| `--label-tracking` | `0.16em` — letter-spacing for uppercase labels |

Fluid scale (clamp-based):

| Token | Size |
|---|---|
| `--text-sm` | `0.875rem` |
| `--text-base` | `1.0625rem` |
| `--text-lg` | `clamp(1.15rem, 1.05rem + 0.4vw, 1.3rem)` |
| `--text-h3` | `clamp(1.35rem, 1.2rem + 0.8vw, 1.8rem)` |
| `--text-h2` | `clamp(1.9rem, 1.5rem + 2vw, 2.8rem)` |
| `--text-hero` | `clamp(2.6rem, 1.6rem + 5.5vw, 5.25rem)` |

### 2.5 Shadows

| Token | Value |
|---|---|
| `--shadow-paper` | `0 1px 2px rgba(27,24,19,0.05), 0 10px 28px -14px rgba(27,24,19,0.18)` |
| `--shadow-lifted` | `0 2px 4px rgba(27,24,19,0.07), 0 22px 44px -18px rgba(27,24,19,0.28)` |

### 2.6 Word-Status Colours (Reading View)

Five-rung progression from "new" to "known". Drawn from the house palette.

| State | Wash | Underline |
|---|---|---|
| `--w-new` | `rgba(47,125,69,0.13)` green | `var(--accent)` |
| `--w-unfamiliar` | `rgba(191,155,48,0.28)` gold | `var(--gold)` |
| `--w-learning` | `rgba(191,155,48,0.12)` faint gold | `rgba(191,155,48,0.55)` |
| `--w-familiar` | `transparent` | gold–green blend |
| `--w-known` | `transparent` | none |
| `--w-ignored` | `transparent` | none; text in `--ink-faint` |

### 2.7 Register Taxonomy Colours

Eight archival-register colours for classification badges:

| Token | Colour |
|---|---|
| `--reg-bureaucratic` | `#5b6b73` |
| `--reg-underground` | `var(--accent)` |
| `--reg-personal` | `#a6733b` |
| `--reg-scholarly` | `#6a6a86` |
| `--reg-journalistic` | `#c1652b` |
| `--reg-epistolary` | `#7d5a8c` |
| `--reg-legal` | `#3f6f8c` |
| `--reg-poetic` | `#8c3f5a` |

---

## 3. Base Chrome

### 3.1 Top Navigation (`.topnav`)

- Fixed/sticky `56px` bar with `backdrop-filter: blur(12px)` on wider screens.
- `.brand` uses `--font-display` in `1.15rem` weight `700`.
- `.brand-accent` span inside it gets `--accent` colour.
- `.navlinks a` are `--font-sans`, `0.72rem`, `--label-tracking`, uppercase.
  Each has a green underline (`::after`) that `scaleX(0 → 1)` on hover.
  Active page gets `[aria-current]` attribute → underline always visible.
- `.nav-search` is an inline form with a search input; hidden on narrow screens.

### 3.2 Page Container (`.page`)

```css
.page { max-width: 46rem; margin: 0 auto; padding: 2rem 1.25rem 4rem; }
```

Reading page overrides to `72rem` when `.read-layout` is present.

### 3.3 Masthead (`.masthead`)

- Thick bottom border (`4px solid var(--ink)`).
- `h1` inside uses `--font-display` at `--text-h2`.
- `.label` class for the small uppercase label above the title.

### 3.4 Section Heading (`.section-head`)

`--font-sans`, `--text-sm`, `--label-tracking`, uppercase, `--ink-soft` colour,
with a bottom rule.

---

## 4. Component Patterns

### 4.1 Text Card (`.text-card`)

```html
<li class="text-card">
  <a href="...">
    <span class="text-title">Card title</span>
    <span class="text-meta">Metadata line</span>
  </a>
</li>
```

- Background: `--paper-raised`, border: `--rule`, shadow: `--shadow-paper`.
- Link hover shows a green `outline: 2px solid var(--accent)`.
- `.text-title`: `--font-display`, `--text-lg`, `display: block`.
- `.text-meta`: `--font-sans`, `--text-sm`, `--ink-faint`, `display: block`.
- `.text-card` also supports `position: relative` for action menus.
- Cards in a list are gridded via `.text-list { display: grid; gap: 0.75rem; }`.

### 4.2 Buttons

**Base pattern** (`.modal-btn`, `.lib-action-btn`, `.wp-btn`, `.narr-btn`, `.sort-pill`):

```css
font-family: var(--font-sans);
font-size: var(--text-sm);
letter-spacing: var(--label-tracking);
text-transform: uppercase;
padding: 0.5rem 0.9rem;
border: 1px solid var(--rule-dark);
background: var(--paper);
color: var(--ink);
cursor: pointer;
transition: background 0.12s, color 0.12s, border-color 0.12s;
```

Hover → `border-color: var(--accent); color: var(--accent-deep);`

**Primary variant** (`.modal-btn-primary`): inverted — `background: var(--ink); color: var(--paper-raised); border-color: var(--ink);`
Hover → `background: var(--accent-deep);`

**Import button** (`.lib-import-btn`): pre-bordered accent — `border-color: var(--accent); color: var(--accent-deep);`
Hover → `background: var(--accent); color: var(--paper-raised);`

### 4.3 Sort Bar (`.sort-bar`)

A `flex; gap: 0.35rem; flex-wrap: wrap` row of `.sort-pill` buttons.
Active pill gets `[aria-pressed="true"]` → `border-color: var(--accent); background: var(--accent-wash); color: var(--accent-deep);`.

### 4.4 Search Input (`.lib-search-input`)

```css
width: 100%;
max-width: 28rem;
font-family: var(--font-body);
font-size: var(--text-base);
padding: 0.55rem 0.8rem;
border: 1px solid var(--rule-dark);
background: var(--paper);
color: var(--ink);
```

Focus: `outline: 2px solid var(--accent); outline-offset: 1px;`

### 4.5 Modal

```html
<div class="modal-backdrop" hidden>
  <div class="modal-card" role="dialog" aria-modal="true">
    <h3 class="modal-title">Title</h3>
    <p class="modal-body">Content...</p>
    <div class="modal-actions">
      <button class="modal-btn">Cancel</button>
      <button class="modal-btn modal-btn-primary">Confirm</button>
    </div>
  </div>
</div>
```

- `.modal-backdrop`: `position: fixed; inset: 0; z-index: 400;` with semi-transparent dark background, flex-centers its child.
- `.modal-card`: `--paper-raised`, `--shadow-lifted`, `max-width: 26rem`.
- `.modal-title`: `--font-display`, `--text-h3`.
- `.modal-actions`: `display: flex; gap: 0.75rem; justify-content: flex-end;`

### 4.6 Stat Row (`.stat-row`)

```html
<section class="stat-row">
  <div class="stat"><span class="stat-n">42</span><span class="stat-l">label</span></div>
  ...
</section>
```

- `display: flex; gap: 1rem; flex-wrap: wrap;`
- Each `.stat`: `--paper-raised`, `border: 1px solid var(--rule); padding: 0.75rem 1.25rem; min-width: 7rem; text-align: center;`
- `.stat-n`: `--font-display`, `--text-h3`, `display: block`.
- `.stat-l`: `--font-sans`, `--text-sm`, `--label-tracking`, uppercase, `--ink-faint`.

### 4.7 Folder Section

Used on the home page for grouped texts. Structure:

```html
<div class="lib-folder" data-folder-name="Name" data-open="true">
  <button class="lib-folder-header" aria-expanded="true">
    <span class="lib-folder-icon"><!-- SVG or emoji --></span>
    <span class="lib-folder-name">Name</span>
    <span class="lib-folder-count">(N)</span>
    <span class="lib-folder-chevron"><!-- chevron SVG --></span>
  </button>
  <div class="lib-folder-body">
    <ul class="text-list">...</ul>
  </div>
</div>
```

- Header has `border-left: 3px solid var(--accent)` and `background: var(--accent-wash)`.
- Body uses `max-height` transition for accordion open/close.
- Chevron rotates -90° when collapsed.

### 4.8 Progress Bar

```html
<span class="text-progress">
  <span class="text-progress-track">
    <span class="text-progress-fill" style="width: 42%"></span>
  </span>
  <span class="text-progress-pct">42% known</span>
</span>
```

- Track: `height: 3px; background: var(--paper-recessed); max-width: 12rem;`
- Fill: `background: var(--accent); transition: width 0.6s ease-out;`

### 4.9 Source Badge

```html
<span class="text-source-badge">Source name</span>
```

- `padding: 0.1rem 0.45rem; border: 1px solid var(--rule); border-radius: 2px; color: var(--ink-soft);`

---

## 5. Word Panel (Reading View)

The `.read-layout` uses a two-column grid: `2fr 1fr`.

The `.read-panel` in the right column shows word details:
- `.wp-term`: word in `--font-display` at `--text-h3`.
- `.wp-lemma`: lemma line with `--font-sans`, `--text-sm`, `--ink-faint`.
- `.wp-meta-label`: uppercase label with `--font-sans`, `--text-sm`, bottom rule.
- `.wp-gloss`: body font for the gloss.
- `.wp-etymology`: italic body text in `--ink-soft`.
- `.wp-register-tag`: small uppercase badge in `--tint-wash`.
- `.wp-states`: 2-column grid of state buttons.

---

## 6. Animation Conventions

| Animation | Duration | Trigger |
|---|---|---|
| `state-pulse-flash` | 0.5s | Word state change |
| `ink-dry` | 0.4s | Word state change (tactile) |
| `ink-create` | 0.5s | New word creation (LingQ moment) |

All motion is disabled when `[data-reduce-motion]` or `prefers-reduced-motion: reduce`
is active. The guard in `app.css` uses `!important` on `animation-duration: 0.001ms`.

---

## 7. Responsive Breakpoints

| Name | Width | Behaviour |
|---|---|---|
| Narrow | `max-width: 48rem` | Read layout stacks single column; panel `position: static` |
| Narrow | `max-width: 720px` | Nav search hidden |
| Narrow | `max-width: 700px` | `.topnav` backdrop-filter removed, nav-search hidden |
| Wide | `min-width: 700px` | Topnav gets backdrop-filter blur |

---

## 9. Icons

- Never use icon fonts or emoji in UI chrome. All icons are inline SVGs with
  `aria-hidden="true"`.
- SVG attributes: `viewBox="0 0 24 24"`, `width="16" height="16"`,
  `fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"
  stroke-linejoin="round"`.
- Exception: the folder icon picker allows emoji as user-chosen folder icons
  (rendered as `<span class="lib-folder-icon-emoji">`).

---

## 10. HTML / Template Conventions

- FastAPI + Jinja2. Base template: `templates/base.html`.
- Each page extends base and provides `{% block title %}`, `{% block head %}`,
  `{% block content %}`, `{% block scripts %}`.
- Asset cache-busting via `?v={{ asset_v }}` on every CSS/JS link.
- Theme and reduce-motion state stamped on `<html>` via middleware
  (`data-theme` / `data-reduce-motion`).
- All JavaScript is vanilla ES5-compatible (no framework, no transpiler),
  wrapped in IIFEs. Modules expose themselves on `window`.
- `[hidden] { display: none !important; }` global — components use `.hidden` attribute.

---

## 11. File & Naming Conventions

| File | Purpose |
|---|---|
| `tokens.css` | All CSS custom properties / design tokens |
| `app.css` | Base chrome, shared components, reset, utilities |
| `{feature}.css` | Page- or feature-specific styles (e.g. `reading.css`, `library.css`) |
| `{feature}.js` | Per-page behaviour (IIFE-wrapped) |
| `templates/{feature}.html` | Jinja2 template per route |

---

## 12. Key Do's and Don'ts

- **Do** reference token variables everywhere. Never hardcode colours.
- **Do** use `--font-sans` + `--label-tracking` + `text-transform: uppercase` for labels,
  buttons, and navigation.
- **Do** use `--font-display` for headings and card titles.
- **Do** use `--font-body` for running text and form inputs.
- **Do** keep animations under 0.6s and motion-reduce-safe.
- **Don't** use icon fonts or emoji in UI (except the folder-icon picker).
- **Don't** hardcode dark-mode rules — the token system handles it.
- **Don't** use a JS framework. Vanilla JS, IIFE-wrapped, no transpiler.
- **Don't** add new font dependencies. The three font stacks have local fallbacks.

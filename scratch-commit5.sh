#!/usr/bin/env bash
set -e
export PATH="$HOME/.local/bin:$PATH"
cd ~/projects/artifice-suite || exit 1
rm -f scratch-gate.sh

echo "=== reuse lint after removing scratch ==="
reuse lint 2>&1 | grep -iE 'compliant|Missing licenses' | head -3

git add -A
git commit -F - <<'EOF'
feat(ui): port artifice-draft to Jinja and add a shared masthead

First stage of the cross-app UI parity work (Step 9). The three apps
described throughout the plan as "static" were never static — each read
index.html and ran str.replace() on it before serving. This replaces that
hand-rolled substitution with a real template engine in one app, as a pilot
before ocr and transcribe follow.

- graph: FileSystemLoader -> ChoiceLoader over PackageLoaders. The old
  loader took a __file__-relative path, which breaks in a frozen bundle;
  PackageLoader resolves through importlib. Fixed before the pattern was
  copied into three more apps. graph's hatchling backend is untouched.
- shared-ui becomes a template provider as well as an asset provider, with
  shared_ui/templates/_masthead.html and a matching masthead.css. The
  shared unit is the chrome, not a page skeleton — the apps' bodies differ
  too much for one skeleton, the masthead does not. Contract: brand_accent,
  brand_tagline, nav_items, active_tab, show_theme_toggle.
- draft: templates/{base,index,about}.html, a real /about route, and the
  stale static/index.html deleted — it was still served at 200 and would
  have drifted into a second answer to what the app looks like.
- ci.yml: the wheel job's content assertion covered only artifice-ocr. It
  now also asserts shared-ui ships _masthead.html and masthead.css, that
  draft ships its three templates, and that draft's static/index.html is
  absent. Templates missing from a wheel fail only at runtime in an
  installed app, which nothing else here exercises.

Two defects found by measuring the rendered page, neither visible in tests,
served bytes, or the diff:

- draft carried two overlapping headers. The old <header class="masthead">
  was never removed, so its h1 painted directly over the new brand link at
  the same coordinates and the nav sat behind it. It looked almost right in
  a screenshot and was wrong in the DOM.
- masthead.css shipped an SPDX header in HTML comment syntax. CSS tolerates
  <!-- --> as legacy CDO/CDC tokens but parses the text between them as
  CSS, consuming everything up to the first { — which swallowed the whole
  .topnav rule. The masthead rendered display:block, position:static, no
  padding, no height, brand and nav stacked and flush to the edge, while
  every later rule applied normally. reuse lint passes on it, because it
  checks the tags are present rather than that they are valid comment
  syntax for the file type. Part V now records this.

Draft's theme toggle is deliberately still absent: it also lacks a
[data-theme="dark"] accent block, so a toggle without that half-works.

draft 225, graph 169. reuse lint compliant, token parity no drift.
Masthead verified from draft's live DOM: display flex, position fixed,
height 56px, padding 20px, brand and nav on one row, .brand-accent
rgb(137,34,84) = draft's --accent.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XwcCgLwkYovtSzU63oPYvN
EOF

git push origin phase6-byom-screen
git log --oneline -1
git status -sb

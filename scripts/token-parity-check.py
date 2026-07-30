#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

"""Token parity guard: compare design-system reference tokens against runtime tokens,
and app-local token re-declarations against the canonical runtime tokens.

Compares only light-mode values to avoid false drift against dark-mode overrides.
Exempts the four fluid-typography tokens (--text-lg, --text-h3, --text-h2, --text-hero)
because the runtime uses clamp() while the reference records a static specimen from inside
that range.  For those four, the script validates that the reference's fixed rem value
falls inside the runtime's clamp range — it does not simply skip them.

The app-local check scans every ``apps/*/src/*/web/static/**/*.css``, extracts light-mode
custom-property declarations, and compares each one that shadows a canonical token name
against the canonical value in ``packages/shared-ui/shared_ui/assets/tokens.css``.
App-only tokens (names with no canonical counterpart) are not flagged — adding new
tokens is fine; redefining a canonical token to a different value is the defect.

Exit: 0 if all tokens agree, 1 if drift or missing tokens are found anywhere.
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

RUNTIME_TOKENS_FILE = REPO_ROOT / "packages" / "shared-ui" / "shared_ui" / "assets" / "tokens.css"
REF_TOKEN_DIR = REPO_ROOT / "design-system" / "tokens"

# Typography tokens defined as clamp() in runtime, fixed rem in reference.
# The reference value must fall inside the clamp range.
# Rationale: a static specimen design-system cannot express a fluid clamp(),
# so it records a fixed value from inside that range.  This is correct —
# neither side should be "fixed" to match the other.
FLUID_EXEMPT_NAMES = {
    "--text-lg",
    "--text-h3",
    "--text-h2",
    "--text-hero",
}

# ---- dark / duplicate block stripping ---------------------------------------

_BLOCK_OPENER = re.compile(
    r"(?:"
    r"@media\s*\(\s*prefers-color-scheme\s*:\s*dark\s*\)"
    r"|@media\s*\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)"
    r"|\[data-theme\s*=\s*[\"']dark[\"']\]"
    r"|\[data-theme\s*=\s*[\"']light[\"']\]"
    r")\s*\{"
)

_IMPORT_LINE = re.compile(r"@import\s+[^;]+;")


def strip_dark_blocks(css: str) -> str:
    """Remove dark-mode, light-theme explicit blocks, and reduced-motion blocks.

    Also removes ``@import`` lines, which carry no tokens.
    """
    css = _IMPORT_LINE.sub("", css)

    result: list[str] = []
    i = 0
    while i < len(css):
        m = _BLOCK_OPENER.search(css, i)
        if not m:
            result.append(css[i:])
            break
        # Keep the text before the block opener.
        result.append(css[i : m.start()])
        # Skip the block — find its matching closing brace.
        depth = 1
        j = m.end()
        while j < len(css) and depth > 0:
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
            j += 1
        i = j
    return "".join(result)


# ---- token extraction -------------------------------------------------------

_TOKEN_DECL = re.compile(r"(--[\w-]+)\s*:\s*([^;]*);")


def extract_tokens(css: str) -> dict[str, str]:
    """Return ``{name: raw_value}`` for every ``--name: value;`` declaration."""
    return {m.group(1): m.group(2).strip() for m in _TOKEN_DECL.finditer(css)}


# ---- normalisation ----------------------------------------------------------

_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def normalise(value: str) -> str:
    """Collapse whitespace, strip comments, lower-case, unify quotes.

    Also collapses whitespace around commas so that e.g. ``rgba(47, 125, 69, 0.07)``
    and ``rgba(47,125,69,0.07)``, or multi-value shadow lists separated by commas,
    compare equal.

    Strips all remaining quotes as the final step so that ``'Georgia'``,
    ``\"Georgia\"`` and bare ``Georgia`` inside a font stack compare equal.
    """
    value = _COMMENT_RE.sub("", value)
    value = " ".join(value.split())
    value = value.lower()
    value = value.replace("'", '"')
    # Collapse all whitespace around commas to a single comma (no spaces).
    value = re.sub(r"\s*,\s*", ",", value)
    # Strip remaining quotes — font-family name quoting (single, double, or
    # bare) must not cause false drift.
    value = value.replace('"', "")
    return value


# ---- clamp-range validation for exempted fluid tokens -----------------------

_CLAMP_RE = re.compile(
    r"clamp\(\s*([\d.]+)rem\s*,\s*[\d.]+\s*rem\s*\+\s*[\d.]+\s*vw\s*,\s*([\d.]+)rem\s*\)"
)

_REF_REM_RE = re.compile(r"([\d.]+)rem")


def _parse_ref_rem(value: str):
    """Return ``float`` rem value from e.g. ``1.25rem``, or ``None``."""
    m = _REF_REM_RE.search(value)
    return float(m.group(1)) if m else None


def check_clamp_range(name: str, runtime_val: str, ref_val: str) -> tuple[bool, str]:
    """Verify the reference's fixed rem falls inside the runtime clamp range.

    Returns ``(ok, error_message_if_not)``.
    """
    ref_num = _parse_ref_rem(ref_val)
    if ref_num is None:
        return False, f"{name}: cannot parse reference value '{ref_val}'"

    m = _CLAMP_RE.search(runtime_val)
    if not m:
        return False, f"{name}: cannot parse clamp in runtime value '{runtime_val}'"

    lo, hi = float(m.group(1)), float(m.group(2))
    if lo <= ref_num <= hi:
        return True, ""

    return False, (
        f"{name}: reference value {ref_num}rem falls OUTSIDE "
        f"clamp range [{lo}rem, {hi}rem]\n"
        f"  runtime:   {runtime_val}\n"
        f"  reference: {ref_val}"
    )


# ---- app-local token check ---------------------------------------------------

APP_CSS_GLOB = "apps/*/src/*/web/static/**/*.css"


def _find_app_css_files() -> list[Path]:
    """Return every CSS file under an app's web static directory.

    The glob is ``apps/*/src/*/web/static/**/*.css`` — a fifth app, or a
    second stylesheet inside an existing app, is picked up without editing
    the script.
    """
    return sorted(REPO_ROOT.glob(APP_CSS_GLOB))


def _check_app_tokens(canonical: dict[str, str]) -> int:
    """Compare app-local CSS tokens against the canonical runtime tokens.

    For each CSS file found, extracts light-mode tokens, then compares every
    local token that shadows a canonical name.  Tokens with no canonical
    counterpart are left alone — they are app-specific domain vocabulary,
    not suite-wide design tokens.

    Returns the number of drifted tokens (0 = clean).
    """
    total_errors = 0

    for css_path in _find_app_css_files():
        css = css_path.read_text()
        css = strip_dark_blocks(css)
        local_tokens = extract_tokens(css)

        if not local_tokens:
            continue

        # Only compare tokens that shadow a canonical name.
        shadowed = {n for n in local_tokens if n in canonical}
        if not shadowed:
            continue

        file_errors: list[str] = []
        matched = 0

        for name in sorted(shadowed):
            canon_val = canonical[name]
            local_val = local_tokens[name]

            n_canon = normalise(canon_val)
            n_local = normalise(local_val)

            if n_canon != n_local:
                file_errors.append(
                    f"DRIFT: {name}\n"
                    f"  canonical:  {canon_val}\n"
                    f"  app-local:  {local_val}"
                )
            else:
                matched += 1

        relative = css_path.relative_to(REPO_ROOT)
        print(f"\n  {relative} — {len(shadowed)} canonical tokens declared")

        if file_errors:
            print(f"    {matched} agree, {len(file_errors)} DRIFTED:")
            for e in file_errors:
                for line in e.split("\n"):
                    print(f"      {line}")
            total_errors += len(file_errors)
        else:
            print(f"    {matched} agree — clean")

    return total_errors


# ---- main -------------------------------------------------------------------

def _load_runtime_tokens() -> dict[str, str]:
    css = RUNTIME_TOKENS_FILE.read_text()
    css = strip_dark_blocks(css)
    return extract_tokens(css)


def _load_ref_tokens() -> dict[str, str]:
    css_parts: list[str] = []
    for f in sorted(REF_TOKEN_DIR.glob("*.css")):
        css_parts.append(f.read_text())
    css = "\n".join(css_parts)
    css = strip_dark_blocks(css)
    return extract_tokens(css)


def main() -> int:
    runtime = _load_runtime_tokens()
    reference = _load_ref_tokens()

    # ── Check 1: design-system reference vs runtime tokens ─────────
    errors: list[str] = []
    matched = 0
    exempt_ok = 0

    for name in sorted(runtime):
        rt_val = runtime[name]

        if name not in reference:
            errors.append(
                f"MISSING: '{name}' present in runtime "
                f"({RUNTIME_TOKENS_FILE}) but absent from reference"
            )
            continue

        ref_val = reference[name]

        if name in FLUID_EXEMPT_NAMES:
            ok, msg = check_clamp_range(name, rt_val, ref_val)
            if not ok:
                errors.append(msg)
            else:
                exempt_ok += 1
            continue

        n_rt = normalise(rt_val)
        n_ref = normalise(ref_val)
        if n_rt != n_ref:
            errors.append(
                f"DRIFT: {name}\n"
                f"  runtime:   {rt_val}\n"
                f"  reference: {ref_val}"
            )
            continue

        matched += 1

    # Reference-only tokens are fine (extended scales, aliases).
    ref_only = set(reference) - set(runtime)
    if ref_only:
        print(f"  ({len(ref_only)} reference-only tokens — aliases/extended scales, OK)")

    print(
        f"Token parity: {matched} agree, {exempt_ok} exempted (clamp range verified)"
    )
    print(f"  exempted: {', '.join(sorted(FLUID_EXEMPT_NAMES))}")

    if errors:
        print(f"\n{len(errors)} ERROR(S):")
        for e in errors:
            print(f"  {e}")
        exit_code = 1
    else:
        print("  No drift detected.")
        exit_code = 0

    # ── Check 2: app-local tokens vs canonical runtime tokens ─────
    print("\n--- App-local token check ---")
    print(f"  canonical source: {RUNTIME_TOKENS_FILE}")
    app_errors = _check_app_tokens(runtime)

    if app_errors:
        print(f"\n{app_errors} ERROR(S) total across apps")
        exit_code = 1
    else:
        print("\n  All apps clean — no canonical tokens redefined to a different value.")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())

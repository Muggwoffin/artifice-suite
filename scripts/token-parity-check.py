#!/usr/bin/env python3
"""Token parity guard: compare design-system reference tokens against runtime tokens.

Compares only light-mode values to avoid false drift against dark-mode overrides.
Exempts the four fluid-typography tokens (--text-lg, --text-h3, --text-h2, --text-hero)
because the runtime uses clamp() while the reference records a static specimen from inside
that range.  For those four, the script validates that the reference's fixed rem value
falls inside the runtime's clamp range — it does not simply skip them.

Exit: 0 if tokens agree, 1 if drift or missing tokens are found.
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
    """
    value = _COMMENT_RE.sub("", value)
    value = " ".join(value.split())
    value = value.lower()
    value = value.replace("'", '"')
    # Collapse all whitespace around commas to a single comma (no spaces).
    value = re.sub(r"\s*,\s*", ",", value)
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
        return 1

    print("  No drift detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

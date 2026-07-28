#!/usr/bin/env bash
#
# build-wheel.sh — clean-build a wheel for one Artifice app.
#
# Problem: the Python build-backend (setuptools) reuses files left in build/
# from a previous build.  A deleted module stays in the wheel because it is
# still on disk under build/lib/<package>/ — an invisible packaging bug that
# only surfaces in the built artifact.  Clearing build/ *and* dist/ first
# makes it impossible to forget.
#
# Usage: scripts/build-wheel.sh <app-name>
#
#   scripts/build-wheel.sh artifice-ocr
#   scripts/build-wheel.sh artifice-draft

set -euo pipefail

APP_NAME="${1:?Usage: $0 <app-name>}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$REPO_ROOT/apps/$APP_NAME"

die() { printf 'error: %s\n' "$*" >&2; exit 1; }

[ -d "$APP_DIR" ] || die "no app directory found at $APP_DIR"
[ -f "$APP_DIR/pyproject.toml" ] || die "$APP_DIR/pyproject.toml not found"

# ── Clean previous build artefacts ──────────────────────────────────────
if [ -d "$APP_DIR/build" ]; then
    rm -rf "$APP_DIR/build"
    echo "[clean] removed $APP_DIR/build"
fi
if [ -d "$APP_DIR/dist" ]; then
    rm -rf "$APP_DIR/dist"
    echo "[clean] removed $APP_DIR/dist"
fi

# ── Build ───────────────────────────────────────────────────────────────
echo "[build] building $APP_NAME wheel..."
(
    cd "$APP_DIR"
    uv run --with build python -m build --wheel 2>&1
)

# ── Verify ───────────────────────────────────────────────────────────────
WHEEL_COUNT=$(find "$APP_DIR/dist" -name '*.whl' 2>/dev/null | wc -l)
if [ "$WHEEL_COUNT" -eq 0 ]; then
    die "no .whl produced"
fi

for whl in "$APP_DIR/dist"/*.whl; do
    echo "[done]  $whl"
done

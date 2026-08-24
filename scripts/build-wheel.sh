#!/usr/bin/env bash

# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

#
# build-wheel.sh — clean-build a wheel for one Artifice app or shared package.
#
# Problem: the Python build-backend (setuptools) reuses files left in build/
# from a previous build.  A deleted module stays in the wheel because it is
# still on disk under build/lib/<package>/ — an invisible packaging bug that
# only surfaces in the built artifact.  Clearing build/ *and* dist/ first
# makes it impossible to forget.
#
# Usage: scripts/build-wheel.sh <app-or-package-name>
#
#   scripts/build-wheel.sh artifice-ocr       # an app under apps/
#   scripts/build-wheel.sh artifice-draft
#   scripts/build-wheel.sh shared-ui          # a package under packages/

set -euo pipefail

TARGET="${1:?Usage: $0 <app-or-package-name>}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

die() { printf 'error: %s\n' "$*" >&2; exit 1; }

# Resolve under apps/ first, then packages/.  The three shared packages
# (model-harness, secure-io, shared-ui) carry the code and assets every app
# depends on, so they must be buildable here too — a stale build/ in one of
# them is the exact invisible packaging bug this script exists to catch.
if [ -d "$REPO_ROOT/apps/$TARGET" ]; then
    TARGET_DIR="$REPO_ROOT/apps/$TARGET"
elif [ -d "$REPO_ROOT/packages/$TARGET" ]; then
    TARGET_DIR="$REPO_ROOT/packages/$TARGET"
else
    die "no directory found at $REPO_ROOT/apps/$TARGET or $REPO_ROOT/packages/$TARGET"
fi

[ -f "$TARGET_DIR/pyproject.toml" ] || die "$TARGET_DIR/pyproject.toml not found"

# ── Clean previous build artefacts ──────────────────────────────────────
if [ -d "$TARGET_DIR/build" ]; then
    rm -rf "$TARGET_DIR/build"
    echo "[clean] removed $TARGET_DIR/build"
fi
if [ -d "$TARGET_DIR/dist" ]; then
    rm -rf "$TARGET_DIR/dist"
    echo "[clean] removed $TARGET_DIR/dist"
fi

# ── Build ───────────────────────────────────────────────────────────────
echo "[build] building $TARGET wheel..."
(
    cd "$TARGET_DIR"
    uv run --with build python -m build --wheel 2>&1
)

# ── Verify ───────────────────────────────────────────────────────────────
WHEEL_COUNT=$(find "$TARGET_DIR/dist" -name '*.whl' 2>/dev/null | wc -l)
if [ "$WHEEL_COUNT" -eq 0 ]; then
    die "no .whl produced"
fi

for whl in "$TARGET_DIR/dist"/*.whl; do
    echo "[done]  $whl"
done

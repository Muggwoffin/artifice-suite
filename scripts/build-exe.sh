#!/usr/bin/env bash

# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

#
# build-exe.sh — freeze an Artifice app into a standalone onedir executable.
#
# Problem: PyInstaller reuses files left in build/ from a previous run, and a
# stale build/ can silently resurrect deleted code — the same trap
# build-wheel.sh exists to avoid.  Clearing build/ *and* dist/ first makes it
# impossible to forget.
#
# onedir (not onefile) is the default and the only path this script supports.
# A onedir bundle maps files directly from disk, starts faster, and is easier
# to debug than a onefile archive that extracts to a temp directory on every
# launch.  See artifice-ocr.spec for the full rationale.
#
# Usage: scripts/build-exe.sh <app-name>
#
#   scripts/build-exe.sh artifice-ocr

set -euo pipefail

APP_NAME="${1:?Usage: $0 <app-name>}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$REPO_ROOT/apps/$APP_NAME"
SPEC="$APP_DIR/$APP_NAME.spec"

die() { printf 'error: %s\n' "$*" >&2; exit 1; }

[ -d "$APP_DIR" ]  || die "no app directory found at $APP_DIR"
[ -f "$SPEC" ]     || die "$SPEC not found — write one first"

# OCR's core value depends on three external applications whose real behaviour
# cannot be proved by a protocol stub. Keep this ahead of cleanup and Freeze so
# a failed live integration produces no new executable at all.
if [ "$APP_NAME" = "artifice-ocr" ]; then
    bash "$REPO_ROOT/scripts/interop/run-live-release-gate.sh" --local-only
fi

# ── Clean previous build artefacts ──────────────────────────────────────
# PyInstaller puts build/ and dist/ at the CWD (the repo root), not under
# the app directory.  Clear both sets so nothing stale survives.
_BUILD_ROOT="$REPO_ROOT/build/$APP_NAME"
_DIST_DIR="$REPO_ROOT/dist/$APP_NAME"

if [ -d "$_BUILD_ROOT" ]; then
    rm -rf "$_BUILD_ROOT"
    echo "[clean] removed $_BUILD_ROOT"
fi
if [ -d "$_DIST_DIR" ]; then
    rm -rf "$_DIST_DIR"
    echo "[clean] removed $_DIST_DIR"
fi
# Also clear any stale app-level build/ from earlier runs.
if [ -d "$APP_DIR/build" ]; then
    rm -rf "$APP_DIR/build"
    echo "[clean] removed $APP_DIR/build"
fi
if [ -d "$APP_DIR/dist" ]; then
    rm -rf "$APP_DIR/dist"
    echo "[clean] removed $APP_DIR/dist"
fi

# ── Build ───────────────────────────────────────────────────────────────
echo "[build] freezing $APP_NAME with PyInstaller..."
(
    cd "$REPO_ROOT"
    uv run --with pyinstaller pyinstaller --clean --noconfirm "$SPEC" 2>&1
)

# ── Verify ───────────────────────────────────────────────────────────────
if [ ! -f "$_DIST_DIR/$APP_NAME" ]; then
    die "no executable produced at $_DIST_DIR/$APP_NAME"
fi

echo "[done]  $_DIST_DIR/$APP_NAME"
du -sh "$_DIST_DIR" | awk '{printf "         %s  %s\n", $1, $2}'

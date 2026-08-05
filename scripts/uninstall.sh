#!/usr/bin/env bash

# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

#
# uninstall.sh — remove one or more Artifice apps, leaving user data in place.
#
# Usage:
#   bash scripts/uninstall.sh <app> [<app> ...]
#
# What it does for each app:
#   1. Reads the app's user-data directory (via its own --data-dir command)
#      BEFORE the app is removed — after uv tool uninstall, the command is gone.
#   2. Runs uv tool uninstall <app>
#   3. Prints a prominent disclosure: the program is removed, your data is
#      still on disk, and it may contain an API key.
#
# It does NOT delete your data.  It does NOT ask interactively.
# If you also want to delete your data, do that manually afterward.
#

set -euo pipefail

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# ── helpers ─────────────────────────────────────────────────────────────

resolve_data_dir() {
    local app="$1"
    "$app" --data-dir 2>/dev/null || true
}

# ── ensure uv is available ──────────────────────────────────────────────

if ! command -v uv &>/dev/null; then
    die "uv is not installed. Nothing to uninstall."
fi

# ── parse arguments ─────────────────────────────────────────────────────

if [ $# -eq 0 ]; then
    die "no app specified. Usage: $0 <app> [<app> ...]"
fi

for arg in "$@"; do
    case "$arg" in
        artifice-ocr|artifice-draft|artifice-graph|artifice-transcribe) ;;
        --*) die "unknown flag: $arg (uninstall takes app names only)" ;;
        *) die "unknown app: $arg" ;;
    esac
done

# ── uninstall each app ──────────────────────────────────────────────────

for app in "$@"; do
    # --- Step 1: read the data directory BEFORE removing the program ---
    data_dir=""
    if command -v "$app" &>/dev/null 2>&1 ||
       { [ "$app" = "artifice-ocr" ] && command -v artifice-ocr &>/dev/null 2>&1; } ||
       { [ "$app" = "artifice-graph" ] && command -v artifice-graph &>/dev/null 2>&1; }; then
        data_dir="$(resolve_data_dir "$app" 2>/dev/null || true)"
    fi

    # --- Step 2: remove the programs ---
    if uv tool list 2>/dev/null | grep -q "^$app "; then
        uninstall_output="$(uv tool uninstall "$app" 2>&1)"
        printf '\nRemoved: %s\n' "$uninstall_output"
    else
        printf '\n%s is not installed — nothing to remove.\n' "$app"
    fi

    # --- Step 3: disclosure ---
    if [ -n "$data_dir" ]; then
        cat <<EOF

────────────────────────────────────────────────────────────────────────
Your data has been LEFT IN PLACE

  Location: $data_dir

  This directory was NOT deleted by the uninstaller.
  It may contain your API key, settings, and project data.

  If you wish to delete it, run:
      rm -rf "$data_dir"

  Be certain before you do.
────────────────────────────────────────────────────────────────────────

EOF
    else
        cat <<EOF

────────────────────────────────────────────────────────────────────────
NOTE: The data directory could not be read (the app was not installed,
or --data-dir failed).  If you previously used $app, your data may still
be on disk.  Check manually — typical paths:

    artifice-ocr         ~/.artifice_ocr/
    artifice-draft       ~/.artifice_draft/
    artifice-graph       ~/.callosip/
    artifice-transcribe  platformdirs("artifice-transcribe", "ArtificeSuite")
────────────────────────────────────────────────────────────────────────

EOF
    fi
done

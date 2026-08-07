#!/usr/bin/env bash

# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

#
# install.sh — install one or more Artifice apps via uv tool install.
#
# The repository must already be cloned and this script must be run from the
# repo root (the workspace root).  Nothing is published to any index, so an
# editable install from the local workspace is the only supported path.
#
# Usage:
#   bash scripts/install.sh <app> [<app> ...]
#   bash scripts/install.sh --list
#   bash scripts/install.sh artifice-transcribe --cuda
#
# Supported apps:  artifice-ocr  artifice-draft  artifice-graph
#                  artifice-transcribe
#
# For artifice-transcribe the default is a CPU-only torch stack
# (~1.6 GB download).  Pass --cuda for the CUDA stack (~7.2 GB).
#

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# ── helpers ─────────────────────────────────────────────────────────────

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
info() { printf '  %s\n' "$*"; }
banner() { printf '\n── %s ──\n' "$*"; }

print_data_path() {
    local app="$1"
    "$app" --data-dir
}

# ── ensure uv is available ──────────────────────────────────────────────

if ! command -v uv &>/dev/null; then
    die 'uv is required but not found on PATH.

Install it manually:
  curl -LsSf https://astral.sh/uv/install.sh | sh

Alternative methods (Homebrew, winget, pipx):
  https://docs.astral.sh/uv/getting-started/installation/

This script does not run a network-fetched installer automatically:
piping a downloaded script into a shell interpreter with no integrity
check is not something we will do on your behalf without you seeing
exactly what that command looks like first.  Run the command above
yourself, then re-run this script.'
fi

# ── parse arguments ─────────────────────────────────────────────────────

if [ $# -eq 0 ]; then
    die "no app specified. Usage: $0 <app> [<app> ...]  (or --list)"
fi

if [ "$1" = "--list" ]; then
    echo "Available apps:"
    echo "  artifice-ocr         OCR pipeline (Tropy integration, PDF export)"
    echo "  artifice-draft       Copy editing with tracked changes"
    echo "  artifice-graph       Knowledge graph + Obsidian export"
    echo "  artifice-transcribe  Speech-to-text + diarization"
    echo ""
    echo "For artifice-transcribe, add --cuda for GPU support (default: CPU)."
    exit 0
fi

CUDA=false
APPS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --cuda) CUDA=true ;;
        artifice-ocr|artifice-draft|artifice-graph|artifice-transcribe)
            APPS+=("$1") ;;
        *) die "unknown argument: $1 (use --list to see available apps)" ;;
    esac
    shift
done

if [ ${#APPS[@]} -eq 0 ]; then
    die "no valid app specified"
fi

# ── install ─────────────────────────────────────────────────────────────

INSTALLED=()

for app in "${APPS[@]}"; do
    app_dir="apps/$app"
    [ -d "$app_dir" ] || die "app directory not found: $app_dir"
    [ -f "$app_dir/pyproject.toml" ] || die "pyproject.toml not found in $app_dir"

    banner "Installing $app"

    if [ "$app" = "artifice-transcribe" ]; then
        if [ "$CUDA" = true ]; then
            info "GPU (CUDA) install — this may download ~7 GB"
            uv tool install --editable "./${app_dir}[asr-cuda]" \
                --torch-backend auto
        else
            info "CPU install — this avoids the ~7 GB CUDA runtime"
            uv tool install --editable "./${app_dir}[asr]" \
                --torch-backend cpu
        fi
    else
        uv tool install --editable "./$app_dir"
    fi

    INSTALLED+=("$app")
done

# ── summary ─────────────────────────────────────────────────────────────

banner "Install complete"

for app in "${INSTALLED[@]}"; do
    case "$app" in
        artifice-ocr)
            echo "  artifice-ocr           CLI + pipeline"
            echo "  artifice-ocr-web       Web UI server"
            ;;
        artifice-draft)
            echo "  artifice-draft         CLI mode"
            ;;
        artifice-graph)
            echo "  artifice-graph          CLI + pipeline"
            echo "  artifice-graph-web      Web UI server"
            ;;
        artifice-transcribe)
            echo "  artifice-transcribe     FastAPI server (port 8000)"
            ;;
    esac
    echo "  Data: $(print_data_path "$app")"
    echo
done

echo "Uninstall with: bash scripts/uninstall.sh <app> [<app> ...]"

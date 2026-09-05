#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Maurice Casey
# SPDX-License-Identifier: AGPL-3.0-or-later

set -euo pipefail

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH='' cd -- "$SCRIPT_DIR/../.." && pwd)
# Resolved from this script, not the caller's CWD.
# shellcheck disable=SC1091
. "$SCRIPT_DIR/versions.env"

channel=${1:-stable}
source_dir="$REPO_ROOT/.interop/tropy-$channel"
runtime_dir="$REPO_ROOT/.interop/runtime/node-v$NODE_VERSION-linux-x64"

bash "$SCRIPT_DIR/doctor.sh" "$channel"
export PATH="$runtime_dir/bin:$PATH"
export ARTIFICE_LIVE_TROPY=1
export ARTIFICE_TROPY_SOURCE="$source_dir"
# Keeps automated/sandboxed runs self-contained; callers may still provide a
# shared cache explicitly when they want one.
export UV_CACHE_DIR="${UV_CACHE_DIR:-$REPO_ROOT/.interop/uv-cache}"

cd "$REPO_ROOT"
if [[ "${ARTIFICE_LIVE_HEADED:-0}" == "1" ]]; then
  if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
    echo "error: ARTIFICE_LIVE_HEADED=1 requires a graphical display" >&2
    exit 1
  fi
  exec uv run pytest -m live_interop apps/artifice-ocr/tests/test_tropy_live.py -v
fi
# A private X server prevents WSLg's WebGL renderer from intermittently
# crashing while Playwright and Tropy are alive together. Set
# ARTIFICE_LIVE_HEADED=1 for an observable manual run.
if command -v xvfb-run >/dev/null 2>&1; then
  exec xvfb-run -a uv run pytest -m live_interop apps/artifice-ocr/tests/test_tropy_live.py -v
fi
if [[ -n "${DISPLAY:-}" || -n "${WAYLAND_DISPLAY:-}" ]]; then
  echo "[live gate] xvfb-run unavailable; using the existing graphical display"
  exec uv run pytest -m live_interop apps/artifice-ocr/tests/test_tropy_live.py -v
fi
echo "error: install xvfb or provide a graphical display to run live Tropy" >&2
exit 1

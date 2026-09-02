#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Maurice Casey
# SPDX-License-Identifier: AGPL-3.0-or-later

set -u

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH='' cd -- "$SCRIPT_DIR/../.." && pwd)
# Resolved from this script, not the caller's CWD.
# shellcheck disable=SC1091
. "$SCRIPT_DIR/versions.env"

channel=${1:-stable}
source_dir="$REPO_ROOT/.interop/tropy-$channel"
runtime_dir="$REPO_ROOT/.interop/runtime/node-v$NODE_VERSION-linux-x64"
failures=0

check_command() {
  if command -v "$1" >/dev/null 2>&1; then
    echo "ok       $1: $(command -v "$1")"
  else
    echo "missing  $1"
    failures=$((failures + 1))
  fi
}

echo "Artifice desktop interoperability doctor"
echo "channel: $channel"
for command_name in git curl tar xz make g++ python3; do
  check_command "$command_name"
done

if [[ -n "${DISPLAY:-}" || -n "${WAYLAND_DISPLAY:-}" ]]; then
  echo "ok       graphical display is available"
elif command -v xvfb-run >/dev/null 2>&1; then
  echo "ok       xvfb-run is available for headless Electron"
else
  echo "missing  graphical display or xvfb-run"
  failures=$((failures + 1))
fi

if [[ -x "$runtime_dir/bin/node" ]]; then
  echo "ok       isolated Node: $("$runtime_dir/bin/node" --version)"
else
  echo "missing  isolated Node $NODE_VERSION (run bootstrap-tropy.sh)"
  failures=$((failures + 1))
fi

if [[ -d "$source_dir/.git" ]]; then
  echo "ok       Tropy source: $source_dir"
else
  echo "missing  Tropy $channel source (run bootstrap-tropy.sh $channel)"
  failures=$((failures + 1))
fi

if [[ -x "$source_dir/node_modules/.bin/electron" && -f "$source_dir/lib/main/index.js" ]]; then
  echo "ok       Tropy Electron dependencies and application bundle"
else
  echo "missing  built Tropy application (run bootstrap-tropy.sh $channel)"
  failures=$((failures + 1))
fi

if command -v pkg-config >/dev/null 2>&1 && pkg-config --exists vips-cpp; then
  echo "ok       system libvips development files"
else
  echo "optional libvips-dev absent; bootstrap will use Tropy's bundled library"
fi

if command -v xvfb-run >/dev/null 2>&1; then
  echo "ok       xvfb-run (scheduled/headless testing)"
else
  echo "optional xvfb-run absent; WSLg tests still work"
fi

if (( failures > 0 )); then
  echo "$failures required check(s) failed" >&2
  exit 1
fi
echo "All required checks passed"

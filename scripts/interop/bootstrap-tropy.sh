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
case "$channel" in
  stable)
    tropy_ref=$TROPY_STABLE_REF
    ;;
  canary)
    tropy_ref=$TROPY_CANARY_REF
    ;;
  *)
    echo "usage: $0 [stable|canary]" >&2
    exit 2
    ;;
esac

interop_root="$REPO_ROOT/.interop"
source_dir="$interop_root/tropy-$channel"
runtime_dir="$interop_root/runtime/node-v$NODE_VERSION-linux-x64"
archive="$interop_root/runtime/node-v$NODE_VERSION-linux-x64.tar.xz"

mkdir -p "$interop_root/runtime"

if [[ ! -d "$source_dir/.git" ]]; then
  git clone --filter=blob:none https://github.com/tropy/tropy.git "$source_dir"
fi

git -C "$source_dir" fetch --tags origin "$tropy_ref"
git -C "$source_dir" checkout --detach "$tropy_ref"

if [[ ! -x "$runtime_dir/bin/node" ]]; then
  curl -fsSL \
    "https://nodejs.org/dist/v$NODE_VERSION/node-v$NODE_VERSION-linux-x64.tar.xz" \
    -o "$archive"
  echo "$NODE_LINUX_X64_SHA256  $archive" | sha256sum --check --status
  tar -xJf "$archive" -C "$interop_root/runtime"
fi

export PATH="$runtime_dir/bin:$PATH"
echo "Using $(node --version), npm $(npm --version)"

(
  cd "$source_dir"
  npm install --ignore-scripts
  npm rebuild electron
  if command -v pkg-config >/dev/null 2>&1 && pkg-config --exists vips-cpp; then
    node scripts/rebuild.js --force --global-libvips
  else
    echo "libvips-dev not found; using Tropy's bundled libvips for the native rebuild."
    node scripts/rebuild.js --force
  fi
  npm run rollup
)

echo "Tropy $channel is ready at $source_dir"
echo "Run: bash scripts/interop/run-live-tropy.sh $channel"

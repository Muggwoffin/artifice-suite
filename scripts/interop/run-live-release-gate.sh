#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Maurice Casey
# SPDX-License-Identifier: AGPL-3.0-or-later

# Release-blocking live interop gate for Artifice OCR. This launches an
# isolated real Tropy process and sends a real archival scan through both
# Ollama and LM Studio. It never opens a user's Tropy profile or project.

set -euo pipefail

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH='' cd -- "$SCRIPT_DIR/../.." && pwd)
channel=${ARTIFICE_TROPY_CHANNEL:-stable}
publish_status=0

command -v curl >/dev/null 2>&1 || {
  echo "error: curl is required for live endpoint discovery" >&2
  exit 1
}

if [[ "${1:-}" == "--publish-status" ]]; then
  publish_status=1
elif [[ -n "${1:-}" && "${1:-}" != "--local-only" ]]; then
  echo "usage: $0 [--local-only|--publish-status]" >&2
  exit 2
fi

first_reachable_base() {
  local port=$1
  local probe=$2
  local host gateway
  local -a hosts=("127.0.0.1")
  gateway=""
  if command -v ip >/dev/null 2>&1; then
    gateway=$(ip route show default 2>/dev/null | awk 'NR == 1 { print $3 }')
  fi
  if [[ -n "$gateway" ]]; then
    hosts+=("$gateway")
  fi
  hosts+=("host.docker.internal")
  for host in "${hosts[@]}"; do
    if curl --fail --silent --show-error --max-time 3 "http://$host:$port$probe" >/dev/null 2>&1; then
      printf 'http://%s:%s' "$host" "$port"
      return 0
    fi
  done
  return 1
}

if [[ -z "${ARTIFICE_LIVE_OLLAMA_URL:-}" ]]; then
  ARTIFICE_LIVE_OLLAMA_URL=$(first_reachable_base 11434 /api/tags) || {
    echo "error: Ollama was not reachable on localhost or the WSL host (port 11434)" >&2
    exit 1
  }
fi
if [[ -z "${ARTIFICE_LIVE_LM_STUDIO_URL:-}" ]]; then
  lm_base=$(first_reachable_base 1234 /v1/models) || {
    echo "error: LM Studio was not reachable on localhost or the WSL host (port 1234)" >&2
    exit 1
  }
  ARTIFICE_LIVE_LM_STUDIO_URL="$lm_base/v1"
fi

export ARTIFICE_LIVE_MODELS=1
export ARTIFICE_LIVE_OLLAMA_URL
export ARTIFICE_LIVE_LM_STUDIO_URL
export UV_CACHE_DIR="${UV_CACHE_DIR:-$REPO_ROOT/.interop/uv-cache}"

status_repo=""
status_sha=""
if (( publish_status )); then
  git -C "$REPO_ROOT" diff --quiet || {
    echo "error: tracked worktree changes must be committed before publishing the gate" >&2
    exit 1
  }
  git -C "$REPO_ROOT" diff --cached --quiet || {
    echo "error: staged changes must be committed before publishing the gate" >&2
    exit 1
  }
  status_repo=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
  status_sha=$(git -C "$REPO_ROOT" rev-parse HEAD)
  gh api --method POST "repos/$status_repo/statuses/$status_sha" \
    -f state=pending \
    -f context=live-interop/release-gate \
    -f description='Real Tropy, Ollama, and LM Studio checks are running' >/dev/null
  report_failure() {
    local code=$?
    if (( code != 0 )); then
      gh api --method POST "repos/$status_repo/statuses/$status_sha" \
        -f state=failure \
        -f context=live-interop/release-gate \
        -f description='A real Tropy, Ollama, or LM Studio check failed' >/dev/null || true
    fi
    exit "$code"
  }
  trap report_failure EXIT
fi

echo "[live gate] Ollama:   $ARTIFICE_LIVE_OLLAMA_URL"
echo "[live gate] LM Studio: $ARTIFICE_LIVE_LM_STUDIO_URL"
echo "[live gate] Tropy:     $channel (isolated profile and project)"

cd "$REPO_ROOT"
# Exactly two paid/expensive model calls: one per backend, both initiated from
# the same visible Source controls users exercise in the packaged app.
uv run pytest -m live_interop apps/artifice-ocr/tests/test_live_ui_model_interop.py -v
bash scripts/interop/run-live-tropy.sh "$channel"

if (( publish_status )); then
  trap - EXIT
  gh api --method POST "repos/$status_repo/statuses/$status_sha" \
    -f state=success \
    -f context=live-interop/release-gate \
    -f description='Real Tropy, Ollama, and LM Studio checks passed' >/dev/null
  echo "[live gate] published success for $status_sha"
fi
echo "[live gate] PASS"

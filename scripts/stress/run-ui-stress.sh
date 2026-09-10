#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

set -euo pipefail

PROFILE="pr"
REPLAY_SEED=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --scheduled) PROFILE="scheduled" ;;
    --replay)
      shift
      REPLAY_SEED="${1:?--replay requires a numeric seed}"
      ;;
    *)
      echo "Usage: $0 [--scheduled] [--replay SEED]" >&2
      exit 2
      ;;
  esac
  shift
done

if [[ -n "$REPLAY_SEED" ]]; then
  export ARTIFICE_STRESS_SEEDS="$REPLAY_SEED"
  export ARTIFICE_STRESS_ACTIONS="${ARTIFICE_STRESS_ACTIONS:-30}"
elif [[ "$PROFILE" == "scheduled" ]]; then
  export ARTIFICE_STRESS_SEED_COUNT="${ARTIFICE_STRESS_SEED_COUNT:-50}"
  export ARTIFICE_STRESS_ACTIONS="${ARTIFICE_STRESS_ACTIONS:-75}"
else
  export ARTIFICE_STRESS_SEED_COUNT="${ARTIFICE_STRESS_SEED_COUNT:-8}"
  export ARTIFICE_STRESS_ACTIONS="${ARTIFICE_STRESS_ACTIONS:-30}"
fi

export ARTIFICE_STRESS_ARTIFACTS="${ARTIFICE_STRESS_ARTIFACTS:-.artifacts/ui-stress}"
uv run pytest -q -m ui_stress apps/artifice-ocr/tests/stress

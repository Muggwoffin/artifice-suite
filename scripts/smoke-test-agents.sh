#!/usr/bin/env bash

# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

# Verify the Artifice Suite agent fleet is actually wired up.
#
# Run from the repo root:
#     bash scripts/smoke-test-agents.sh          # Linux / macOS / WSL
#     bash scripts/smoke-test-agents.sh          # Windows: from Git Bash
#
# Why this exists: `opencode run --agent <name>` does NOT fail loudly when an agent
# is misconfigured. If the agent is `mode: subagent`, OpenCode prints a warning and
# silently answers as the default `build` agent instead. The reply looks correct.
# This script asserts on the response banner, which names the agent AND the model
# that actually served the request, so a fallback cannot pass.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

PASS=0
FAIL=0

green() { printf '\033[32m%s\033[0m\n' "$1"; }
red()   { printf '\033[31m%s\033[0m\n' "$1"; }
bold()  { printf '\033[1m%s\033[0m\n' "$1"; }

ok()  { green "  PASS  $1"; PASS=$((PASS+1)); }
bad() { red   "  FAIL  $1"; FAIL=$((FAIL+1)); }

# OpenCode terminates the banner line with a carriage return. Left in place it
# sits between the model name and end-of-line, so any `${model}$` assertion below
# fails against a banner that is in fact correct. Strip SGR colour and CR both.
strip_ansi() { sed -e 's/\x1b\[[0-9;]*m//g' -e 's/\r$//'; }

# --- OpenCode agents -------------------------------------------------------
# name:expected-model-substring
OPENCODE_AGENTS=(
  "lead-engineer:deepseek-v4-pro"
  "tester:kimi-k2.7-code"
  "arch-auditor-docs:minimax-m2.7"
  "security-auditor:qwen3.7-max"
  "code-reviewer:minimax-m3"
  "oss-reviewer:mistral-medium-latest"
  # ui-ux returned to OpenCode on 2026-08-06 — see the Claude Code block below
  # for why, and why this model in particular.
  "ui-ux:minimax-m2.7"
)

bold "OpenCode runtime"

if ! command -v opencode >/dev/null 2>&1; then
  bad "opencode CLI not found on PATH"
else
  ok "opencode CLI present ($(opencode --version 2>/dev/null | tr -d '\r'))"

  # Reduce the registry to just its header lines BEFORE matching.
  #
  # `opencode agent list` emits ~4000 lines, of which about nineteen are the
  # "<name> (<mode>)" headers we care about; everything else is a pretty-printed
  # JSON permission dump under each agent. Capturing all of it into a shell
  # variable and grepping the blob once per agent was the cause of the flaky
  # gate recorded as HANDOVER item 12 — `mode=all` failed on *different* agents
  # across runs while every direct check passed, because a partial or
  # interleaved capture of a 4000-line stream drops whichever headers happen to
  # fall past the truncation point.
  #
  # Extracting the headers first makes the comparison deterministic: nineteen
  # short lines, no JSON, nothing timing-dependent. Keep it this way — this gate
  # exists to catch silent agent fallback, so a gate that cries wolf is worse
  # than none. A gate that has never run clean is not a passing gate.
  registry="$(opencode agent list 2>&1 | strip_ansi \
    | grep -E '^[a-z0-9_-]+ \((all|primary|subagent)\)' || true)"

  if [[ -z "$registry" ]]; then
    bad "opencode agent list returned no agent headers — cannot verify any mode"
  fi

  for entry in "${OPENCODE_AGENTS[@]}"; do
    agent="${entry%%:*}"
    # Split on the FIRST colon only. Ollama model IDs carry their own colon
    # (gemma4-32k:12b), and a greedy ##*: would keep only the tag, which then
    # fails the end-anchored banner match below.
    model="${entry#*:}"

    # Must be registered as `all` — `subagent` triggers the silent fallback.
    if printf '%s' "$registry" | grep -qE "^${agent} \(all\)"; then
      ok "$agent registered as mode=all"
    else
      bad "$agent not registered as mode=all (silent-fallback risk)"
      continue
    fi

    reply="$(timeout 150 opencode run --agent "$agent" \
      "Reply with exactly: PONG $agent. Do not use any tools." 2>&1 | strip_ansi)"

    # Banner form: "> <agent> · <model>"
    if printf '%s' "$reply" | grep -qE "^> ${agent} .* ${model}\$"; then
      ok "$agent served by $model"
    else
      bad "$agent did not report model $model — got: $(printf '%s' "$reply" | grep -E '^> ' | head -1)"
    fi

    if printf '%s' "$reply" | grep -q "Falling back to default agent"; then
      bad "$agent fell back to the default agent"
    fi
  done
fi

# --- Claude Code runtime ---------------------------------------------------
# As of 2026-08-06 NO agent runs here. `ui-ux` was the last one, and it has now
# moved to OpenCode for the SECOND time. A stray definition here would SHADOW the
# OpenCode one when the orchestrator dispatches by name — the same trap the
# security-auditor check below guards against.
#
# History, because this placement has oscillated and the reasoning is what
# matters rather than any one destination:
#   2026-07-28  left Claude Code -> OpenCode/Copilot; whole fleet off the
#               maintainer's subscription, which the orchestrator alone used.
#   2026-07-29  returned to Claude Code on `sonnet` after the Copilot and
#               OpenCode Go tiers were each exhausted in a single day.
#   2026-08-06  left again for `opencode-go/minimax-m2.7`, because the shared
#               budget bit exactly as predicted: the agent died mid-task on a
#               session limit, leaving a half-written shared component.
#
# The standing rule survived all three moves: `ui-ux` must not share a model with
# `code-reviewer` (currently `minimax-m3`), which reviews its output. A reviewer
# grading its own model's work is the failure the independence rule exists to
# prevent. `minimax-m2.7` also satisfies the maintainer's cost constraint of
# "cheaper than kimi-k3".

bold "Claude Code runtime"

# NO agent definitions belong here at all any more.
_stray=()
for _f in .claude/agents/*.md; do
  [[ -e "$_f" ]] || continue
  _stray+=("$_f")
done
if (( ${#_stray[@]} > 0 )); then
  bad "unexpected agent definitions in .claude/agents/ — the whole fleet is OpenCode as of 2026-08-06"
  printf '        %s\n' "${_stray[@]}"
else
  ok "no Claude Code agent definitions (whole fleet is OpenCode)"
fi

# ui-ux must be defined in exactly one runtime, and that runtime is OpenCode.
if [[ -f .opencode/agents/ui-ux.md ]]; then
  if [[ -f .claude/agents/ui-ux.md ]]; then
    bad "ui-ux defined in BOTH runtimes — the Claude Code copy will shadow the OpenCode one"
  else
    ok "ui-ux defined in OpenCode runtime only"
  fi
else
  bad "ui-ux missing from .opencode/agents/ — it moved there on 2026-08-06"
fi

# security-auditor moved to OpenCode/Gemini to reduce Claude token usage. It must
# not be defined in both runtimes — a stale Claude Code copy would shadow the
# OpenCode one when the orchestrator dispatches by name.
if [[ -f .claude/agents/security-auditor.md ]]; then
  bad "security-auditor still defined in .claude/agents/ — it now lives in .opencode/agents/"
else
  ok "security-auditor not duplicated in Claude Code runtime"
fi

# It is read-only by design. Write access would let an audit mutate what it audits.
if grep -qE '^[[:space:]]*(write|edit|bash|patch):[[:space:]]*true' .opencode/agents/security-auditor.md; then
  bad "security-auditor has a write/edit/bash/patch tool enabled — must stay read-only"
else
  ok "security-auditor is read-only (no write/edit/bash/patch)"
fi

# `.claude/rules/` was superseded by `.claude/agents/`. Files left there load as
# project-wide instructions into every session instead of scoping to an agent.
if [[ -d .claude/rules ]] && compgen -G ".claude/rules/*.md" >/dev/null; then
  bad ".claude/rules/*.md present — these leak into every session's context"
else
  ok ".claude/rules/ clear (no ambient instruction leakage)"
fi

# --- Token parity guard ----------------------------------------------------
bold "Design-system token parity"
if python3 scripts/token-parity-check.py; then
  ok "runtime tokens match design-system reference"
else
  bad "token drift detected (see above)"
fi

# --- Summary ---------------------------------------------------------------
echo
bold "$PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]] || exit 1

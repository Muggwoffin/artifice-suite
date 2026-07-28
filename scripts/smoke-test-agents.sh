#!/usr/bin/env bash
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
  "tester:kimi-k3"
  "arch-auditor-docs:glm-5.2"
  "security-auditor:qwen3.7-max"
  "code-reviewer:claude-sonnet-5"
  "oss-reviewer:gemma4-32k:12b"
)

bold "OpenCode runtime"

if ! command -v opencode >/dev/null 2>&1; then
  bad "opencode CLI not found on PATH"
else
  ok "opencode CLI present ($(opencode --version 2>/dev/null | tr -d '\r'))"

  registry="$(opencode agent list 2>&1 | strip_ansi)"

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

# --- Claude Code agents ----------------------------------------------------
# These run on the user's Claude subscription and are dispatched by the
# orchestrator, not from this shell. Verified structurally.

bold "Claude Code runtime"

CLAUDE_AGENTS=(ui-ux)

for agent in "${CLAUDE_AGENTS[@]}"; do
  f=".claude/agents/${agent}.md"
  if [[ ! -f "$f" ]]; then
    bad "$f missing"
    continue
  fi
  if grep -qE '^model:[[:space:]]*sonnet[[:space:]]*$' "$f"; then
    ok "$agent defined, model: sonnet"
  else
    bad "$agent is not pinned to model: sonnet"
  fi
done

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

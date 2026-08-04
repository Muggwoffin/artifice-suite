#!/usr/bin/env bash

# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

# Dispatch an OpenCode sub-agent safely from a Windows-side orchestrator session.
#
# Usage:
#   bash scripts/dispatch-opencode.sh <agent> <brief-file> [--wait SECONDS]
#   bash scripts/dispatch-opencode.sh <agent> <brief-file> --foreground
#   bash scripts/dispatch-opencode.sh --status
#   bash scripts/dispatch-opencode.sh --stop <agent>
#
# Why this exists: dispatching across the Windows -> WSL boundary breaks in four
# ways that are individually silent and collectively expensive (GUARDS 1-4), and
# a fifth trap has nothing to do with the boundary: run artefacts from a previous
# dispatch outlive it and get read as though they describe the current one
# (GUARD 5). See the header comments on each guard below. Always prefer this
# script to a hand-rolled invocation.
#
# Liveness is judged by CPU time against wall time, never by the log — logs are
# block-buffered when redirected, so a frozen log proves nothing. 0.00 CPU over a
# long elapsed time means a stalled transport; low-but-nonzero CPU means the
# provider is throttling. Two different faults, one identical symptom.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNDIR="${TMPDIR:-/tmp}/opencode-dispatch"
mkdir -p "$RUNDIR"

# ---------------------------------------------------------------- helpers ---

# GUARD 4: never `pkill -f <agent>` — that pattern also matches the
# orchestrator's own wrapper shell, killing the wrapper while leaving the agent
# alive. Once left two arch-auditor-docs racing on the same files. Resolve real
# PIDs from /proc/<pid>/cmdline instead.
agent_pids() {
  local agent="$1" pid cmdline
  for pid in $(pgrep -f 'opencode' 2>/dev/null); do
    [ -r "/proc/$pid/cmdline" ] || continue
    cmdline="$(tr '\0' ' ' < "/proc/$pid/cmdline")"
    case "$cmdline" in
      *"--agent $agent"*) printf '%s\n' "$pid" ;;
    esac
  done
}

cmd_status() {
  local pid cmdline agent etime found=0
  for pid in $(pgrep -f 'opencode' 2>/dev/null); do
    [ -r "/proc/$pid/cmdline" ] || continue
    cmdline="$(tr '\0' ' ' < "/proc/$pid/cmdline")"
    case "$cmdline" in
      *--agent*) ;;
      *) continue ;;
    esac
    agent="$(printf '%s' "$cmdline" | grep -o -- '--agent [a-z-]*' | head -1 | cut -d' ' -f2)"
    etime="$(ps -o etime= -p "$pid" 2>/dev/null | tr -d ' ')"
    printf 'pid=%-8s elapsed=%-10s agent=%s\n' "$pid" "$etime" "$agent"
    found=1
  done
  [ "$found" -eq 0 ] && echo "no opencode agents running"

  echo
  echo "--- run artefacts ---"
  local f name
  for f in "$RUNDIR"/*.status; do
    [ -e "$f" ] || continue
    name="$(basename "$f" .status)"
    # A status file belonging to a currently-running agent describes an EARLIER
    # run. Saying so is the whole point — an unqualified `exit=143` next to a live
    # process reads as "this run failed" and has already caused one misdiagnosis.
    if [ -n "$(agent_pids "$name")" ]; then
      printf '%s: %s   <-- STALE, from a previous run; %s is running now\n' \
        "$name" "$(cat "$f")" "$name"
    else
      printf '%s: %s\n' "$name" "$(cat "$f")"
    fi
  done

  # NOTE: agent logs are BLOCK-BUFFERED when stdout is a file, so a frozen log
  # proves nothing about liveness. Judge progress by mtimes and git diff.
  echo
  echo "--- real content changes (line-ending noise excluded) ---"
  git -C "$REPO" diff --ignore-cr-at-eol --stat | tail -20
}

# GUARD 6: refuse to let an agent stop itself. An OpenCode agent that has picked
# up the orchestrator persona from CLAUDE.md will try to dispatch work, hit the
# "already running" error below, follow its advice, and SIGTERM its own process
# tree — surfacing as a mysterious exit=143 with a log that stops mid-sentence.
# GUARD 4 protects the *orchestrator's* wrapper; this protects the agent itself.
is_own_ancestor() {
  local target="$1" p=$$
  while [ "$p" -gt 1 ]; do
    [ "$p" = "$target" ] && return 0
    p="$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' ')"
    [ -z "$p" ] && break
  done
  return 1
}

cmd_stop() {
  local agent="$1" pids
  pids="$(agent_pids "$agent")"
  if [ -z "$pids" ]; then
    echo "no running process for agent '$agent'"
    return 0
  fi
  local pid
  for pid in $pids; do
    if is_own_ancestor "$pid"; then
      echo "REFUSING to stop pid $pid ($agent): that is this process's own agent." >&2
      echo "  You are '$agent'. You cannot dispatch or stop yourself — implement" >&2
      echo "  the task directly instead of delegating it." >&2
      return 1
    fi
  done
  for pid in $pids; do
    echo "stopping pid $pid ($agent)"
    kill -TERM "$pid" 2>/dev/null
  done
  sleep 3
  pids="$(agent_pids "$agent")"
  # shellcheck disable=SC2086  # $pids is a newline-separated PID list and MUST
  # word-split — quoting it would pass "123 456" to kill as a single argument.
  [ -n "$pids" ] && { echo "still alive, sending KILL: $pids"; kill -KILL $pids 2>/dev/null; }
  echo "stopped."
}

# ------------------------------------------------------------------- main ---

case "${1:-}" in
  --status) cmd_status; exit 0 ;;
  --stop)   [ $# -ge 2 ] || { echo "usage: $0 --stop <agent>" >&2; exit 2; }
            cmd_stop "$2"; exit 0 ;;
esac

[ $# -ge 2 ] || { echo "usage: $0 <agent> <brief-file> [--wait SECONDS] [--foreground]" >&2; exit 2; }
AGENT="$1"; BRIEF_SRC="$2"; shift 2
WAIT=0
FOREGROUND=0
for arg in "$@"; do
  case "$arg" in
    --foreground) FOREGROUND=1 ;;
  esac
done
[ "${1:-}" = "--wait" ] && WAIT="${2:-25}"

[ -f "$BRIEF_SRC" ] || { echo "brief file not found: $BRIEF_SRC" >&2; exit 1; }

# Refuse to start a second copy of an agent that is already running.
if [ -n "$(agent_pids "$AGENT")" ]; then
  echo "ERROR: '$AGENT' is already running (pids: $(agent_pids "$AGENT" | tr '\n' ' '))." >&2
  # Do NOT advise --stop unconditionally. If the caller *is* this agent, that
  # advice tells it to kill itself, which is exactly what happened once.
  if is_own_ancestor "$(agent_pids "$AGENT" | head -1)"; then
    echo "       You are '$AGENT'. This script dispatches sub-agents and is the" >&2
    echo "       orchestrator's tool, not yours. Implement the task directly." >&2
  else
    echo "       Stop it first:  $0 --stop $AGENT" >&2
  fi
  exit 1
fi

BRIEF="$RUNDIR/$AGENT.brief"
LOG="$RUNDIR/$AGENT.log"
STATUS="$RUNDIR/$AGENT.status"

# GUARD 5: clear the previous run's artefacts BEFORE launching. The status file is
# only written when the runner finishes, so a leftover `exit=143` from a killed
# run sits there looking authoritative while the new agent is still working — and
# reports a failure that already happened for a process that is perfectly healthy.
# The log is truncated for the same reason: a stale banner names the model of the
# *previous* run, which is exactly the check this script exists to make trustworthy.
rm -f "$STATUS" "$LOG"

# GUARD 1 (part a): normalise CRLF. Briefs written by Windows-side tooling arrive
# with CRLF. Use sed with an explicit hex escape — `tr -d "\r"` through this
# boundary deletes literal 'r' characters too, silently corrupting the text.
sed 's/\x0d$//' "$BRIEF_SRC" > "$BRIEF"

# Guard against the truncation failure: a brief that arrives as one word means
# the quoting was mangled somewhere upstream.
CHARS=$(wc -c < "$BRIEF" | tr -d ' ')
if [ "$CHARS" -lt 200 ]; then
  echo "ERROR: brief is only $CHARS chars — suspiciously short, refusing to dispatch." >&2
  exit 1
fi

# Resolve the runner path here, not inside the env-prefixed command below. Written
# inline there it reads as `AGENT=... bash "$RUNDIR/$AGENT.runner"`, where the
# argument is expanded by THIS shell while the prefix targets the forked one
# (shellcheck SC2097/SC2098). Same value either way, but the line lies about which
# shell resolves it.
RUNNER_PATH="$RUNDIR/$AGENT.runner"

cat > "$RUNNER_PATH" <<'RUNNER'
#!/usr/bin/env bash
# GUARD 1 (part b): the brief is read from a file INSIDE this script, so no
# quoted multi-line text ever crosses the Windows->WSL argument boundary.
# GUARD 2: all variables are expanded here, inside WSL. The orchestrator's Bash
# tool eats $var before wsl.exe sees it, even inside single quotes.
cd "$REPO" || exit 1
opencode run --agent "$AGENT" "$(cat "$BRIEF")" > "$LOG" 2>&1
echo "exit=$?" > "$STATUS"
RUNNER

# GUARD 3: setsid + nohup + disown + stdin from /dev/null, THEN block until the
# child proves it is alive. A plain `cmd &` inside `wsl.exe -- bash -c` is reaped
# when that invocation returns, and setsid alone does not reliably prevent it:
# there is a startup race. If the launching `bash -c` exits before setsid's fork
# is established, the child dies having produced nothing.
#
# On 2026-07-28 that race cost a whole dispatch. The signature is precise and
# worth recognising: **`.runner` written, `.log` absent**. The runner redirects
# with `> "$LOG"`, and a redirect creates its file before the command runs — even
# a missing `opencode` binary would leave an empty log plus `exit=127`. So a
# missing log means the runner never executed a single line. That is a launch
# failure, not a slow start, and no amount of waiting will produce output.
#
# Blocking here until the log appears closes the race (the parent stays alive
# through the vulnerable window) and verifies the launch instead of asserting it.
# --foreground sidesteps the race entirely: the caller owns the process lifetime.
# This is the reliable path when the orchestrator can background the *invocation*
# itself (Claude Code's `run_in_background`), because the harness then holds the
# process open and reports completion. Prefer it over trusting detachment.
if [ "$FOREGROUND" -eq 1 ]; then
  echo "running $AGENT in the FOREGROUND (brief ${CHARS} chars)"
  echo "  log: $LOG"
  REPO="$REPO" AGENT="$AGENT" BRIEF="$BRIEF" LOG="$LOG" STATUS="$STATUS" \
    bash "$RUNNER_PATH" < /dev/null
  echo "finished: $(cat "$STATUS" 2>/dev/null || echo 'no status written')"
  echo "--- banner ---"
  head -3 "$LOG" 2>/dev/null
  exit 0
fi

REPO="$REPO" AGENT="$AGENT" BRIEF="$BRIEF" LOG="$LOG" STATUS="$STATUS" \
  setsid nohup bash "$RUNNER_PATH" > /dev/null 2>&1 < /dev/null &
disown 2>/dev/null || true

LAUNCH_TIMEOUT=15
waited=0
while [ "$waited" -lt "$((LAUNCH_TIMEOUT * 10))" ]; do
  [ -f "$LOG" ] && break
  sleep 0.1
  waited=$((waited + 1))
done

if [ ! -f "$LOG" ]; then
  echo "ERROR: '$AGENT' failed to launch — no log after ${LAUNCH_TIMEOUT}s." >&2
  echo "       The runner never executed. This is the setsid startup race, not a" >&2
  echo "       slow model: a redirect creates its log before the command runs, so" >&2
  echo "       an absent log means no line of the runner ran at all." >&2
  echo "       Fall back to foreground and let the caller background it:" >&2
  echo "         $0 $AGENT <brief> --foreground" >&2
  rm -f "$RUNDIR/$AGENT.runner"
  exit 1
fi

# The log exists, but the process must also still be alive — a runner that died
# immediately (bad agent name, missing binary) also leaves a log behind.
sleep 1
if [ -z "$(agent_pids "$AGENT")" ] && [ ! -s "$STATUS" ]; then
  echo "ERROR: '$AGENT' started but died immediately. Log follows:" >&2
  head -20 "$LOG" >&2
  exit 1
fi

echo "dispatched: $AGENT  (brief ${CHARS} chars) — launch confirmed"
echo "  log:    $LOG"
echo "  status: $STATUS   (contains 'exit=N' once finished)"

if [ "$WAIT" -gt 0 ]; then
  sleep "$WAIT"
  echo
  echo "--- banner check (must read '> $AGENT · <expected-model>') ---"
  head -6 "$LOG" 2>/dev/null
fi

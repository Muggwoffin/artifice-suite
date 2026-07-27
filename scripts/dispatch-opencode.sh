#!/usr/bin/env bash
# Dispatch an OpenCode sub-agent safely from a Windows-side orchestrator session.
#
# Usage:
#   bash scripts/dispatch-opencode.sh <agent> <brief-file> [--wait SECONDS]
#   bash scripts/dispatch-opencode.sh --status
#   bash scripts/dispatch-opencode.sh --stop <agent>
#
# Why this exists: dispatching across the Windows -> WSL boundary breaks in four
# ways that are individually silent and collectively expensive. See the header
# comments on each guard below. Always prefer this script to a hand-rolled
# invocation.

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
  local f
  for f in "$RUNDIR"/*.status; do
    [ -e "$f" ] || continue
    printf '%s: %s\n' "$(basename "$f" .status)" "$(cat "$f")"
  done

  # NOTE: agent logs are BLOCK-BUFFERED when stdout is a file, so a frozen log
  # proves nothing about liveness. Judge progress by mtimes and git diff.
  echo
  echo "--- real content changes (line-ending noise excluded) ---"
  git -C "$REPO" diff --ignore-cr-at-eol --stat | tail -20
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
    echo "stopping pid $pid ($agent)"
    kill -TERM "$pid" 2>/dev/null
  done
  sleep 3
  pids="$(agent_pids "$agent")"
  [ -n "$pids" ] && { echo "still alive, sending KILL: $pids"; kill -KILL $pids 2>/dev/null; }
  echo "stopped."
}

# ------------------------------------------------------------------- main ---

case "${1:-}" in
  --status) cmd_status; exit 0 ;;
  --stop)   [ $# -ge 2 ] || { echo "usage: $0 --stop <agent>" >&2; exit 2; }
            cmd_stop "$2"; exit 0 ;;
esac

[ $# -ge 2 ] || { echo "usage: $0 <agent> <brief-file> [--wait SECONDS]" >&2; exit 2; }
AGENT="$1"; BRIEF_SRC="$2"; shift 2
WAIT=0
[ "${1:-}" = "--wait" ] && WAIT="${2:-25}"

[ -f "$BRIEF_SRC" ] || { echo "brief file not found: $BRIEF_SRC" >&2; exit 1; }

# Refuse to start a second copy of an agent that is already running.
if [ -n "$(agent_pids "$AGENT")" ]; then
  echo "ERROR: '$AGENT' is already running (pids: $(agent_pids "$AGENT" | tr '\n' ' '))." >&2
  echo "       Stop it first:  $0 --stop $AGENT" >&2
  exit 1
fi

BRIEF="$RUNDIR/$AGENT.brief"
LOG="$RUNDIR/$AGENT.log"
STATUS="$RUNDIR/$AGENT.status"

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

cat > "$RUNDIR/$AGENT.runner" <<'RUNNER'
#!/usr/bin/env bash
# GUARD 1 (part b): the brief is read from a file INSIDE this script, so no
# quoted multi-line text ever crosses the Windows->WSL argument boundary.
# GUARD 2: all variables are expanded here, inside WSL. The orchestrator's Bash
# tool eats $var before wsl.exe sees it, even inside single quotes.
cd "$REPO" || exit 1
opencode run --agent "$AGENT" "$(cat "$BRIEF")" > "$LOG" 2>&1
echo "exit=$?" > "$STATUS"
RUNNER

# GUARD 3: setsid + nohup + disown + stdin from /dev/null. A plain `cmd &` inside
# `wsl.exe -- bash -c` is reaped when that invocation returns.
REPO="$REPO" AGENT="$AGENT" BRIEF="$BRIEF" LOG="$LOG" STATUS="$STATUS" \
  setsid nohup bash "$RUNDIR/$AGENT.runner" > /dev/null 2>&1 < /dev/null &
disown 2>/dev/null || true

echo "dispatched: $AGENT  (brief ${CHARS} chars)"
echo "  log:    $LOG"
echo "  status: $STATUS   (contains 'exit=N' once finished)"

if [ "$WAIT" -gt 0 ]; then
  sleep "$WAIT"
  echo
  echo "--- banner check (must read '> $AGENT · <expected-model>') ---"
  head -6 "$LOG" 2>/dev/null
fi

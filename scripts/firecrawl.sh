#!/usr/bin/env bash
#
# firecrawl.sh — lifecycle control for the self-hosted Firecrawl instance used
# by OpenCode sub-agents to verify locally-served app surfaces.
#
# The instance is deliberately local-only:
#   * bound to 127.0.0.1:3002, never 0.0.0.0 (it runs unauthenticated)
#   * USE_DB_AUTHENTICATION=false, so any bearer token is accepted
#   * browser pool capped to 1, because Chromium competes for the RAM the
#     local 12B model contexts need
#
# Headless Chromium does not always exit cleanly when a scrape is abandoned.
# Always run `down` or `prune` after an audit run rather than leaving the stack
# idling — see the `prune` subcommand.
#
# Usage: scripts/firecrawl.sh {up|down|restart|status|prune|verify|logs}

set -euo pipefail

FIRECRAWL_DIR="${FIRECRAWL_DIR:-$HOME/tools/firecrawl}"
FIRECRAWL_URL="${FIRECRAWL_URL:-http://localhost:3002}"
# Services we actually want. The foundationdb pair is experimental and only
# used when NUQ_BACKEND=fdb, so it is deliberately excluded.
SERVICES=(api nuq-postgres)

die() { printf 'error: %s\n' "$*" >&2; exit 1; }

require_dir() {
  [ -d "$FIRECRAWL_DIR" ] || die "Firecrawl checkout not found at $FIRECRAWL_DIR"
  cd "$FIRECRAWL_DIR" || die "cannot cd to $FIRECRAWL_DIR"
}

require_docker() {
  command -v docker >/dev/null 2>&1 || die "docker not found on PATH"
  # A docker binary under /mnt/c is Docker Desktop's Windows shim reached across
  # the WSL interop boundary. That is the same class of trap that made the
  # opencode npm shim hang forever; refuse it outright.
  local bin
  bin="$(command -v docker)"
  case "$bin" in
    /mnt/c/*) die "docker resolves to the Windows shim ($bin). Install docker.io natively in WSL." ;;
  esac
  docker info >/dev/null 2>&1 || die "docker daemon not reachable (try: sudo systemctl start docker)"
}

cmd_up() {
  require_docker; require_dir
  docker compose up -d "${SERVICES[@]}" 2>&1 | grep -v 'variable is not set' || true
  cmd_verify
}

cmd_down() {
  require_docker; require_dir
  docker compose down --remove-orphans 2>&1 | grep -v 'variable is not set' || true
  echo "Firecrawl stopped."
}

cmd_restart() { cmd_down; cmd_up; }

cmd_status() {
  require_docker; require_dir
  docker compose ps --format 'table {{.Service}}\t{{.Status}}' 2>/dev/null
  printf '\nbinding: '
  # Confirm the published port is loopback-only, not LAN-exposed.
  if docker compose port api 3002 2>/dev/null | grep -q '^127\.0\.0\.1:'; then
    echo "127.0.0.1 only (correct)"
  else
    echo "NOT loopback-only — check the ports mapping in docker-compose.yaml"
  fi
}

# Reclaim memory after an audit run. Stale headless Chromium processes are the
# main offender; restarting playwright-service is cheaper and safer than a
# system-wide prune, so that is the default and the image prune is opt-in.
cmd_prune() {
  require_docker; require_dir
  echo "Restarting playwright-service to clear stale Chromium processes..."
  docker compose restart playwright-service >/dev/null 2>&1 || true
  echo "Removing stopped containers and dangling build cache..."
  docker container prune -f >/dev/null
  docker image prune -f >/dev/null
  echo "Done. Current usage:"
  docker system df 2>/dev/null | head -5
}

cmd_verify() {
  require_docker; require_dir
  printf 'waiting for %s ' "$FIRECRAWL_URL"
  local i
  for i in $(seq 1 45); do
    if curl -sf -m 3 "$FIRECRAWL_URL/" >/dev/null 2>&1; then
      printf '\nAPI responding after ~%ss\n' "$((i * 2))"
      cmd_status
      return 0
    fi
    printf '.'
    sleep 2
  done
  printf '\n'
  echo "API did not respond. Last 30 log lines:" >&2
  docker compose logs api --tail 30 2>&1 | tail -30 >&2
  return 1
}

cmd_logs() {
  require_docker; require_dir
  docker compose logs "${1:-api}" --tail "${2:-50}"
}

case "${1:-}" in
  up)      cmd_up ;;
  down)    cmd_down ;;
  restart) cmd_restart ;;
  status)  cmd_status ;;
  prune)   cmd_prune ;;
  verify)  cmd_verify ;;
  logs)    shift; cmd_logs "$@" ;;
  *)       die "usage: $0 {up|down|restart|status|prune|verify|logs [service] [lines]}" ;;
esac

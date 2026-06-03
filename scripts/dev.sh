#!/usr/bin/env bash
# Restart backend (uvicorn) + frontend (vite) for the bug_fix workflow.
#
# Usage:
#   scripts/dev.sh           # restart both
#   scripts/dev.sh stop      # stop both
#   scripts/dev.sh status    # show what's running
#
# Notes:
# - Binds backend to 127.0.0.1:8000 explicitly so it doesn't conflict
#   with any Docker container squatting *:8000 (those still bind via
#   IPv6 ::1 and would shadow `localhost`).
# - Logs go to .dev/{backend,frontend}.log; pids to .dev/{backend,frontend}.pid.

set -euo pipefail

# Resolve repo root from this script's location so it works from anywhere.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DEV_DIR="$ROOT_DIR/.dev"
mkdir -p "$DEV_DIR"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"

BACKEND_PID_FILE="$DEV_DIR/backend.pid"
FRONTEND_PID_FILE="$DEV_DIR/frontend.pid"
BACKEND_LOG="$DEV_DIR/backend.log"
FRONTEND_LOG="$DEV_DIR/frontend.log"

# ─── helpers ──────────────────────────────────────────────────────────

c_blue() { printf "\033[34m%s\033[0m" "$1"; }
c_green() { printf "\033[32m%s\033[0m" "$1"; }
c_red() { printf "\033[31m%s\033[0m" "$1"; }
c_dim() { printf "\033[2m%s\033[0m" "$1"; }

info() { echo "$(c_blue "[dev]") $*"; }
ok()   { echo "$(c_green "[ok] ") $*"; }
warn() { echo "$(c_red "[!]  ") $*"; }

# True if PID file holds a live process.
pid_alive() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] || return 1
  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" 2>/dev/null
}

# Kill the tracked PID and any of its descendants (uvicorn --reload
# spawns a worker; npm run dev spawns node). Leaves Docker / other
# services alone because we only touch the tree rooted at our pid.
_kill_tree() {
  local root="$1"
  # gather descendant pids breadth-first
  local pending=("$root") all=()
  while (( ${#pending[@]} > 0 )); do
    local p="${pending[0]}"
    pending=("${pending[@]:1}")
    all+=("$p")
    # children of p
    while IFS= read -r child; do
      [[ -n "$child" ]] && pending+=("$child")
    done < <(pgrep -P "$p" 2>/dev/null || true)
  done
  # SIGTERM youngest-first
  local i
  for (( i=${#all[@]}-1; i>=0; i-- )); do
    kill "${all[i]}" 2>/dev/null || true
  done
  # wait briefly, then SIGKILL anything left
  sleep 0.5
  for (( i=${#all[@]}-1; i>=0; i-- )); do
    kill -0 "${all[i]}" 2>/dev/null && kill -9 "${all[i]}" 2>/dev/null || true
  done
}

kill_tracked() {
  local pid_file="$1" label="$2"
  if [[ -f "$pid_file" ]]; then
    local pid
    pid="$(cat "$pid_file" 2>/dev/null || true)"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      info "stopping $label (pid $pid)"
      _kill_tree "$pid"
    fi
    rm -f "$pid_file"
  fi
}

# Wait until URL returns 2xx/3xx. Bails out after `timeout` seconds.
wait_for_http() {
  local url="$1" timeout="${2:-30}" label="$3"
  local elapsed=0
  while (( elapsed < timeout )); do
    if curl -s --max-time 1 -o /dev/null -w "%{http_code}" "$url" 2>/dev/null \
        | grep -qE "^(2|3)[0-9][0-9]$"; then
      return 0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
  warn "$label didn't become ready within ${timeout}s — check $BACKEND_LOG / $FRONTEND_LOG"
  return 1
}

require_venv_python() {
  if [[ ! -x "$ROOT_DIR/.venv/bin/uvicorn" ]]; then
    warn ".venv/bin/uvicorn missing — install deps first (poetry install / pip install)"
    exit 1
  fi
}

# ─── commands ─────────────────────────────────────────────────────────

start_backend() {
  require_venv_python
  info "starting backend on ${BACKEND_HOST}:${BACKEND_PORT}"
  # nohup detaches from this shell so `dev.sh` can exit while uvicorn
  # keeps running. We record the parent pid; kill_tracked walks the
  # child tree later when we need to stop the worker too.
  (
    cd "$ROOT_DIR"
    nohup "$ROOT_DIR/.venv/bin/uvicorn" \
      app.backend.main:app --reload \
      --host "$BACKEND_HOST" --port "$BACKEND_PORT" \
      >"$BACKEND_LOG" 2>&1 &
    echo $! >"$BACKEND_PID_FILE"
    disown 2>/dev/null || true
  )
  wait_for_http "http://${BACKEND_HOST}:${BACKEND_PORT}/workflows/domains" 30 "backend" \
    && ok "backend up — $(curl -s "http://${BACKEND_HOST}:${BACKEND_PORT}/workflows/domains")"
}

start_frontend() {
  if [[ ! -d "$ROOT_DIR/app/frontend/node_modules" ]]; then
    warn "app/frontend/node_modules missing — run \`cd app/frontend && npm install\` first"
    exit 1
  fi
  info "starting vite on :${FRONTEND_PORT}"
  (
    cd "$ROOT_DIR/app/frontend"
    nohup npm run dev >"$FRONTEND_LOG" 2>&1 &
    echo $! >"$FRONTEND_PID_FILE"
    disown 2>/dev/null || true
  )
  wait_for_http "http://localhost:${FRONTEND_PORT}" 30 "vite" \
    && ok "vite up at http://localhost:${FRONTEND_PORT}"
}

cmd_stop() {
  kill_tracked "$BACKEND_PID_FILE" "backend"
  kill_tracked "$FRONTEND_PID_FILE" "vite"
  ok "stopped"
}

cmd_status() {
  if pid_alive "$BACKEND_PID_FILE"; then
    ok "backend pid $(cat "$BACKEND_PID_FILE") — http://${BACKEND_HOST}:${BACKEND_PORT}"
  else
    warn "backend not running"
  fi
  if pid_alive "$FRONTEND_PID_FILE"; then
    ok "vite    pid $(cat "$FRONTEND_PID_FILE") — http://localhost:${FRONTEND_PORT}"
  else
    warn "vite not running"
  fi
  echo
  echo "$(c_dim "logs:")"
  echo "  $(c_dim "$BACKEND_LOG")"
  echo "  $(c_dim "$FRONTEND_LOG")"
}

cmd_restart() {
  cmd_stop
  start_backend
  start_frontend
  echo
  cmd_status
}

# ─── dispatch ─────────────────────────────────────────────────────────

case "${1:-restart}" in
  restart|"") cmd_restart ;;
  stop)       cmd_stop ;;
  status)     cmd_status ;;
  start)      cmd_restart ;;
  *)
    echo "usage: $0 {restart|stop|status}" >&2
    exit 2
    ;;
esac

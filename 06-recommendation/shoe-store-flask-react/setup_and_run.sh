#!/usr/bin/env bash
# Sets up the recommendation-nodejs demo end-to-end and starts both services.
# Idempotent: re-running skips steps that are already done.
#
# Usage:
#   ./setup_and_run.sh              # full setup + start backend & frontend
#   ./setup_and_run.sh --skip-db    # skip dbsetup.sql (data already loaded)
#   ./setup_and_run.sh --stop       # stop running backend/frontend
#   ./setup_and_run.sh --status     # show what's running

set -euo pipefail

# Db2's db2profile references AIX/HP-UX library-path vars that are unset on
# Linux; under `set -u` sourcing it aborts with "unbound variable".
#
# Binding them once is not enough: db2profile *unsets* the ones it finds empty,
# so a second `source` in the same shell dies exactly where the first survived.
# Always go through this helper, which re-binds them before every source.
source_db2profile() {
  : "${LIBPATH:=}"
  : "${SHLIB_PATH:=}"
  : "${LD_LIBRARY_PATH_32:=}"
  : "${LD_LIBRARY_PATH_64:=}"
  # shellcheck disable=SC1090
  source "$DB2_PROFILE"
}

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$APP_DIR/backend"
FRONTEND_DIR="$APP_DIR/frontend"
LOG_DIR="${LOG_DIR:-/tmp}"
BACKEND_LOG="$LOG_DIR/recnodejs-backend.log"
FRONTEND_LOG="$LOG_DIR/recnodejs-frontend.log"
BACKEND_PIDFILE="$LOG_DIR/recnodejs-backend.pid"
FRONTEND_PIDFILE="$LOG_DIR/recnodejs-frontend.pid"

DB2_PROFILE="${DB2_PROFILE:-/home/db2inst1/sqllib/db2profile}"
BACKEND_PORT="${BACKEND_PORT:-5000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

log()  { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

stop_service() {
  local name="$1" pidfile="$2"
  if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    log "Stopping $name (PID $(cat "$pidfile"))"
    kill "$(cat "$pidfile")" 2>/dev/null || true
    sleep 1
    kill -9 "$(cat "$pidfile")" 2>/dev/null || true
  fi
  rm -f "$pidfile"
}

cmd_stop() {
  stop_service backend  "$BACKEND_PIDFILE"
  stop_service frontend "$FRONTEND_PIDFILE"
  log "Stopped."
}

cmd_status() {
  for entry in "backend:$BACKEND_PIDFILE:$BACKEND_PORT" "frontend:$FRONTEND_PIDFILE:$FRONTEND_PORT"; do
    IFS=: read -r name pidfile port <<<"$entry"
    if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
      echo "$name: running (PID $(cat "$pidfile"), port $port)"
    else
      echo "$name: not running"
    fi
  done
}

# Rows in S1.SQ_SHOES, or non-numeric output if it cannot be read. Two rules,
# both learned the hard way:
#  1. CONNECT and SELECT must be separate `db2` calls. Folded into one -x string
#     with a shell redirect, CLP fails to parse it and the SQL0104N text lands on
#     stdout — non-empty and != "0", so a naive check passes even when the table
#     does not exist.
#  2. They must run in the *same* subshell. CLP keeps its connection in a backend
#     process tied to the shell, so connecting outside the $( ) leaves the query
#     with SQL1024N.
# Callers must anchor on ^[0-9]+$ so error text fails the check instead of passing it.
db_sq_shoes_count() {
  { db2 connect to sample > /dev/null 2>&1
    db2 -x "select count(*) from s1.sq_shoes" 2>/dev/null
    db2 connect reset > /dev/null 2>&1; } | tr -d ' \n'
}

load_db() {
  log "Loading SAMPLE database (S1.SQ_SHOES, S1.SHOE_COLOR_SIZES)"
  [[ -f "$DB2_PROFILE" ]] || die "Db2 profile not found at $DB2_PROFILE"
  source_db2profile
  cd "$APP_DIR"
  # dbsetup.sql opens with DROPs that fail with SQL0204N on a fresh database.
  # That is expected and harmless, but it makes db2 exit 4 — which under
  # `set -e` + pipefail would abort the whole script after the data loaded but
  # before the backend and frontend were set up. Swallow the status here and
  # verify by row count instead, which is what we actually care about.
  db2 -tvf dbsetup.sql | tail -5 || true
  cd - >/dev/null

  local count
  count="$(db_sq_shoes_count || true)"
  [[ "$count" =~ ^[0-9]+$ && "$count" != "0" ]] \
    || die "dbsetup.sql ran but S1.SQ_SHOES is still empty — check the IMPORT output above"
  log "Loaded: S1.SQ_SHOES has $count rows"
}

setup_backend() {
  log "Setting up backend venv & dependencies"
  cd "$BACKEND_DIR"

  if [[ ! -d .venv ]]; then
    command -v uv >/dev/null || die "uv not found; install from https://astral.sh/uv"
    local py
    py="$(command -v python3.12 || true)"
    [[ -n "$py" ]] || die "python3.12 not found"
    uv venv --python "$py"
  fi

  # shellcheck disable=SC1091
  source .venv/bin/activate
  uv pip install -q -r requirements.txt

  if [[ ! -f .env ]]; then
    if [[ -f .env.example ]]; then
      cp .env.example .env
      warn ".env created from .env.example — edit it with your Db2 password before re-running."
      exit 1
    else
      die "No .env and no .env.example to copy from"
    fi
  fi
  cd - >/dev/null
}

port_in_use() {
  ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$1\$"
}

start_backend() {
  if [[ -f "$BACKEND_PIDFILE" ]] && kill -0 "$(cat "$BACKEND_PIDFILE")" 2>/dev/null; then
    log "Backend already running (PID $(cat "$BACKEND_PIDFILE"))"
    return
  fi
  if port_in_use "$BACKEND_PORT"; then
    warn "Port $BACKEND_PORT is already in use (not started by this script). Run with --stop or free the port."
    return
  fi
  log "Starting backend on port $BACKEND_PORT (log: $BACKEND_LOG)"
  cd "$BACKEND_DIR"
  # shellcheck disable=SC1091
  source .venv/bin/activate
  nohup python run.py >"$BACKEND_LOG" 2>&1 &
  echo $! >"$BACKEND_PIDFILE"
  cd - >/dev/null

  for _ in {1..20}; do
    if curl -s -o /dev/null "http://localhost:$BACKEND_PORT/api/products"; then
      log "Backend ready: http://localhost:$BACKEND_PORT/api/products"
      return
    fi
    sleep 0.5
  done
  warn "Backend didn't respond in 10s — check $BACKEND_LOG"
}

setup_frontend() {
  log "Setting up frontend dependencies"
  cd "$FRONTEND_DIR"
  if [[ ! -d node_modules ]]; then
    command -v npm >/dev/null || die "npm not found"
    npm install
  fi
  cd - >/dev/null
}

start_frontend() {
  if [[ -f "$FRONTEND_PIDFILE" ]] && kill -0 "$(cat "$FRONTEND_PIDFILE")" 2>/dev/null; then
    log "Frontend already running (PID $(cat "$FRONTEND_PIDFILE"))"
    return
  fi
  if port_in_use "$FRONTEND_PORT"; then
    warn "Port $FRONTEND_PORT is already in use (not started by this script). Run with --stop or free the port."
    return
  fi
  log "Starting frontend on port $FRONTEND_PORT (log: $FRONTEND_LOG)"
  cd "$FRONTEND_DIR"
  nohup npm run dev -- --host >"$FRONTEND_LOG" 2>&1 &
  echo $! >"$FRONTEND_PIDFILE"
  cd - >/dev/null

  for _ in {1..20}; do
    if curl -s -o /dev/null "http://localhost:$FRONTEND_PORT/"; then
      log "Frontend ready: http://localhost:$FRONTEND_PORT/"
      return
    fi
    sleep 0.5
  done
  warn "Frontend didn't respond in 10s — check $FRONTEND_LOG"
}

print_urls() {
  log "Access URLs"
  echo "  The frontend calls the API with relative paths and Vite proxies /api to"
  echo "  the backend, so the backend host appears nowhere in the frontend source."
  echo "  Any URL that reaches port $FRONTEND_PORT works — and it is the only port"
  echo "  you need to forward or open."
  echo
  echo "    http://localhost:$FRONTEND_PORT/   (from this host, or a forwarded port)"
  # Unquoted on purpose: `hostname -I` is a space-separated list, and word
  # splitting drops the trailing blank that a read-loop would otherwise hand
  # back as a failing final iteration — which becomes the script's exit status.
  local ip
  for ip in $(hostname -I 2>/dev/null); do
    echo "    http://$ip:$FRONTEND_PORT/"
  done
}

main() {
  local skip_db=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --skip-db) skip_db=1 ;;
      --stop)    cmd_stop; exit 0 ;;
      --status)  cmd_status; exit 0 ;;
      -h|--help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
      *)         die "Unknown arg: $1" ;;
    esac
    shift
  done

  [[ $skip_db -eq 1 ]] || load_db
  setup_backend
  start_backend
  setup_frontend
  start_frontend
  print_urls
}

# Only run main() when executed directly, not when sourced by run.sh.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi

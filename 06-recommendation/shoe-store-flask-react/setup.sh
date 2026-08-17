#!/usr/bin/env bash
# Setup-only script: ensures the app and database are set up, without starting
# anything. Checks each piece first and only runs the work that's missing.
#
# Usage:
#   ./setup.sh             # check & set up DB, backend, frontend
#   ./setup.sh --force-db  # always reload the database (drops & re-imports)
#   ./setup.sh -h          # help

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Reuse paths and helpers (load_db, setup_backend, setup_frontend, log/warn/die).
# shellcheck disable=SC1091
source "$APP_DIR/setup_and_run.sh"

db_loaded() {
  [[ -f "$DB2_PROFILE" ]] || return 1
  source_db2profile
  local count
  count="$(db_sq_shoes_count || true)"
  [[ "$count" =~ ^[0-9]+$ && "$count" != "0" ]]
}

main_setup() {
  local force_db=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --force-db) force_db=1 ;;
      -h|--help)  sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
      *)          die "Unknown arg: $1" ;;
    esac
    shift
  done

  local did_anything=0

  if (( force_db )) || ! db_loaded; then
    if (( force_db )); then
      log "DB: --force-db given, reloading"
    else
      log "DB: S1.SQ_SHOES is empty or missing, loading"
    fi
    load_db
    did_anything=1
  else
    log "DB: S1.SQ_SHOES already populated — skipping"
  fi

  if [[ ! -d "$BACKEND_DIR/.venv" ]] || [[ ! -f "$BACKEND_DIR/.env" ]]; then
    log "Backend: setting up venv / deps / .env"
    setup_backend  # will exit if it had to copy .env.example → .env
    did_anything=1
  else
    log "Backend: venv and .env present — verifying deps are current"
    # shellcheck disable=SC1091
    source "$BACKEND_DIR/.venv/bin/activate"
    uv pip install -q -r "$BACKEND_DIR/requirements.txt"
    deactivate
  fi

  if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    log "Frontend: installing npm dependencies"
    setup_frontend
    did_anything=1
  else
    log "Frontend: node_modules present — skipping npm install"
  fi

  log "Setup complete."
  if (( did_anything )); then
    echo "  Some work was done."
  else
    echo "  Everything was already in place."
  fi
  echo "  Next: ./run.sh to start the app."
}

main_setup "$@"

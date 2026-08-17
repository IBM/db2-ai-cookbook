#!/usr/bin/env bash
# Run-only script: assumes setup is already done. Verifies prereqs, starts
# backend & frontend if not running, and prints the app URL.
#
# Usage:
#   ./run.sh             # start (if not running) and print URL
#   ./run.sh --stop      # stop both services
#   ./run.sh --status    # show what's running

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Reuse all helpers (paths, log/warn/die, port_in_use, start_backend,
# start_frontend, print_urls, cmd_stop, cmd_status) from setup_and_run.sh.
# shellcheck disable=SC1091
source "$APP_DIR/setup_and_run.sh"

verify_setup() {
  local problems=()

  [[ -d "$BACKEND_DIR/.venv" ]]      || problems+=("backend venv missing ($BACKEND_DIR/.venv)")
  [[ -f "$BACKEND_DIR/.env" ]]       || problems+=("backend .env missing ($BACKEND_DIR/.env)")
  [[ -d "$FRONTEND_DIR/node_modules" ]] || problems+=("frontend node_modules missing")

  # Check Db2 tables exist with data. Skip the check if db2 isn't on PATH yet.
  if [[ -f "$DB2_PROFILE" ]]; then
    source_db2profile
    local count
    count="$(db_sq_shoes_count || true)"
    if [[ ! "$count" =~ ^[0-9]+$ || "$count" == "0" ]]; then
      problems+=("S1.SQ_SHOES in SAMPLE is empty or unreadable")
    fi
  else
    problems+=("Db2 profile not found at $DB2_PROFILE")
  fi

  if (( ${#problems[@]} > 0 )); then
    warn "Setup looks incomplete:"
    for p in "${problems[@]}"; do echo "    - $p" >&2; done
    echo >&2
    echo "Run ./setup_and_run.sh first to finish setup." >&2
    exit 1
  fi
}

main_run() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --stop)    cmd_stop;   exit 0 ;;
      --status)  cmd_status; exit 0 ;;
      -h|--help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
      *)         die "Unknown arg: $1" ;;
    esac
    shift
  done

  verify_setup
  start_backend
  start_frontend
  print_urls
}

main_run "$@"

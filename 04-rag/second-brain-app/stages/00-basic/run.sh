#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV_DIR="$REPO_ROOT/.venv"

if [ ! -d "$VENV_DIR" ]; then
  echo "Error: .venv not found at $VENV_DIR" >&2
  echo "Create it first: python3.12 -m venv .venv" >&2
  exit 1
fi

# Kill any previously-running stage app (any stage). Matches only python
# processes launched from this project's venv, so unrelated processes
# on the system aren't touched.
PIDS=$(pgrep -f "^$VENV_DIR/bin/python " || true)
if [ -n "$PIDS" ]; then
  echo "Stopping previous app instance(s): $PIDS"
  echo "$PIDS" | xargs kill 2>/dev/null || true
  sleep 1
  PIDS=$(pgrep -f "^$VENV_DIR/bin/python " || true)
  [ -n "$PIDS" ] && echo "$PIDS" | xargs kill -9 2>/dev/null || true
fi

# Call the venv's binaries by absolute path — works even if another
# venv is already active in the parent shell.
"$VENV_DIR/bin/python" -m pip install -q -r "$SCRIPT_DIR/requirements.txt"
cd "$SCRIPT_DIR"
exec "$VENV_DIR/bin/python" app.py

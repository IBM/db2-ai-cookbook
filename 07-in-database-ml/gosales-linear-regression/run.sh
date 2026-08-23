#!/usr/bin/env bash
# Start (or restart) the demo. ./run.sh --stop to stop it.
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-5050}"
PIDFILE=/tmp/idax-demo.pid
LOG=/tmp/idax-demo.log

stop() {
  if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    kill "$(cat "$PIDFILE")" 2>/dev/null || true; sleep 1
    kill -9 "$(cat "$PIDFILE")" 2>/dev/null || true
  fi
  rm -f "$PIDFILE"
}

[[ "${1:-}" == "--stop" ]] && { stop; echo "stopped"; exit 0; }
[[ "${1:-}" == "--status" ]] && {
  if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null
  then echo "running (PID $(cat "$PIDFILE"), port $PORT)"; else echo "not running"; fi; exit 0; }

stop
cd "$APP_DIR"
source .venv/bin/activate
nohup python app.py >"$LOG" 2>&1 &
echo $! >"$PIDFILE"
for _ in {1..25}; do
  curl -s -o /dev/null "http://localhost:$PORT/" && { echo "ready:  http://localhost:$PORT/"; exit 0; }
  sleep 0.4
done
echo "did not come up — see $LOG" >&2; exit 1

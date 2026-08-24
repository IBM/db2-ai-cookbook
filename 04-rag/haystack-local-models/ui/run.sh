#!/usr/bin/env bash
# run.sh — start the web UI with ONE command.
#
#   ./ui/run.sh        http://127.0.0.1:8000
#
# There is no offline mode: both workflows are live. Before starting, make sure the two
# llama.cpp servers are up and Db2 is reachable:
#
#   scripts/llama-servers.sh start
#   scripts/llama-servers.sh status
#
# Env: PORT (default 8000) and HOST (default 127.0.0.1). Loopback by default, so over
# Remote-SSH the browser needs the port forwarded. To skip forwarding:
#
#   HOST=0.0.0.0 ./ui/run.sh     reachable at http://<this-host-ip>:8000
#
# That serves an unauthenticated app — which can overwrite the index — to the whole
# network. Trusted networks only.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"
PORT="${PORT:-8000}"
HOST="${HOST:-127.0.0.1}"

# 0.0.0.0 is a bind address, not a browsable one — show a reachable IP instead.
if [ "$HOST" = "0.0.0.0" ]; then
    SHOWN="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
    SHOWN="${SHOWN:-$(hostname)}"
else
    SHOWN="$HOST"
fi

case "$HOST" in
    127.0.0.1|localhost) ;;
    *) echo "WARNING: binding to $HOST publishes the UI on the network. It has no" >&2
       echo "         authentication, and anyone reaching it can replace the index." >&2
       echo "         Use it only on a network you trust." >&2 ;;
esac

# fastapi/uvicorn/haystack/ibm_db all live in the recipe venv, not the system python.
PY="$REPO/.venv/bin/python"
if [ ! -x "$PY" ]; then
    echo "No venv at $PY — see docs/setup.md step 5." >&2; exit 1
fi
if ! "$PY" -c "import fastapi, uvicorn, multipart" 2>/dev/null; then
    echo "UI dependencies missing. Install them with:" >&2
    echo "    $PY -m pip install -r ui/requirements.txt" >&2
    exit 1
fi

# A previous server orphaned by a closed terminal keeps holding the port and would block
# the bind ("address already in use").
if fuser "${PORT}/tcp" >/dev/null 2>&1; then
    echo "Port ${PORT} busy — stopping the previous server first."
    fuser -k "${PORT}/tcp" >/dev/null 2>&1 || true
    sleep 1
fi

echo "UI → http://$SHOWN:$PORT   (API docs at /docs)"
cd "$HERE" && PYTHONPATH="$REPO/src" exec "$PY" -m uvicorn api:app --host "$HOST" --port "$PORT"

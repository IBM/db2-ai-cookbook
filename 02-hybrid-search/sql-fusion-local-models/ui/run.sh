#!/usr/bin/env bash
# run.sh — start the demo with ONE command.
#
#   ./ui/run.sh           OFFLINE (default): serves the static UI + frozen
#                         fixtures.json with python's stdlib server. No Db2, no
#                         pip deps — this is the conference/talk path.
#
#   ./ui/run.sh --live    LIVE: FastAPI backend answers typed queries against the
#                         real engine (runs as the Db2 instance owner, local
#                         connection). For Q&A / ad-hoc queries.
#
# Env: PORT (default 8000) and HOST (default 127.0.0.1). Both modes bind loopback,
# so over Remote-SSH the browser needs the port forwarded. To skip forwarding:
#
#   HOST=0.0.0.0 ./ui/run.sh --live    reachable at http://<this-host-ip>:8000
#
# That serves an unauthenticated app to the whole network — trusted networks only.
#
# Build/refresh the fixtures first with:  ./ui/build_fixtures.sh

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"
OWNER="${DB2_INSTANCE_OWNER:-db2inst1}"
PORT="${PORT:-8000}"
# Loopback by default: over Remote-SSH the browser reaches it through a forwarded
# port. Set HOST=0.0.0.0 to bind every interface and skip tunnelling altogether.
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
    *) echo "WARNING: binding to $HOST publishes the demo on the network. It has no" >&2
       echo "         authentication, and the staged .env holds the Db2 password." >&2
       echo "         Use it only on a network you trust." >&2 ;;
esac

# Run a command as the Db2 instance owner. If we ARE already that user (the normal
# "operate as db2inst1" case), run it directly — no sudo, which db2inst1 need not
# have. Only drop privileges via sudo when a different user launched this script.
as_owner() {
    if [ "$(id -un)" = "$OWNER" ]; then
        bash -lc "$1"
    else
        sudo -iu "$OWNER" bash -lc "$1"
    fi
}

if [ "${1:-}" = "--live" ]; then
    # Stage everything the instance owner can read (it can't read /home/<you>).
    # Namespaced by port: the stage is wiped on every launch, so a shared path would
    # let a second instance delete the static files out from under a server already
    # running on another port.
    STAGE="/tmp/hybrid-ui-$PORT"
    rm -rf "$STAGE"; mkdir -p "$STAGE"
    cp "$HERE/api.py" "$HERE/build_fixtures.py" "$HERE/demo_view.py" \
       "$HERE/queries.json" "$HERE/demo_queries.json" "$STAGE/"
    cp -r "$REPO/src/hybrid_search" "$STAGE/"      # the search engine package
    cp -r "$HERE/static" "$STAGE/static"
    # api.py's book title/author lookup. Staged under the stage root because api.py
    # resolves it relative to its own location, which is $STAGE when live.
    mkdir -p "$STAGE/data"
    [ -f "$REPO/data/corpus.csv" ] && cp "$REPO/data/corpus.csv" "$STAGE/data/"
    [ -f "$REPO/.env" ] && cp "$REPO/.env" "$STAGE/.env"   # fusion weights/gates/pool
    chmod -R a+rX "$STAGE"
    # ...but never world-readable: .env holds the Db2 password. Must follow the
    # recursive chmod above, which would otherwise leave it 0644 in /tmp.
    [ -f "$STAGE/.env" ] && chmod 600 "$STAGE/.env"
    # uvicorn/fastapi/ibm_db live in the repo venv, not the system python.
    PY="$REPO/.venv/bin/python"; [ -x "$PY" ] || PY="python3"
    # A previous server orphaned by a closed terminal keeps holding the port and
    # would block the bind ("address already in use"). It runs as $OWNER, so free
    # the port as $OWNER before starting.
    if as_owner "fuser ${PORT}/tcp" >/dev/null 2>&1; then
        echo "Port ${PORT} busy — stopping the previous live server first."
        as_owner "fuser -k ${PORT}/tcp" >/dev/null 2>&1 || true
        sleep 1
    fi
    echo "LIVE  → http://$SHOWN:$PORT   (real Db2 search as $OWNER; docs at /docs)"
    as_owner "cd '$STAGE' && DB2_HOST=local '$PY' -m uvicorn api:app --host $HOST --port $PORT"
else
    [ -f "$HERE/static/fixtures.json" ] || {
        echo "No fixtures yet — run ./ui/build_fixtures.sh first." >&2; exit 1; }
    # Free the port if a previous offline server (this user) is still holding it.
    if fuser "${PORT}/tcp" >/dev/null 2>&1; then
        echo "Port ${PORT} busy — stopping the previous server first."
        fuser -k "${PORT}/tcp" >/dev/null 2>&1 || true
        sleep 1
    fi
    echo "OFFLINE → http://$SHOWN:$PORT   (frozen fixtures, no Db2 needed)"
    cd "$HERE/static" && exec python3 -m http.server "$PORT" --bind "$HOST"
fi

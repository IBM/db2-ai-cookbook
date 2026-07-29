#!/usr/bin/env bash
# build_fixtures.sh — freeze every curated query x 3 strategies into fixtures.json.
#
# Runs build_fixtures.py as the Db2 instance owner over a LOCAL connection (the
# only fast/working path), then copies the result back into ui/static/ for the
# offline demo. Run this whenever the corpus, model, or fusion knobs change.
#
#   ./ui/build_fixtures.sh

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"      # ui/
REPO="$(dirname "$HERE")"
OWNER="${DB2_INSTANCE_OWNER:-db2inst1}"

# Stage files the instance owner can read (it can't read /home/<you>).
rm -rf /tmp/hybrid_search
cp "$HERE/build_fixtures.py" "$HERE/queries.json" /tmp/
cp -r "$REPO/src/hybrid_search" /tmp/           # the search engine package
chmod 644 /tmp/build_fixtures.py /tmp/queries.json
chmod -R a+rX /tmp/hybrid_search
rm -f /tmp/fixtures.json

# Stage .env next to the package so core._find_env() picks up the tuned HYBRID_*
# knobs. Without this the builder silently freezes fixtures using code defaults.
[ -f "$REPO/.env" ] && { cp "$REPO/.env" /tmp/hybrid_search/.env; chmod 600 /tmp/hybrid_search/.env; }

# The repo venv has ibm_db + the engine package; system python3 has neither.
PY="$REPO/.venv/bin/python"; [ -x "$PY" ] || PY="python3"

# Only sudo when we're NOT already the instance owner — avoids the sudoers
# dependency (a fresh Db2 owner isn't in sudoers) and sudo -i's env/cwd reset.
if [ "$(id -un)" = "$OWNER" ]; then
    DB2_HOST=local "$PY" /tmp/build_fixtures.py
else
    sudo -iu "$OWNER" bash -lc "DB2_HOST=local '$PY' /tmp/build_fixtures.py"
fi

# Publish the data the static UI serves.
mkdir -p "$HERE/static"
cp /tmp/fixtures.json "$HERE/static/fixtures.json"
cp "$HERE/queries.json" "$HERE/static/queries.json"
echo "published -> ui/static/fixtures.json , ui/static/queries.json"

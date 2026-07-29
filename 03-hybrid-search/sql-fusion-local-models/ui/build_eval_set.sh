#!/usr/bin/env bash
# build_eval_set.sh — freeze the gold passages for the featured eval queries into
# ui/static/eval_set.json, which powers the "Golden eval set" page.
#
# Like build_fixtures.sh, it runs as the Db2 instance owner over a LOCAL
# connection. Cheap (no embedding calls) — just reads chunk text by id.
# Re-run it whenever the corpus or the featured query set changes.
#
#   ./ui/build_eval_set.sh

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"      # ui/
REPO="$(dirname "$HERE")"
OWNER="${DB2_INSTANCE_OWNER:-db2inst1}"

# Stage files the instance owner can read (it can't read /home/<you>).
rm -rf /tmp/hybrid_search
cp "$HERE/build_eval_set.py" "$HERE/queries.json" /tmp/
cp -r "$REPO/src/hybrid_search" /tmp/           # the search engine package
chmod 644 /tmp/build_eval_set.py /tmp/queries.json
chmod -R a+rX /tmp/hybrid_search
rm -f /tmp/eval_set.json

# Stage .env next to the package so core._find_env() picks up the tuned HYBRID_*
# knobs. Without this the builder silently freezes data using code defaults.
[ -f "$REPO/.env" ] && { cp "$REPO/.env" /tmp/hybrid_search/.env; chmod 600 /tmp/hybrid_search/.env; }

# The repo venv has ibm_db + the engine package; system python3 has neither.
PY="$REPO/.venv/bin/python"; [ -x "$PY" ] || PY="python3"

# Only sudo when we're NOT already the instance owner — avoids the sudoers
# dependency (a fresh Db2 owner isn't in sudoers) and sudo -i's env/cwd reset.
if [ "$(id -un)" = "$OWNER" ]; then
    DB2_HOST=local "$PY" /tmp/build_eval_set.py
else
    sudo -iu "$OWNER" bash -lc "DB2_HOST=local '$PY' /tmp/build_eval_set.py"
fi

# Publish the data the static UI serves.
mkdir -p "$HERE/static"
cp /tmp/eval_set.json "$HERE/static/eval_set.json"
echo "published -> ui/static/eval_set.json"

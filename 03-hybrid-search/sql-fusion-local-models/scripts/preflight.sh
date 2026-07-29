#!/usr/bin/env bash
# preflight.sh — verify everything 1_ingest.sql needs BEFORE it touches the table.
#
# Why this exists: if OpenSearch is down, the ingest fails in a way that points
# nowhere near the real cause. The chain is:
#     OpenSearch down -> SYSTS_DROP fails (SQL20427N)
#                     -> DROP TABLE blocked by the text index (SQL20536N)
#                     -> CREATE TABLE fails (SQL0601N)
#                     -> IMPORT runs against the OLD table
#                     -> every row rejected as a duplicate key (SQL0803N)
# You end up staring at "92 rows rejected" with no hint to start a service.
#
# Waits for services rather than failing instantly, because 0_start-services.sh
# backgrounds OpenSearch and it needs ~1 min to accept connections.
#
#   ./scripts/preflight.sh            # then: db2 -tvf scripts/1_ingest.sql
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"

EMBED_PORT="${EMBED_PORT:-8085}"
OS_PORT="${OPENSEARCH_PORT:-9200}"
WAIT_SECS="${PREFLIGHT_WAIT:-90}"

FAIL=0
ok()  { echo "  PASS  $1"; }
bad() { echo "  FAIL  $1"; FAIL=1; }

# Poll a URL until it answers or we run out of patience.
wait_for() {
    local url="$1" label="$2" hint="$3" waited=0
    until curl -s -o /dev/null -m3 "$url"; do
        if [ "$waited" -ge "$WAIT_SECS" ]; then
            bad "$label not responding after ${WAIT_SECS}s — $hint"
            return 1
        fi
        [ "$waited" = 0 ] && echo "  ....  waiting for $label (up to ${WAIT_SECS}s)"
        sleep 3; waited=$((waited + 3))
    done
    ok "$label"
}

echo "Preflight (ingest prerequisites):"

# 1. Db2 instance must actually be started, not merely installed.
if command -v db2gcf >/dev/null 2>&1 && db2gcf -s 2>/dev/null | grep -qi available; then
    ok "Db2 instance running"
else
    bad "Db2 not started — run: db2start   (or ./scripts/0_start-services.sh)"
fi

# 2. OpenSearch backs Db2 Text Search. Without it the text-index DDL fails and
#    silently poisons the whole ingest (see the chain above).
wait_for "http://127.0.0.1:${OS_PORT}" "OpenSearch :${OS_PORT}" \
         "start it with ./scripts/0_start-services.sh"

# 3. Embedding server serves TO_EMBEDDING during the UPDATE step.
wait_for "http://127.0.0.1:${EMBED_PORT}/health" "embedding server :${EMBED_PORT}" \
         "start it with ./scripts/0_start-services.sh"

# 4. The corpus IMPORT path is client-relative — ingest must be run from the repo root.
if [ -f "$REPO/data/corpus.csv" ]; then
    ok "data/corpus.csv present ($(($(wc -l < "$REPO/data/corpus.csv") - 1)) rows)"
else
    bad "data/corpus.csv missing — ingest IMPORTs it relative to the repo root"
fi

echo
if [ "$FAIL" = 0 ]; then
    echo "PREFLIGHT: PASS — safe to run:  db2 -tvf scripts/1_ingest.sql"
else
    echo "PREFLIGHT: FAIL — fix the above before ingesting (running anyway will"
    echo "                  fail with confusing duplicate-key errors, not a clear cause)."
    exit 1
fi

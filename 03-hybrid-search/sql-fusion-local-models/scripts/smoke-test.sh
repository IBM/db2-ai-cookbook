#!/usr/bin/env bash
# smoke-test.sh — end-to-end "did my setup work?" check.
# Verifies the three required services are up and that a real hybrid search runs
# through the engine and returns results. Corpus-agnostic (passes on any ingested
# corpus); prints the top hit so you can eyeball it. Exits non-zero on any failure.
#
#   ./scripts/smoke-test.sh
set -uo pipefail

# Same overrides 0_start-services.sh honors, so a non-default port still smoke-tests.
EMBED_PORT="${EMBED_PORT:-8085}"
OS_PORT="${OPENSEARCH_PORT:-9200}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"
FAIL=0
ok()  { echo "  PASS  $1"; }
bad() { echo "  FAIL  $1"; FAIL=1; }

echo "Services:"
if command -v db2gcf >/dev/null && db2gcf -s 2>/dev/null | grep -qi available; then
  ok "Db2 available"
else
  bad "Db2 not available — run ./scripts/0_start-services.sh"
fi
curl -s -o /dev/null -m3 "http://127.0.0.1:${OS_PORT}"        && ok "OpenSearch :${OS_PORT}"       || bad "OpenSearch down — ./scripts/0_start-services.sh"
curl -s -o /dev/null -m3 "http://127.0.0.1:${EMBED_PORT}/health" && ok "embedding server :${EMBED_PORT}" || bad "embedding server down — ./scripts/0_start-services.sh"

echo "Search (engine end-to-end):"
PY="$REPO/.venv/bin/python"; [ -x "$PY" ] || PY=python3
out=$(cd "$REPO" && PYTHONPATH=src DB2_HOST=local "$PY" - <<'PYEOF' 2>/dev/null
try:
    from hybrid_search import core as h
    conn = h.connect()
    r = h.hybrid(conn, "a book about building better habits", 3)
    if r:
        top = h.snippet(conn, r[0][0], 60)
        print(f"OK\t{len(r)}\t#{r[0][0]} {top}")
    else:
        print("EMPTY\t0\t(no results — is the corpus ingested? run 1_ingest.sql)")
except Exception as e:
    print(f"ERR\t0\t{type(e).__name__}: {e}")
PYEOF
)
status=$(printf '%s' "$out" | cut -f1)
detail=$(printf '%s' "$out" | cut -f3-)
if [ "$status" = "OK" ]; then ok "hybrid search returns results — top: $detail"; else bad "hybrid search: $detail"; fi

echo
if [ "$FAIL" = 0 ]; then echo "SMOKE TEST: PASS"; else echo "SMOKE TEST: FAIL"; exit 1; fi

#!/usr/bin/env bash
# 3_stop-services.sh — stop the llama.cpp embedding server, OpenSearch, and Db2.
# Run as the Db2 instance owner. Tries each even if one isn't running.
# (Db2 won't stop while a client holds a connection — close those first.)
set -uo pipefail

EMBED_PORT="${EMBED_PORT:-8085}"
RERANK_PORT="${RERANK_PORT:-8087}"
OS_HOME="${OPENSEARCH_HOME:-/opt/opensearch}"

# llama.cpp embedding server
if fuser -k "${EMBED_PORT}/tcp" 2>/dev/null; then echo "Embeddings: stopped"; else echo "Embeddings: not running"; fi

# cross-encoder reranker (started by 0_start-services.sh when its model is present)
if fuser -k "${RERANK_PORT}/tcp" 2>/dev/null; then echo "Reranker: stopped"; else echo "Reranker: not running"; fi

# OpenSearch (runs as db2inst1 — same owner as this script, so no sudo needed)
if [ -f "$OS_HOME/opensearch.pid" ] && kill "$(cat "$OS_HOME/opensearch.pid")" 2>/dev/null; then
  echo "OpenSearch: stopped"
else
  echo "OpenSearch: not running (or no pid file)"
fi

# Db2
if db2stop 2>/dev/null; then echo "Db2: stopped"; else echo "Db2: not running, or has active connections"; fi

#!/usr/bin/env bash
# 0_start-services.sh — start the services the pipeline needs: Db2, OpenSearch, the
# llama.cpp embedding server, and (if its model is present) the cross-encoder
# reranker. Run as the Db2 instance owner. Idempotent: skips anything already up.
# Complete the one-time setup (see docs/) beforehand.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LLAMA="${LLAMA_CPP_DIR:-$HOME/llama.cpp}"
MODEL="${BGE_GGUF:-$HOME/models/bge-small-en-v1.5/bge-small-en-v1.5-q8_0.gguf}"
EMBED_PORT="${EMBED_PORT:-8085}"
# The Db2 embedding model (scripts/1_ingest.sql) hardcodes port 8085. If you override
# EMBED_PORT here, TO_EMBEDDING will still call 8085 and fail at search time. Warn now.
[ "$EMBED_PORT" = "8085" ] || echo "WARNING: EMBED_PORT=$EMBED_PORT but 1_ingest.sql's model URL hardcodes 8085 — edit the URL there too, or TO_EMBEDDING will fail." >&2
OS_HOME="${OPENSEARCH_HOME:-/opt/opensearch}"
OS_PORT="${OPENSEARCH_PORT:-9200}"

# Db2
if db2gcf -s 2>/dev/null | grep -q Available; then
  echo "Db2: already running"
else
  db2start && echo "Db2: started"
fi

# OpenSearch
if curl -s -o /dev/null "http://localhost:${OS_PORT}"; then
  echo "OpenSearch: already running on :${OS_PORT}"
else
  # Redirect the JVM's early startup notices (incubator/Unsafe/JNA warnings) off the
  # terminal; OpenSearch's real logs still go to $OS_HOME/logs/. Keeps this script's
  # output clean. -d already daemonizes.
  "$OS_HOME/bin/opensearch" -d -p "$OS_HOME/opensearch.pid" >/tmp/opensearch-start.log 2>&1
  echo "OpenSearch: starting on :${OS_PORT} (~1 min to be ready)"
fi

# llama.cpp embedding server
if curl -s -o /dev/null "http://127.0.0.1:${EMBED_PORT}/health"; then
  echo "Embeddings: already running on :${EMBED_PORT}"
else
  nohup "$LLAMA/build/bin/llama-server" -m "$MODEL" --embedding --pooling cls \
    --ctx-size 512 --host 127.0.0.1 --port "$EMBED_PORT" >/tmp/llama-server.log 2>&1 &
  echo "Embeddings: starting on :${EMBED_PORT} (log: /tmp/llama-server.log)"
fi

# Cross-encoder reranker (its own llama-server; used by live search when RERANK_ON=1
# or the Search tab's Rerank button). Started only when the model is downloaded, so
# machines that don't use reranking are unaffected. Set RERANK_ON=1 in .env to apply
# it to every search.
RERANK_PORT="${RERANK_PORT:-8087}"
RERANK_GGUF="${RERANK_GGUF:-$HOME/models/bge-reranker-v2-m3/bge-reranker-v2-m3-Q4_K_M.gguf}"
if curl -s -o /dev/null "http://127.0.0.1:${RERANK_PORT}/health"; then
  echo "Reranker: already running on :${RERANK_PORT}"
elif [ -f "$RERANK_GGUF" ]; then
  "$HERE/rerank/start_rerank_server.sh" || echo "Reranker: failed to start — see /tmp/rerank-server.log"
else
  echo "Reranker: model not found at $RERANK_GGUF — skipping (see the README, llama.cpp models, to enable)"
fi

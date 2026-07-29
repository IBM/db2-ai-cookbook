#!/usr/bin/env bash
# start_rerank_server.sh — start the cross-encoder reranker as its OWN llama-server
# process (separate from the embedding server, since --reranking and --embeddings are
# mutually exclusive at launch). Idempotent; persistent. Log: /tmp/rerank-server.log
set -euo pipefail

LLAMA="${LLAMA_CPP_DIR:-$HOME/llama.cpp}/build/bin/llama-server"
MODEL="${RERANK_GGUF:-$HOME/models/bge-reranker-v2-m3/bge-reranker-v2-m3-Q4_K_M.gguf}"
PORT="${RERANK_PORT:-8087}"
ALIAS="${RERANK_ALIAS:-reranker}"

if curl -s -o /dev/null -m 3 "http://127.0.0.1:${PORT}/health"; then
  echo "Reranker: already running on :${PORT}"
  exit 0
fi
[ -x "$LLAMA" ] || { echo "llama-server not found at $LLAMA" >&2; exit 1; }
[ -f "$MODEL" ] || { echo "reranker model not found at $MODEL" >&2; exit 1; }

nohup "$LLAMA" -m "$MODEL" --reranking --alias "$ALIAS" --pooling rank \
  --ctx-size 2048 --host 127.0.0.1 --port "$PORT" >/tmp/rerank-server.log 2>&1 &
echo "Reranker: starting bge-reranker-v2-m3 on :${PORT} (log: /tmp/rerank-server.log)"

for _ in $(seq 1 40); do
  curl -s -o /dev/null -m 2 "http://127.0.0.1:${PORT}/health" && { echo "Reranker: ready"; exit 0; }
  sleep 1
done
echo "Reranker: did not become healthy in time — check /tmp/rerank-server.log" >&2
exit 1

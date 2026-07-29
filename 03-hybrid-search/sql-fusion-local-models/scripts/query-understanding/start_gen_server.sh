#!/usr/bin/env bash
# Query-understanding generation server: Qwen2.5-3B-Instruct on an OpenAI-compatible
# /v1 endpoint, JSON-schema-constrained (server-side grammar), greedy/deterministic,
# small n-predict. Warm + persistent. Separate from the bge embedding server (:8085).
set -uo pipefail
LLAMA="${LLAMA_CPP_DIR:-$HOME/llama.cpp}"
MODEL="${QU_GGUF:-$HOME/models/qwen2.5-3b-instruct/Qwen2.5-3B-Instruct-Q4_K_M.gguf}"
PORT="${QU_GEN_PORT:-8086}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if curl -s -o /dev/null "http://127.0.0.1:${PORT}/health"; then
  echo "QU gen server: already running on :${PORT}"; exit 0
fi
nohup "$LLAMA/build/bin/llama-server" -m "$MODEL" \
  --host 127.0.0.1 --port "$PORT" --ctx-size 2048 --n-predict 96 \
  --temp 0 --top-k 1 --grammar-file "$HERE/qu_gen.gbnf" \
  --parallel 2 >/tmp/qu-gen-server.log 2>&1 &
echo "QU gen server: starting on :${PORT} (log: /tmp/qu-gen-server.log; ~20s to load)"

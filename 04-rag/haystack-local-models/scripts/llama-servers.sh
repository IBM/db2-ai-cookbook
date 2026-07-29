#!/usr/bin/env bash
# Start/stop the two llama.cpp servers this project talks to.
#
#   embeddings : bge-small-en-v1.5   :8081  (--embedding --pooling cls, dim 384)
#   generation : Qwen2.5-3B-Instruct :8080
#
# One llama-server process serves one model, so the two roles are two processes.
# Both expose OpenAI-compatible /v1 endpoints, which is all Haystack needs.
set -euo pipefail

LLAMA_BIN="${LLAMA_BIN:-$HOME/llama.cpp/build/bin/llama-server}"
MODELS_DIR="${MODELS_DIR:-$HOME/models}"
LOG_DIR="${LOG_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/logs}"

EMBED_MODEL_PATH="$MODELS_DIR/bge-small-en-v1.5/bge-small-en-v1.5-q8_0.gguf"
CHAT_MODEL_PATH="$MODELS_DIR/qwen2.5-3b-instruct/Qwen2.5-3B-Instruct-Q4_K_M.gguf"
EMBED_PORT="${EMBED_PORT:-8081}"
CHAT_PORT="${CHAT_PORT:-8080}"
EMBED_ALIAS="bge-small-en-v1.5"
CHAT_ALIAS="qwen2.5-3b-instruct"

mkdir -p "$LOG_DIR"

wait_ready() {  # $1=port $2=label — -f matters: /health answers 503 while the model loads
  local port=$1 label=$2
  for _ in $(seq 180); do
    if curl -sf -o /dev/null "http://127.0.0.1:$port/health"; then
      echo "  $label ready on :$port"
      return 0
    fi
    sleep 1
  done
  echo "  $label FAILED to become ready — see $LOG_DIR/$label.log" >&2
  return 1
}

start() {
  [[ -x "$LLAMA_BIN" ]] || { echo "llama-server not found at $LLAMA_BIN" >&2; exit 1; }

  if curl -sf -o /dev/null "http://127.0.0.1:$EMBED_PORT/health"; then
    echo "  embeddings already running on :$EMBED_PORT"
  else
    nohup "$LLAMA_BIN" -m "$EMBED_MODEL_PATH" --alias "$EMBED_ALIAS" \
      --embedding --pooling cls --ctx-size 512 \
      --host 127.0.0.1 --port "$EMBED_PORT" > "$LOG_DIR/embeddings.log" 2>&1 &
    wait_ready "$EMBED_PORT" embeddings
  fi

  if curl -sf -o /dev/null "http://127.0.0.1:$CHAT_PORT/health"; then
    echo "  chat already running on :$CHAT_PORT"
  else
    nohup "$LLAMA_BIN" -m "$CHAT_MODEL_PATH" --alias "$CHAT_ALIAS" \
      --ctx-size 2048 \
      --host 127.0.0.1 --port "$CHAT_PORT" > "$LOG_DIR/chat.log" 2>&1 &
    wait_ready "$CHAT_PORT" chat
  fi
}

stop() {
  for port in "$EMBED_PORT" "$CHAT_PORT"; do
    if fuser -k "$port/tcp" 2>/dev/null; then echo "  stopped :$port"; else echo "  nothing on :$port"; fi
  done
}

status() {
  for pair in "embeddings:$EMBED_PORT" "chat:$CHAT_PORT"; do
    local label=${pair%%:*} port=${pair##*:}
    if curl -sf -o /dev/null "http://127.0.0.1:$port/health"; then
      echo "  $label  :$port  up    $(curl -s "http://127.0.0.1:$port/v1/models" \
        | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"][0]["id"])' 2>/dev/null)"
    else
      echo "  $label  :$port  down"
    fi
  done
}

case "${1:-status}" in
  start)  start ;;
  stop)   stop ;;
  status) status ;;
  *) echo "usage: $0 {start|stop|status}" >&2; exit 2 ;;
esac

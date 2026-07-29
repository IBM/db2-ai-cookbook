#!/usr/bin/env bash
# Start vLLM as an OpenAI-compatible *embedding* server for VLM2Vec-Full on CPU.
# Logs go to server.log in this folder. First run downloads the model (several GB),
# so be patient — watch server.log until you see "Uvicorn running on".
set -e
cd "$(dirname "$0")"
source .venv/bin/activate

# How much RAM vLLM may use for the KV cache (GB). Small is fine for embeddings.
export VLLM_CPU_KVCACHE_SPACE=4

echo "Starting vLLM (CPU). Logs -> server.log"
nohup vllm serve TIGER-Lab/VLM2Vec-Full \
  --runner pooling \
  --convert embed \
  --trust-remote-code \
  --chat-template "$(pwd)/vlm2vec_phi3v.jinja" \
  --max-model-len 4096 \
  --port 8000 \
  > server.log 2>&1 &

echo "vLLM started in background, PID $!"
echo "Ready when this returns the model:  curl -s http://localhost:8000/v1/models"

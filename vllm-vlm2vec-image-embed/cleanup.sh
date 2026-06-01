#!/usr/bin/env bash
# Stop the vLLM server started by serve.sh.
pkill -f "vllm serve"
echo "Sent kill signal to any 'vllm serve' process."

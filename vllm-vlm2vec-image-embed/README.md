# Image embeddings with vLLM (CPU)

Send a JPEG to a local vLLM server, get back a 3072-dimensional vector that represents the image's meaning. Minimal, learning-focused, CPU-only.

> **Tested on:** Red Hat Enterprise Linux 9.6 (Plow), Python 3.12, CPU-only (AMD EPYC, AVX2, no GPU), vLLM 0.22.0 built from source. See the [Appendix](#appendix--rebuilding-venv-from-scratch-on-this-host) for why this host needed a source build.

## Quick start

```bash
cd vllm-vlm2vec-image-embed
source .venv/bin/activate

./serve.sh                              # starts vLLM, logs to server.log
curl -s http://localhost:8000/health    # wait for 200 (~10 min on first run)

python embed_image.py                   # send the image, print the vector
./cleanup.sh                            # stop the server
```

First start downloads ~8 GB of weights and JIT-compiles for CPU — expect ~10 minutes before it's ready.

## What you'll see

```
HTTP status: 200
Embedding dimension: 3072
First 10 values: [0.0065, 0.0142, 0.0245, 0.0220, 0.0177, ...]
```

That vector is the same kind of object you know from text embeddings — usable for similarity search, clustering, or as input to a downstream model. The only new thing is that the "document" is an image.

The first request after startup takes ~2–3 minutes (one-time CPU warmup/compile); warm requests are ~20–25 seconds. Production uses GPUs for a reason.

## How it works

Four layers from model to network:

| Layer | What it does |
|---|---|
| **VLM2Vec-Full** | Trained neural network. Maps pixels → 3072-dim vector. From TIGER-Lab, built on Phi-3.5-vision. |
| **PyTorch (CPU)** | Math engine running the model's tensor operations on your CPU. |
| **Transformers** | Loads the model architecture and weights from Hugging Face. |
| **vLLM** | Wraps the model in an OpenAI-compatible HTTP server. Handles parsing, batching, lifecycle. |

The Python client (`embed_image.py`) just speaks REST — read image, build JSON, POST, parse response. Uses only `requests` and the standard library.

### Request flow

```
sample.jpg  →  base64 encode  →  POST /v1/embeddings
                                        │
                                        ▼
                              ┌─── vLLM server ────┐
                              │ decode → tensor    │
                              │ PyTorch forward    │
                              │ wrap as JSON       │
                              └────────────────────┘
                                        │
                                        ▼
                              [3072 floats] → print
```

## The API shape

vLLM's image-embedding endpoint is a **superset** of OpenAI's spec. Same URL path (`/v1/embeddings`) and same response shape, but the request body uses `messages` (borrowed from OpenAI's vision Chat Completions API) instead of OpenAI's text-only `input` array.

OpenAI doesn't actually offer image embeddings — there's no official standard. vLLM extended OpenAI's pattern by reusing the vision chat format.

**Request:**

```json
{
  "model": "TIGER-Lab/VLM2Vec-Full",
  "messages": [{
    "role": "user",
    "content": [
      {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}},
      {"type": "text", "text": "Represent the given image."}
    ]
  }],
  "encoding_format": "float"
}
```

**Response:**

```json
{
  "object": "list",
  "data": [{
    "object": "embedding",
    "index": 0,
    "embedding": [0.00653, 0.01422, 0.02455, ...]
  }],
  "model": "TIGER-Lab/VLM2Vec-Full",
  "usage": {...}
}
```

## What's not here

Deliberately omitted: GPU support, auth, TLS, client batching, error handling, retries, vector storage. To go further:

- Store vectors in a vector store such as Db2, or a library like FAISS, for search
- Batch multiple images per request
- Embed text queries with the same model and compare against images (shared space)
- Move to a GPU host for usable latency

---

## Appendix — Rebuilding `.venv` from scratch on this host

This venv was built from source because of two host-specific issues on this RHEL 9.6 VM:

1. **No prebuilt vLLM CPU wheel works here.** Official wheels need glibc ≥ 2.35; RHEL 9.6 has 2.34.
2. **vLLM's CPU kernels normally require AVX-512.** This AMD EPYC VM has only AVX2.

On any host with AVX-512 and glibc ≥ 2.35 (or via the official `vllm-cpu` container), skip everything below and run:

```bash
pip install vllm --extra-index-url https://wheels.vllm.ai/cpu
```

### Steps used on this host

```bash
# 1. System build deps (gcc ≥ 12.3 required for vLLM's x86 CPU backend)
sudo dnf install -y python3.12-devel numactl-devel gcc-toolset-13

# 2. Fresh venv in the module folder
mkdir -p ~/multimodal-embeddings/vllm-vlm2vec-image-embed && cd ~/multimodal-embeddings/vllm-vlm2vec-image-embed
python3 -m venv .venv && source .venv/bin/activate && pip install -U pip

# 3. vLLM source + CPU dependency set (torch 2.11.0+cpu)
git clone --depth 1 --branch v0.22.0 https://github.com/vllm-project/vllm.git /tmp/vllm-build
cd /tmp/vllm-build
pip install "cmake>=3.26" wheel packaging ninja setuptools-rust setuptools-scm jinja2
pip install -r requirements/cpu.txt --extra-index-url https://download.pytorch.org/whl/cpu
pip install "torchvision==0.26.0+cpu" "torchaudio==2.11.0+cpu" \
  --extra-index-url https://download.pytorch.org/whl/cpu

# 4. AVX2-only patch — build _C from AVX2 sources instead of AVX-512+AMX.
#    UNSUPPORTED; only because this CPU lacks AVX-512. Drops kernels (AVX-512/AMX,
#    shared-mem TP, MoE, weight-only quant) that a single-process dense embedding
#    model doesn't use.
sed -i 's#SOURCES ${VLLM_EXT_SRC_AVX512} ${VLLM_EXT_SRC_SGL}#SOURCES ${VLLM_EXT_SRC_AVX2}#' cmake/cpu_extension.cmake
sed -i 's#COMPILE_FLAGS ${CXX_COMPILE_FLAGS_AVX512_AMX}#COMPILE_FLAGS ${CXX_COMPILE_FLAGS_AVX2}#' cmake/cpu_extension.cmake
sed -i '/target_compile_definitions(_C PRIVATE "-DCPU_CAPABILITY_AMXBF16")/d' cmake/cpu_extension.cmake

# 5. Compile (~15 min on 16 cores)
source /opt/rh/gcc-toolset-13/enable
export VLLM_TARGET_DEVICE=cpu CC=$(which gcc) CXX=$(which g++) CMAKE_BUILD_PARALLEL_LEVEL=$(nproc)
pip install . --no-build-isolation

# 6. Client deps + sample image
cd ~/multimodal-embeddings/vllm-vlm2vec-image-embed
pip install requests
curl -L -o sample.jpg https://vllm-public-assets.s3.us-west-2.amazonaws.com/multimodal_asset/cat_snow.jpg

# 7. Verify kernels load (must NOT print "Illegal instruction")
python3 -c "import vllm._C; print('vllm._C OK on AVX2')"
```

Sanity checks: `torch.__version__` → `2.11.0+cpu`; `current_platform.is_cpu()` → `True`. `/tmp/vllm-build` can be deleted after the build.
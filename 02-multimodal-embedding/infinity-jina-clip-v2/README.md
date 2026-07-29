# Infinity + jina-clip-v2 (CPU)

> Send an image **URL** (or text) to a local [Infinity](https://github.com/michaelfeil/infinity) server and get back a 1024-dim vector — the lightest, fastest local path in this repo. Containerless, CPU-only, `curl` is the only client.

![Engine](https://img.shields.io/badge/engine-Infinity%20(torch%2C%20CPU)-purple)
![Model](https://img.shields.io/badge/model-jinaai%2Fjina--clip--v2-orange)
![Dim](https://img.shields.io/badge/dim-1024-blue)
![Input](https://img.shields.io/badge/input-image%20URL-lightgrey)

`jina-clip-v2` maps images **and** text into the same 1024-dim space, so you can compare an image to a text query directly.

```mermaid
flowchart LR
    IN["image URL / text"] -->|POST /embeddings| SVC["Infinity server<br/>jina-clip-v2"]
    SVC --> VEC["1024-d<br/>embedding vector"]
    VEC --> USE["similarity search<br/>clustering · dedup"]
```

> **Tested on:** RHEL 9.6 (Plow), kernel `5.14.0-570.62.1.el9_6`, Python 3.12.13, CPU-only (no GPU), Infinity `0.0.77` + `jinaai/jina-clip-v2`. RHEL 9.6 needs a one-time SQLite fix — see the [Appendix](#appendix--host-setup-rhel-96-and-troubleshooting).

> **Latency:** the first request after startup is slow (model warmup); warm requests are ~2.5 s each on CPU.

## Quick start

The `.venv` is already built in this folder. To build it from scratch, see the [Appendix](#build-the-venv-from-scratch).

```bash
cd infinity-jina-clip-v2
source .venv/bin/activate

# start the server in the background (logs -> server.log)
nohup infinity_emb v2 --model-id jinaai/jina-clip-v2 --port 7997 --engine torch > server.log 2>&1 &

# wait until ready (first run downloads ~900 MB + runs a CPU warmup — a few minutes)
until [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:7997/health)" = "200" ]; do sleep 2; done; echo ready

# embed an image straight from a URL — no base64, no local download
curl -s http://localhost:7997/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model":"jinaai/jina-clip-v2","input":["https://vllm-public-assets.s3.us-west-2.amazonaws.com/multimodal_asset/cat_snow.jpg"]}' \
  | python3 -m json.tool | head -20

pkill -f infinity_emb   # stop the server when done
```

```json
{
    "object": "list",
    "data": [
        {"object": "embedding", "embedding": [-0.0707126334309578, 0.028112050145864487, -0.017097393050789833, ...]}
    ],
    "model": "jinaai/jina-clip-v2",
    "usage": {...}
}
```

A `data[0].embedding` array of **1024** floats — the same kind of object you know from text embeddings, usable for similarity search, clustering, or ranking. If the server dies on startup, inspect `server.log`.

## How it works

Four layers, from the model up to the network:

| Layer | What it does |
|---|---|
| **jina-clip-v2** (Transformers + `trust_remote_code`) | The trained model: image or text → 1024-dim vector. It ships its own model code on the Hub, so `trust_remote_code` downloads and runs that code (first start pulls a few `.py` files alongside the weights). |
| **PyTorch (CPU)** | The math engine that runs the model's tensor operations on the CPU. |
| **Infinity** (`infinity-emb`, torch engine) | The serving layer: holds the model in memory, **batches** concurrent requests, returns vectors. "torch engine" = plain PyTorch (vs. ONNX) — the most compatible choice for a custom model. |
| **FastAPI + Uvicorn** | The HTTP layer: defines `/embeddings` and `/health`, listens on the port. |

A request flows **down** the stack (HTTP → FastAPI → Infinity → PyTorch model); the vector flows back **up**.

```
image URL or text
       │  POST /embeddings (input[])
       ▼
┌──────────────────────────────────────────┐
│ Infinity (localhost:7997)                 │
│  1 validate → 2 fetch image from URL      │
│  3 preprocess → 4 CLIP encode (CPU)       │
│  5 L2-normalize → 6 OpenAI-style JSON     │
└──────────────────────────────────────────┘
       │
       ▼  data[].embedding → 1024 floats
```

| Step | Detail |
|---|---|
| 2 · fetch | You send a *URL*, not bytes — **the server** downloads the image, so the server (not your machine) needs network access to it. Text inputs skip this step. |
| 4 · encode | The expensive step, accelerated by request **batching** across concurrent calls. |
| 5 · normalize | Vectors are L2-normalized, so **cosine similarity is just a dot product** — convenient for search/ranking. |

## The API shape

Infinity's endpoint matches OpenAI's text-embeddings API: same path (`/embeddings`), same response shape (`data[].embedding`), so any OpenAI client or plain `curl` works. The difference: each `input` entry can be an **image URL** (or text, or a mix).

**Request** — mix images and text in one call:

```json
{
  "model": "jinaai/jina-clip-v2",
  "input": ["https://.../cat_snow.jpg", "a photo of a cat in the snow"]
}
```

**Response** — one embedding per input, in order, under `data[]`.

## What's not here

Deliberately omitted: auth, TLS, client-side batching, error handling/retries, GPU support, and **any vector storage**. To go further:

- Persist the vectors — e.g. a Db2 `VECTOR` column (as the [vLLM](../vllm-vlm2vec-image-embed/README.md) and [Bedrock](../bedrock-titan-image-embed/README.md) recipes do) or a library like FAISS
- Embed a text query and rank images against it (shared space)
- Move to a GPU host for lower latency

---

## Appendix — host setup (RHEL 9.6) and troubleshooting

Everything below is host-specific or only needed for a from-scratch install. The main flow assumes the happy path.

### Tested environment

| | |
|---|---|
| OS | Red Hat Enterprise Linux 9.6 (Plow) |
| Kernel | `5.14.0-570.62.1.el9_6.x86_64` |
| Python | 3.12.13 (system `python3`) |
| Hardware | CPU-only (no GPU) |
| `sqlite-libs` | `3.34.1-10.el9_8` (see prerequisite below) |

### Prerequisite: fix the system SQLite (one-time, needs sudo)

On a fresh RHEL 9.6 image, `import sqlite3` is **broken system-wide** for Python 3.12: the stock `sqlite-libs-3.34.1-9.el9_7` doesn't export `sqlite3_deserialize`, but the `python3.12-libs` (el9_8) `_sqlite3` extension requires that symbol. Infinity's caching layer imports `sqlite3` at startup, so it crashes immediately.

Fix by updating `sqlite-libs` so it matches `python3.12-libs`:

```bash
sudo dnf update -y sqlite-libs        # 3.34.1-9.el9_7 -> 3.34.1-10.el9_8
python3 -c "import sqlite3; print('sqlite3 OK', sqlite3.sqlite_version)"
```

If `dnf update` reports nothing to do, check whether an old SQLite is being injected via `LD_LIBRARY_PATH` (e.g. a Db2 `sqllib/lib64`) ahead of `/lib64`.

### Build the venv from scratch

```bash
mkdir -p ~/db2-ai-cookbook/02-multimodal-embedding/infinity-jina-clip-v2 && cd ~/db2-ai-cookbook/02-multimodal-embedding/infinity-jina-clip-v2
python3 -m venv .venv && source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

> The pinned versions in `requirements.txt` are **required**. Installing a bare `infinity-emb[all]` pulls newer transitive deps that fail to import or start — see Troubleshooting.

### Troubleshooting

`infinity-emb[all]==0.0.77` has bit-rotted against current PyPI. These are the failures seen on a clean install and the pins that resolve them (all captured in `requirements.txt`):

| Symptom at startup | Cause | Fix |
|---|---|---|
| `ImportError: ... _sqlite3 ...: undefined symbol: sqlite3_deserialize` | System `sqlite-libs` (el9_7) older than `python3.12-libs` (el9_8) | `sudo dnf update sqlite-libs` (see prerequisite) |
| `ModuleNotFoundError: No module named 'optimum.bettertransformer'` | `optimum>=2.0` removed BetterTransformer | `optimum==1.27.0` |
| `RuntimeError: BetterTransformer requires transformers<4.49` | `transformers` too new for optimum's bettertransformer shim | `transformers==4.48.3` (+ `tokenizers==0.21.4`) |
| `TypeError: Secondary flag is not valid for non-boolean flag` | `typer 0.12.5` incompatible with `click>=8.2` | `click==8.1.8` |

Harmless `pip` resolver warnings remain for `optimum-onnx` (wants optimum 2.x) and `colpali-engine` (wants newer transformers). Both are for engines/models this service doesn't use (torch engine + jina-clip-v2), so they're never imported.

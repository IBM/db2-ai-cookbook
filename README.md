# Db2 AI Cookbook

> Practical, runnable recipes for building AI features on IBM Db2 — embeddings, vector search, and the surrounding plumbing. Every recipe is minimal by design, so the moving parts stay visible.

![Db2](https://img.shields.io/badge/Db2-12.1%2B-054ada)
![Python](https://img.shields.io/badge/Python-3.12-blue)
![Status](https://img.shields.io/badge/purpose-learning%20%2F%20reference-success)

The cookbook is organised in two levels:

- A **module** is a topic — one AI capability applied to Db2.
- A **recipe** is one concrete, self-contained way to do it — its own engine, virtualenv, README, and `.env`.

Pick a module, pick a recipe inside it, follow the Quick start.

## Modules

| Module | What it covers | Recipes |
|---|---|---|
| [01-multimodal-embedding](01-multimodal-embedding/) | Turn images and text into vectors with three interchangeable embedding services — two self-hosted on CPU, one managed on AWS — and store the results in a Db2 `VECTOR` column for SQL similarity search. Both modalities land in the same vector space, so you can embed a text query and rank images against it. | 3 |
| [02-rag](02-rag/) | Retrieval-augmented generation over your own documents, with Db2 as the vector database. Parse a PDF into structured chunks, embed and store them, retrieve the closest ones for a question with `VECTOR_DISTANCE`, and have a local language model answer from those excerpts — citing the page and section each came from. Runs entirely on your own machine. | 1 |

More modules are on the way. See [Adding a module](#adding-a-module) below.

## Prerequisites

Most recipes that persist vectors need **Db2 ≥ 12.1.2** (where the `VECTOR` type lands) with the `SAMPLE` database, reachable either locally (run as the instance owner) or over TCP/IP (`DB2COMM=TCPIP`, default port `50000`). Recipes that only compute embeddings and hand them back need no Db2 at all.

Anything host-specific — OS package fixes, model downloads, build-from-source paths — lives in the relevant module or recipe README, not here.

## Repository layout

```
db2-ai-cookbook/
├── 01-multimodal-embedding/      # images + text → vectors → Db2 VECTOR
│   ├── infinity-jina-clip-v2/
│   ├── vllm-vlm2vec-image-embed/
│   ├── bedrock-titan-image-embed/
│   └── README.md
├── 02-rag/                       # documents → chunks → Db2 VECTOR → grounded answers
│   ├── haystack-local-models/
│   └── README.md
├── LICENSE
└── README.md                     # you are here
```

Modules are numbered so they sort in a deliberate reading order; the number is part of the folder name, not a strict sequence you must follow.

## Adding a module

1. Create a numbered folder (`03-…`) with a `README.md` that opens with a one-line description, then lists its recipes in a table.
2. Add a row to the [Modules](#modules) table above.
3. Put each recipe in its own subfolder — one per engine/model combo, with its own `.venv` and **pinned** `requirements.txt`. These stacks bit-rot quickly against current PyPI.

### Naming

Don't repeat what the path already says. A module folder names the **capability** (`rag`, not `db2-rag` — the whole cookbook is Db2). A recipe folder names what makes it *different from its siblings*, which is usually the engine or framework plus the model or how models are served:

```
01-multimodal-embedding/infinity-jina-clip-v2      engine + model
02-rag/haystack-local-models                       framework + model hosting
```

### Recipe README shape

One-line opener → Quick start → expected output → concepts. Host-specific setup and troubleshooting go in an appendix at the end, so the happy path stays short.

### Conventions

- Secrets and host-specific config in a gitignored `.env`; commit a `.env.example` alongside it. Never hardcode credentials.
- Give each recipe that runs a server a distinct port, so several can run side by side.
- Keep the code minimal. A recipe is a teaching artifact, not a library.

## License

[Apache 2.0](LICENSE)

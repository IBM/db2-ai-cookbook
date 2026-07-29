# RAG on IBM Db2 12.1.2+ with Haystack, Docling, and local models

[← Db2 AI Cookbook](../../README.md) · [← RAG module](../README.md)

This tutorial builds **retrieval-augmented generation over your own PDF**, using IBM Db2 as the
vector database and nothing but local models:

- **Vector storage** — native Db2 `VECTOR` columns
- **Vector similarity** — `VECTOR_DISTANCE` (cosine), through Haystack's Db2 integration
- **Document parsing** — [Docling](https://github.com/docling-project/docling) turns a PDF into
  structured, chunked text that keeps its headings and page numbers
- **Embeddings and generation** — two models running on your own machine, served by
  [llama.cpp](https://github.com/ggml-org/llama.cpp) behind an OpenAI-compatible API, so
  Haystack's stock OpenAI components work unchanged. No API keys, no cloud, no per-call cost
- **Orchestration** — [Haystack](https://haystack.deepset.ai/) pipelines, four components end to end

> **Db2 version: 12.1.2 is the minimum.** The native `VECTOR` type and `VECTOR_DISTANCE` were
> introduced in **12.1.2** — on anything older this project cannot work, because the table it
> creates has a `VECTOR` column. Any later release is fine; this guide was written and verified on
> **12.1.5.0**, so you will see that version in the install examples. Check yours with `db2level`.

**The use case: ask questions about a research paper.** The shipped document is
`data/M-Lean_Article.pdf` — a 15-page journal article on a framework for building predictive
models in B2B settings. Any PDF, DOCX, or HTML file works; swap it and re-run.

**Ingestion.** Docling parses the PDF into its real structure, `HybridChunker` splits it on
section boundaries into 70 chunks sized to the embedding model's token budget, each chunk is
vectorized by the local embedding server, and the text, metadata, and 384-dimension vector land
in one Db2 table.

**Ask.** Your question is embedded by the same model, Db2 ranks every chunk by cosine distance,
the top 3 are pasted into a prompt, and the local chat model answers from them — citing the page
and section each excerpt came from.

This README takes you from **a bare Red Hat machine to answered questions**, one command at a
time. No prior Db2, Haystack, or embeddings experience assumed. Every command is one you can copy
and run on its own, and each step ends with something you can check before moving on.

Expanded from the IBM Community tutorial *Agentic Workflows with Haystack and IBM Db2* by
[Dhruv Chaturvedi](https://www.linkedin.com/in/dhruvinsights/), which used cloud Db2 and
watsonx.ai — see [Learn more](#learn-more) for that and the other references.

---

## Contents

- [What it does & why](#what-it-does--why)
- [Architecture: two layers](#architecture-two-layers-over-one-db2-table)
  - [Haystack in one minute](#haystack-in-one-minute)
  - [Ingestion layer](#ingestion-layer--ingestpy)
  - [Search layer](#search-layer--searchpy)
- [Full setup on a fresh RHEL box](#full-setup-on-a-fresh-rhel-box) ← the main guide
  - [Step 1 — Install Db2 (12.1.2 or later) + instance](#step-1--install-db2-1212-or-later--instance)
  - [Step 2 — Configure Db2 and create the database](#step-2--configure-db2-and-create-the-database)
  - [Step 3 — The local models](#step-3--the-local-models)
  - [Step 4 — Get the code](#step-4--get-the-code)
  - [Step 5 — Python project](#step-5--python-project)
  - [Step 6 — Configure `.env`](#step-6--configure-env)
  - [Step 7 — Start the servers & verify](#step-7--start-the-servers--verify)
- [Run the pipeline](#run-the-pipeline-ingest--search)
- [Try it: example questions](#try-it-example-questions)
  - [More questions to try](#more-questions-to-try)
- [How the PDF is chunked](#how-the-pdf-is-chunked-and-why-not-documentsplitter)
- [Verify the vectors in Db2](#verify-the-vectors-in-db2)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Recipe layout](#recipe-layout)
- [Learn more](#learn-more)

---

## What it does & why

A language model can only answer from what it was trained on — it has never seen your PDF, and
asked about it directly it will invent a plausible answer. RAG fixes that by *retrieving* the
relevant passages first and making the model answer from those.

That makes retrieval quality the whole game, and retrieval quality starts with **how the document
was cut up**. Most tutorials pull raw text out of a PDF and slice it every N characters, which
cuts sentences in half, merges a table with the paragraph after it, and loses any notion of which
section or page a passage came from. The answers are then vague and impossible to verify.

This project keeps the document's structure all the way through:

- **Docling** recovers the real layout — headings, sections, tables, reading order, page numbers
- **`HybridChunker`** splits on those structural boundaries rather than a character count, and
  packs each chunk to a token budget measured with the *embedding model's own tokenizer*
- **Db2** stores the text, the structural metadata, and the vector in one row, so a similarity
  search returns a passage that knows what section and page it came from
- The answer therefore comes with **citations** — `p.4 5. Proposed framework design` — that you
  can check against the original

Everything runs locally. The embedding model (bge-small-en-v1.5, 37 MB) and the chat model
(Qwen2.5-3B-Instruct, 2 GB) are served by llama.cpp on this machine, so no document text ever
leaves the box and there is no API bill.

## Architecture: two layers over one Db2 table

The system is two Haystack pipelines that never call each other. They meet only in the Db2
table: the **ingestion layer** writes rows, the **search layer** reads them.

```
                  ┌──────────────────────────────────────────────┐
   your PDF  ───▶ │           INGESTION LAYER  (ingest.py)       │
                  └──────────────────────────────────────────────┘
                                      │
                                      ▼
                  Db2  HAYSTACK_DOCUMENTS (ID, CONTENT, META, EMBEDDING VECTOR(384))
                                      ▲
                                      │
                  ┌──────────────────────────────────────────────┐
 your question ──▶│            SEARCH LAYER  (search.py)         │──▶ grounded answer
                  └──────────────────────────────────────────────┘
```

### Haystack in one minute

If you have used PyTorch or another RAG framework, three Haystack ideas are worth knowing before
reading the diagrams below — the rest follows from them.

- **A `Document` is the currency.** A dataclass with `content` (the text), `meta` (your
  metadata dict), `embedding` (the vector), and `score` (set by a retriever). Ingestion creates
  Documents; search gets them back. Nothing else crosses between the two layers.
- **A `Pipeline` is a graph, not a chain.** You add components under a name, then wire *named
  sockets* together: `pipeline.connect("text_embedder.embedding", "retriever.query_embedding")`.
  The socket names are part of each component's contract, which is why connections are explicit
  rather than positional.
- **`run()` is keyed by component name.** You pass inputs only for sockets that no other
  component feeds — `pipeline.run({"text_embedder": {"text": question}, ...})` — and you get
  back only the *last* component's output, unless you ask for more with
  `include_outputs_from={"retriever"}`. That argument is the main debugging tool: it is how
  `search.py` prints the retrieved chunks.

### Ingestion layer — `ingest.py`

Runs once per document. Turns a PDF into rows in Db2.

```
data/M-Lean_Article.pdf
        │
        ▼
  ┌───────────┐      ┌────────────┐      ┌────────┐
  │ converter │ ───▶ │  embedder  │ ───▶ │ writer │ ───▶  Db2 table
  └───────────┘      └────────────┘      └────────┘
   Docling +          llama.cpp :8081      INSERT
   HybridChunker      384 floats/chunk     70 rows
```

| # | Component | Haystack class | What it does |
|---|---|---|---|
| 1 | `converter` | `DoclingConverter` | Parses the PDF, chunks it with `HybridChunker`, attaches `page_number` + `headings` via `SimpleMeta`. Out: 70 `Document`s with text and metadata, no vectors yet |
| 2 | `embedder` | `OpenAIDocumentEmbedder` | Sends each chunk to the embedding server on `:8081`; fills in `.embedding` (384 floats) |
| 3 | `writer` | `DocumentWriter` | Hands the Documents to `IBMDb2DocumentStore`, which `INSERT`s them into `HAYSTACK_DOCUMENTS` |

Wired as `converter → embedder → writer`
([ingest.py](src/haystack_db2_rag/ingest.py)). The store itself is not a
component — it is the resource the writer writes into, built by
[store.py](src/haystack_db2_rag/store.py).

### Search layer — `search.py`

Runs once per question. Turns a question into a grounded answer.

```
  your question
        │
        ▼
  ┌──────────────┐   ┌───────────┐   ┌────────────────┐   ┌───────────┐
  │ text_embedder│──▶│ retriever │──▶│ prompt_builder │──▶│ generator │──▶ answer
  └──────────────┘   └───────────┘   └────────────────┘   └───────────┘
   llama.cpp :8081    Db2 cosine      excerpts + question   llama.cpp :8080
   384 floats         top 3 rows      → one prompt          Qwen2.5-3B
```

| # | Component | Haystack class | What it does |
|---|---|---|---|
| 1 | `text_embedder` | `OpenAITextEmbedder` | Embeds the question with the **same model** used at ingestion — vectors from different models are not comparable |
| 2 | `retriever` | `IBMDb2EmbeddingRetriever` | Runs `VECTOR_DISTANCE(..., COSINE)` in Db2, returns the `top_k=3` nearest Documents (plus their `score`), optionally filtered on metadata first |
| 3 | `prompt_builder` | `ChatPromptBuilder` | Renders the Jinja template: the retrieved excerpts, then the question |
| 4 | `generator` | `OpenAIChatGenerator` | Sends that prompt to the chat server on `:8080` and returns the reply |

Wired as `text_embedder → retriever → prompt_builder → generator`
([search.py](src/haystack_db2_rag/search.py)).

**What links the two layers** is not code but three shared facts: the embedding dimension
(**384**), the distance metric (**cosine**), and the metadata keys (`page_number`, `headings`).
Change one on one side only and retrieval breaks — silently.

Two llama.cpp servers, because one `llama-server` process serves one model.

---

## Full setup on a fresh RHEL box

**What you're building, in order:** Db2 (the database + vector engine) → an instance and the
`SAMPLE` database → the two local models → the project code → the Python project → your `.env`
→ the running servers. Then you ingest and ask.

**Time & footprint:** ~30–45 min, mostly downloads. CPU-only is fine — **no GPU needed**.
Disk, measured on this box:

| Item | Size |
| --- | --- |
| `~/llama.cpp` (source + build) | 263 MB |
| `~/models` (the two GGUFs) | 2.0 GB |
| `.venv` (Docling pulls in torch + transformers) | 5.7 GB |
| Docling's layout models, cached on first run | 507 MB |
| **Total** | **~8.5 GB** |

**You will need:** root/sudo for Step 1, **Db2 server install media, 12.1.2 or later** (an IBM
entitlement — everything else downloads freely), and internet access. `git`, `gcc-c++`, `make`,
`curl`, and Python 3.12 ship with RHEL 10; `cmake` does not and is installed below.

The whole stack runs as **one user, `db2inst1`** (the Db2 instance owner). Step 1 is system-level
and runs as **root**; from Step 2 on you work as `db2inst1` (`su - db2inst1`). Each step is
marked **(root)** or **(db2inst1)** so you always know which identity to use.

**Verified on:** RHEL 10.0, Db2 12.1.5.0, Python 3.12.13, 16 cores / 30 GB RAM, no GPU.

> **Already have Db2 running?** Skip Step 1 entirely and use Step 2 as a checklist instead of an
> install. You need three things: `db2level` reporting **12.1.2 or later** (the native `VECTOR`
> type does not exist before it), `db2set -all | grep DB2COMM` showing `TCPIP` (the Python client
> connects over TCP), and a database to use — any database; put its name in `DB2_DATABASE` at
> Step 6. Then continue from Step 3.

---

### Step 1 — Install Db2 (12.1.2 or later) + instance

> **The one step not executed on the machine this guide was written on** — Db2 was already
> installed here. Everything from Step 2 onward was run end to end. These commands follow the
> standard Db2 install; if your environment differs, IBM's installation docs are authoritative.

**(root)** You provide the Db2 server install media — **any release from 12.1.2 onward**. The
commands below use the 12.1.5 tarball `v12.1.5_linuxx64_server_dec.tar.gz`; substitute your own
filename and version if it differs.

**1.1 — Install the one Db2 prerequisite.** On RHEL 10 the missing library is `libxcrypt-compat`
(it provides the legacy `libcrypt.so.1`; without it `db2_install` fails with `DBT3507E`):

```bash
sudo dnf install -y libxcrypt-compat
```

**1.2 — Install the Db2 binaries and verify:**

```bash
tar -xvf v12.1.5_linuxx64_server_dec.tar.gz
cd server_dec
./db2_install
db2ls
```

`db2ls` lists the installed copy (e.g. under `/opt/ibm/db2/V12.1`) — confirmation that
`db2_install` succeeded.

> **Reading `db2_install`'s prerequisite check — `E` vs `W`:** a `DBT3507E` (**error**, e.g. the
> missing `libxcrypt-compat`) aborts the install and must be fixed. `DBT3514W` (**warnings**) for
> the 32-bit `.i686` libraries are only required for 32-bit non-SQL routines — this stack uses
> none, so ignore them.

**1.3 — Create the instance owner and the instance.** `db2inst1` is also the fenced user, and the
single account the rest of this guide runs as:

```bash
useradd db2inst1
passwd db2inst1
cd /opt/ibm/db2/V12.1/instance
./db2icrt -u db2inst1 -nosharedgroup db2inst1
```

Remember the password you set — Db2 authenticates against the **operating system**, so this is
the password that goes in `.env` at Step 6.

---

### Step 2 — Configure Db2 and create the database

**(db2inst1)** Switch to the instance owner. Everything from here runs as `db2inst1`:

```bash
su - db2inst1
```

**2.1 — Turn on the TCP listener and start the instance.** The Python client connects over TCP,
so `DB2COMM` must include TCPIP:

```bash
db2set DB2COMM=TCPIP
db2start
db2 get dbm cfg | grep SVCENAME
```

**You should see:** `DB2START processing was successful`, and an `SVCENAME` value — the port (or
service name) the instance listens on. Note it; it goes in `.env` as `DB2_PORT`. On this box it
is `50000`.

**2.2 — Create the `SAMPLE` database** (any database works — `SAMPLE` is just the default in
`.env.example`):

```bash
db2sampl
```

**2.3 — Confirm the database answers:**

```bash
db2 connect to SAMPLE
db2 "SELECT COUNT(*) FROM SYSCAT.TABLES"
db2 connect reset
```

A row count means Db2 is up and reachable. The project's table is created for you at ingest time
— nothing to do here.

> Confirm the version now, before going further: `db2level` must report **12.1.2 or later**.
> Earlier releases have no `VECTOR` type, so `ingest` fails at `CREATE TABLE`. 12.1.5.0 is what
> this guide was verified on; anything newer is fine too.

---

### Step 3 — The local models

**(db2inst1)** Db2 stores the vectors, but something has to *produce* them — and answer questions.
Both jobs run locally through llama.cpp's OpenAI-compatible server: no API keys, no network
egress, no per-call cost.

**3.1 — Build `llama-server`** (CPU; pinned to a known-good tag):

```bash
sudo dnf install -y cmake            # or, without sudo: pip install --user cmake
git clone --depth 1 --branch b9913 https://github.com/ggml-org/llama.cpp.git ~/llama.cpp
cmake -S ~/llama.cpp -B ~/llama.cpp/build -DCMAKE_BUILD_TYPE=Release \
      -DLLAMA_CURL=OFF -DGGML_NATIVE=ON -DLLAMA_BUILD_UI=OFF -DLLAMA_USE_PREBUILT_UI=OFF
cmake --build ~/llama.cpp/build --target llama-server -j"$(nproc)"
```

A few minutes on 16 cores. **You should see:** `Built target llama-server`, and the binary at
`~/llama.cpp/build/bin/llama-server`.

> **`-DLLAMA_BUILD_UI=OFF -DLLAMA_USE_PREBUILT_UI=OFF` are not optional.** Without them the build
> downloads a prebuilt web-UI bundle from Hugging Face that does not match tag b9913, and
> `llama-ui-embed` aborts the build with `missing required asset(s): loading.html`. We only need
> the `/v1` API, not the browser UI. If you hit that error after a partial build, delete
> `~/llama.cpp/build/tools/ui` before rebuilding — the stale asset directory is re-validated.

**3.2 — Download the embedding model** (bge-small-en-v1.5, ~37 MB):

```bash
mkdir -p ~/models/bge-small-en-v1.5
curl -fSL -o ~/models/bge-small-en-v1.5/bge-small-en-v1.5-q8_0.gguf \
  "https://huggingface.co/CompendiumLabs/bge-small-en-v1.5-gguf/resolve/main/bge-small-en-v1.5-q8_0.gguf"
```

**3.3 — Download the generation model** (Qwen2.5-3B-Instruct, ~2 GB):

```bash
mkdir -p ~/models/qwen2.5-3b-instruct
curl -fSL -o ~/models/qwen2.5-3b-instruct/Qwen2.5-3B-Instruct-Q4_K_M.gguf \
  "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf"
```

**3.4 — Sanity-test the embedding model** (start on a throwaway port `:8099`, embed once, stop).
`--pooling cls` is required — the wrong pooling silently degrades quality:

```bash
~/llama.cpp/build/bin/llama-server -m ~/models/bge-small-en-v1.5/bge-small-en-v1.5-q8_0.gguf \
  --embedding --pooling cls --ctx-size 512 --host 127.0.0.1 --port 8099 >/tmp/sanity.log 2>&1 &
until curl -sf -o /dev/null http://127.0.0.1:8099/health; do sleep 1; done
curl -s http://127.0.0.1:8099/v1/embeddings -H 'Content-Type: application/json' \
  -d '{"input":"hello"}' \
  | python3 -c "import sys,json;print('dim', len(json.load(sys.stdin)['data'][0]['embedding']))"
fuser -k 8099/tcp
```

**You should see:** `dim 384`.

**3.5 — Sanity-test the generation model:**

```bash
~/llama.cpp/build/bin/llama-server -m ~/models/qwen2.5-3b-instruct/Qwen2.5-3B-Instruct-Q4_K_M.gguf \
  --ctx-size 2048 --host 127.0.0.1 --port 8099 >/tmp/sanity.log 2>&1 &
until curl -sf -o /dev/null http://127.0.0.1:8099/health; do sleep 1; done
curl -s http://127.0.0.1:8099/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Reply with one word: hello"}]}' \
  | python3 -c "import sys,json;print('reply:', json.load(sys.stdin)['choices'][0]['message']['content'])"
fuser -k 8099/tcp
```

**You should see:** `reply: Hello`. Failures land in `/tmp/sanity.log`.

> Use `curl -sf`, not `curl -s`, in the readiness loop. `/health` answers **503** while the model
> loads, and without `-f` curl treats that as success — the loop exits after one second and the
> request fails with a confusing `KeyError: 'choices'`.

These were throwaway servers. Step 7 starts the real ones on their proper ports.

---

### Step 4 — Get the code

**(db2inst1)** Clone the cookbook into `db2inst1`'s home and enter this recipe:

```bash
cd ~
git clone https://github.com/IBM/db2-ai-cookbook.git
cd db2-ai-cookbook/03-rag/haystack-local-models
```

Every path from here on is relative to that folder. The sample PDF (`data/M-Lean_Article.pdf`)
ships with the recipe, so there is nothing else to download.

---

### Step 5 — Python project

**(db2inst1)** A virtualenv with Haystack, the Db2 integration, and Docling:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

This is the big download — Docling depends on torch and transformers, so expect ~5.7 GB and
several minutes.

---

### Step 6 — Configure `.env`

**(db2inst1)**

```bash
cp .env.example .env
$EDITOR .env
```

Set **`DB2_PASSWORD`** to the *operating-system* password of `db2inst1` (the one from Step 1.3) —
Db2 runs with `AUTHENTICATION=SERVER`, so it authenticates against the OS, not a database user.
Set `DB2_PORT` if your `SVCENAME` from Step 2.1 is not `50000`. The remaining defaults work as-is.

`.env` is git-ignored — real credentials are never committed. See
[`.env.example`](.env.example) for every key.

---

### Step 7 — Start the servers & verify

**(db2inst1)** One script starts both llama.cpp servers — embeddings on `:8081`, chat on `:8080`
— and waits until each is genuinely ready:

```bash
scripts/llama-servers.sh start
scripts/llama-servers.sh status
```

**You should see:**

```
  embeddings  :8081  up    bge-small-en-v1.5
  chat  :8080  up    qwen2.5-3b-instruct
```

Logs go to `logs/`. Stop them with `scripts/llama-servers.sh stop` when you're done for the day.

**Now check the whole stack in one go**, before spending minutes on an ingest that would fail at
the last step. This connects to Db2 with the credentials from your `.env` and pings both model
servers:

```bash
PYTHONPATH=src .venv/bin/python -c "
from haystack_db2_rag.store import document_store
print('Db2 OK —', document_store().count_documents(), 'chunks in the table')"

curl -sf http://127.0.0.1:8081/v1/models >/dev/null && echo "embeddings OK" || echo "embeddings DOWN"
curl -sf http://127.0.0.1:8080/v1/models >/dev/null && echo "chat OK" || echo "chat DOWN"
```

**You should see:**

```
Db2 OK — 0 chunks in the table
embeddings OK
chat OK
```

Zero chunks is correct before your first ingest — the check creates the empty table, which also
proves the credentials can write. If the Db2 line fails instead, the **last line** of the
traceback names the cause (`SQL30082N`, `SQL1032N`, …); look it up in
[Troubleshooting](#troubleshooting).

That's the one-time setup — **everything below is the day-to-day workflow.**

---

## Run the pipeline (ingest → search)

Two commands. Parse and store the PDF, then ask it questions. Run from this recipe's folder with
the servers up and Db2 started.

```bash
export PYTHONPATH=src

.venv/bin/python -m haystack_db2_rag.ingest data/M-Lean_Article.pdf
.venv/bin/python -m haystack_db2_rag.search "What is M-Lean?"
```

`ingest` drops and recreates the table each run, so it is always safe to re-run.
**You should see:** `Stored 70 chunks in HAYSTACK_DOCUMENTS.`

**How long these take**, measured on this box (16 CPU cores, no GPU) — everything runs on the
CPU, so none of it is instant:

| | Time |
| --- | --- |
| First `ingest` (downloads Docling's models) | several minutes |
| Later `ingest` runs, same 15-page PDF | **~50 s** |
| Each `search` | **~10 s** |

`ingest` prints a `Calculating embeddings` progress bar partway through; `search` prints nothing
until the answer is complete, because the chat model generates the whole reply before returning.
Neither is hung.

> The **first** `ingest` run downloads Docling's layout and table-structure models (~500 MB) and
> the bge tokenizer. After that it works offline.

Pass any other document as the argument — PDF, DOCX, or HTML. Drop it in `data/`; only the sample
PDF is tracked by git, so your own files stay out of the repo.

Add a page number as a second argument to filter on metadata *before* the vector search:

```bash
.venv/bin/python -m haystack_db2_rag.search "What does the proposed framework look like?" 4
```

## Try it: example questions

For the shipped paper. The principle is general: **the answer is only as good as the retrieved
chunks, and every answer names where it came from.**

**A question the document answers well** — the concept is stated in the abstract and the title:

```
$ .venv/bin/python -m haystack_db2_rag.search "What is M-Lean?"

Q: What is M-Lean?

A: M-Lean is an end-to-end development framework for predictive models in B2B scenarios.
   It addresses the challenges of uncertainty and inefficiency in machine learning models,
   particularly in the context of deploying models in business-to-business (B2B) settings.

Retrieved:
  [0.308] p.1 M-Lean: An end-to-end development framework for predictive models in B2B...
  [0.418] p.4 5. Proposed framework design: Table 1 Proposed framework vs. ...
  [0.430] p.4 5. Proposed framework design: build-measure-learn loop is th...
```

Lower scores are closer — they are cosine **distances**, not similarities.

**A metadata-filtered question** — the page filter runs in Db2 before the similarity search, so
every hit comes from page 4:

```
$ .venv/bin/python -m haystack_db2_rag.search "What does the proposed framework look like?" 4

A: The proposed framework looks like a structured process divided into three phases, each
   with specific objectives, research questions, and methods for data collection...

Retrieved:
  [0.298] p.4 5. Proposed framework design: Table 1 Proposed framework vs. ...
  [0.302] p.4 5.1. Getting more from business data: ideas suggestions and data discovery...
  [0.315] p.4 5.1. Getting more from business data: ideas suggestions and data discovery...
```

**A question the document cannot answer** — retrieval always returns *something* (the three
least-bad chunks, here at distances around 0.6), but the prompt tells the model to answer only
from them, so it declines instead of falling back on what it knows:

```
$ .venv/bin/python -m haystack_db2_rag.search "What is the capital of France?"

A: The document does not cover the answer to the question "What is the capital of France?"
```

That last one is the behaviour to re-check after any change to the prompt or the retriever — a
RAG system that answers this one has stopped being grounded.

### More questions to try

All verified against the shipped paper — good starting points for exercising the search layer:

```bash
.venv/bin/python -m haystack_db2_rag.search "What is a minimum viable model?"
.venv/bin/python -m haystack_db2_rag.search "What data collection methods does M-Lean use?"
.venv/bin/python -m haystack_db2_rag.search "Why do predictive models degrade after deployment?"
.venv/bin/python -m haystack_db2_rag.search "What is the build-measure-learn loop?"
.venv/bin/python -m haystack_db2_rag.search "What are the limitations of this study?"
.venv/bin/python -m haystack_db2_rag.search "What are the phases of the M-Lean framework?"
```

Each is chosen to show a different retrieval behaviour:

| Question | What it demonstrates |
| --- | --- |
| *What is a minimum viable model?* | A **definition** stated in one place — the answer is one sentence, cited to a single chunk on p.6. The cleanest illustration of RAG working |
| *What data collection methods does M-Lean use?* | Information **spread across three sections**; the answer pulls all three phases together from separate chunks |
| *Why do predictive models degrade after deployment?* | A **"why" question** whose answer is an argument rather than a stated fact — the model has to synthesize from the retrieved passages |
| *What is the build-measure-learn loop?* | A concept the paper **borrows from Lean Startup**; a good check that answers stay tied to how *this* paper uses the term |
| *What are the limitations of this study?* | A **standard section of any paper** — try this one when you swap in your own PDF |
| *What are the phases of the M-Lean framework?* | Instructive **imperfection**: retrieval favours the build-measure-learn chunk, so the answer describes that loop's stages rather than the paper's exploratory/improving phases. Compare `--top-k` values or add the page filter (`… 4`) and watch the answer change |

That last row is worth running deliberately. It shows the thing that matters most in RAG: the
answer is only ever as good as the chunks the retriever chose, and a confident-sounding answer
can still be aimed at the wrong part of the document. It depends on **both** halves of the
generator setup: the "do not use any other knowledge" sentence in the prompt, *and*
`temperature: 0`. With sampling left on, this same question answered "The capital of France is
Paris" in 5 of 6 runs.

> **On reproducibility:** at `temperature: 0` the same question gives byte-identical answers —
> except for the **first** request after a llama.cpp server restart, which differs from every
> later one because the prompt cache is cold and the numerics differ slightly. If you are
> comparing outputs, discard the first run after `llama-servers.sh start`.

## How the PDF is chunked (and why not DocumentSplitter)

`DoclingConverter` runs with `ExportType.DOC_CHUNKS` and Docling's `HybridChunker`
([src/haystack_db2_rag/ingest.py](src/haystack_db2_rag/ingest.py)):

```python
chunker = HybridChunker(
    tokenizer=HuggingFaceTokenizer.from_pretrained("BAAI/bge-small-en-v1.5", max_tokens=448)
)
```

This is the right pairing when Docling does the parsing, rather than Haystack's generic
`DocumentSplitter`:

1. `HybridChunker` splits on the document's **own structure** — sections, headings, tables —
   which is precisely what Docling recovers. `DocumentSplitter` splits by word or sentence count
   and discards that structure, so you pay for the parse and then throw the result away.
2. It is **tokenizer-aware**: hand it the embedding model's tokenizer and no chunk overflows the
   model's context window. Overflow is silent — the server truncates and you lose the tail of the
   chunk with no error and no warning.
3. Section headings and page numbers survive into `doc.meta`, which is what makes the citations
   above possible.

**Why 448 and not bge's full 512.** Docling prepends the section headings to each chunk *after*
the token budget is applied. At `max_tokens=512` one chunk in this PDF came out at 519 tokens and
was silently truncated. At 448 the same document yields 70 chunks with a median of 331 tokens and
a maximum of 456 — all comfortably inside the window.

**Why the metadata is trimmed.** Db2 stores document metadata as BSON, which forbids field names
beginning with `$`. Docling's full `dl_meta` contains `$ref` keys, so `ingest.py` passes a small
`SimpleMeta` extractor keeping just the page number and headings. Without it **every** insert
fails with `SQL0443N … JSON2BSON`.

## Verify the vectors in Db2

The vectors are ordinary Db2 data — you can inspect them without Python:

```bash
db2 connect to SAMPLE
db2 "SELECT COUNT(*) FROM HAYSTACK_DOCUMENTS"
db2 "SELECT COLNAME, TYPENAME, LENGTH FROM SYSCAT.COLUMNS WHERE TABNAME='HAYSTACK_DOCUMENTS'"
```

**You should see:** 70 rows, and the `EMBEDDING` column reported as type `VECTOR` with length
`384` — Db2 is storing the vectors natively, not as a blob.

You can even run the similarity search in pure SQL, no application involved:

```bash
db2 "SELECT SUBSTR(CONTENT,1,60) FROM HAYSTACK_DOCUMENTS \
     ORDER BY VECTOR_DISTANCE(EMBEDDING, \
       (SELECT EMBEDDING FROM HAYSTACK_DOCUMENTS FETCH FIRST 1 ROWS ONLY), COSINE) \
     FETCH FIRST 3 ROWS ONLY"
```

## Configuration

Everything is in [`.env`](.env.example) — the Db2 connection and the two llama.cpp endpoints:

| Key | Meaning |
| --- | --- |
| `DB2_DATABASE` · `DB2_HOSTNAME` · `DB2_PORT` | connection target (`SAMPLE`, `localhost`, `50000`) |
| `DB2_USERNAME` · `DB2_PASSWORD` | the instance owner and its **OS** password |
| `DB2_TABLE_NAME` | table to create and query (`HAYSTACK_DOCUMENTS`) |
| `EMBED_BASE_URL` · `EMBED_MODEL` | the embedding server (`http://127.0.0.1:8081/v1`) |
| `CHAT_BASE_URL` · `CHAT_MODEL` | the chat server (`http://127.0.0.1:8080/v1`) |

Values that must not drift from the model are constants in
[src/haystack_db2_rag/settings.py](src/haystack_db2_rag/settings.py), not `.env` keys: the
384-dimension embedding size, the 448-token chunk budget, and the tokenizer name. Changing them
in `.env` would have no effect, so they are not offered there.

## Troubleshooting

Symptom → cause → fix. Every row here is a failure hit while building this.

| Symptom | Cause | Fix |
|---|---|---|
| Build aborts: `UI: llama-ui-embed failed` / `missing required asset(s): loading.html` | The build fetches a prebuilt web UI that doesn't match tag b9913 | Add `-DLLAMA_BUILD_UI=OFF -DLLAMA_USE_PREBUILT_UI=OFF`; if a partial build already ran, `rm -rf ~/llama.cpp/build/tools/ui` first |
| Sanity test fails with `KeyError: 'choices'` a second after starting the server | `/health` returns **503** while the model loads, and `curl -s` treats that as success | Use `curl -sf` in the readiness loop |
| Embedding sanity prints a dim other than 384 | Wrong GGUF, or `--pooling cls` missing | Re-download the model file and pass the flag |
| `CREATE TABLE` fails on the `VECTOR` column during the first `ingest` | Db2 is older than **12.1.2**, which is where the native `VECTOR` type was introduced | `db2level` to confirm, then upgrade — there is no workaround; the type does not exist |
| `SQL1032N No start database manager command was issued` (from the `db2` CLI) or `SQL30081N … communication error` (from `ingest`/`search`) | Db2 isn't running. The CLI and the Python client report it differently — the Python client connects over TCP, so it fails at the socket | `db2start` |
| `SQL30082N … reason "24" ("USERNAME AND/OR PASSWORD INVALID")` | `AUTHENTICATION=SERVER` — Db2 checks the **OS** password | Put `db2inst1`'s OS password in `DB2_PASSWORD` |
| Db2 connect fails though the instance is up | `DB2COMM` not set to TCPIP, or `DB2_PORT` ≠ the instance's `SVCENAME` | `db2set DB2COMM=TCPIP; db2stop; db2start`, and check `db2 get dbm cfg \| grep SVCENAME` |
| `SQL1024N A database connection does not exist` | Running SQL without connecting | `db2 connect to SAMPLE` |
| **Every** insert fails `SQL0443N … JSON2BSON … JSON parsing error` | Docling's `dl_meta` contains `$ref`; BSON forbids field names starting with `$` | Keep the `SimpleMeta` extractor in `ingest.py` — it strips `dl_meta` |
| Every search prints `Nothing was retrieved` although `SELECT COUNT(*)` shows rows | A row whose embedding is all zeros. `VECTOR_DISTANCE(…, COSINE)` raises **`SQL0801N` division by zero**, which aborts the whole ranking query — the retriever swallows it and returns an empty list, so nothing says *why* | Re-run `ingest` to rebuild the table. To see the real error, run the ranking query in `db2` directly: the CLI prints `SQL0801N` where Python prints nothing |
| `ModuleNotFoundError: No module named 'haystack_db2_rag'` | The package lives in `src/` | `export PYTHONPATH=src` |
| `Connection refused` on `:8081` or `:8080` | A llama.cpp server isn't running | `scripts/llama-servers.sh start`, then `status` |
| transformers warns `Token indices sequence length is longer … (519 > 512)` | A chunk exceeds the embedding window and is being silently truncated | Lower `EMBED_MAX_TOKENS` in `settings.py` (448 works for this PDF) |
| First `ingest` run seems to hang | It's downloading Docling's ~500 MB layout models | Wait it out; subsequent runs are offline and fast |

## Recipe layout

```
src/haystack_db2_rag/   settings.py (all config, from .env) · store.py (the Db2 connection)
                        ingest.py  converter → embedder → writer
                        search.py  text_embedder → retriever → prompt_builder → generator
scripts/                llama-servers.sh  (start · stop · status for both llama.cpp servers)
data/                   M-Lean_Article.pdf  (the sample document)
docs/                   test-plan.md  (what to test, and why generation can't be asserted on)
```

The code is deliberately minimal — no error handling, no retries, no edge cases — so each file
reads top to bottom in one sitting.

## Learn more

**This project**

- [Agentic Workflows with Haystack and IBM Db2](https://community.ibm.com/community/user/blogs/dhruv-chaturvedi/2026/07/10/agentic-workflows-with-haystack-and-ibm-db2)
  by [Dhruv Chaturvedi](https://www.linkedin.com/in/dhruvinsights/) — the IBM Community tutorial
  this recipe expands on.
- [Build grounded AI applications with the new IBM Db2 integration for Haystack](https://www.ibm.com/new/announcements/build-grounded-ai-applications-with-the-new-ibm-db2-integration-for-haystack)
  — the IBM announcement of the integration.

**Haystack**

- [Haystack documentation](https://docs.haystack.deepset.ai/docs/intro) — pipelines, components,
  and the concepts behind them.
- [Haystack on GitHub](https://github.com/deepset-ai/haystack) — the framework itself.

**The Db2 integration**

- [IBM Db2 Document Store integration](https://haystack.deepset.ai/integrations/ibm-db-document-store)
  — the integration page, with the current component reference.
- [`ibm-db-haystack` on PyPI](https://pypi.org/project/ibm-db-haystack/) — the package this
  project installs (0.2.0 here).

**The other pieces**

- [Docling](https://github.com/docling-project/docling) — the document parser, and
  [`docling-haystack`](https://pypi.org/project/docling-haystack/), its Haystack integration.
- [llama.cpp](https://github.com/ggml-org/llama.cpp) — the local model server.

> Following the IBM tutorial alongside this recipe? Its code uses `Db2DocumentStore` and
> `Db2EmbeddingRetriever`; `ibm-db-haystack` 0.2.0 renamed those to `IBMDb2DocumentStore` and
> `IBMDb2EmbeddingRetriever`, which is what [store.py](src/haystack_db2_rag/store.py) imports.

## License

[Apache-2.0](../../LICENSE), covering the code in this cookbook.

`data/M-Lean_Article.pdf` is a published journal article
(*Information and Software Technology* 113, 2019, © Elsevier), included as sample input. It is
not covered by this repository's license — replace it with your own document for any other use.

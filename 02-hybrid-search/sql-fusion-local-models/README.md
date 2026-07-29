# Hybrid Search on IBM Db2 12.1.5

[← Db2 AI Cookbook](../../README.md) · [← Hybrid search module](../README.md)

This tutorial implements **hybrid search** on **IBM Db2 12.1.5**, using the AI stack
built into Db2:

- **Vector storage** — native `VECTOR` columns
- **Vector similarity** — `VECTOR_DISTANCE` (cosine)
- **Similarity search** over the vector column
- **Vector index** — approximate-nearest-neighbor index for fast retrieval
- **Text search** — Db2 Text Search (BM25), OpenSearch-backed
- **Language-model integration** — in-database `TO_EMBEDDING`, calling a local
  OpenAI-compatible model (no API keys, no cloud)

**The use case: audiobook search.** The corpus is a catalogue of 92 audiobooks. For
each book we keep its title, some metadata (author, narrator), and a summary — all
in a single Db2 table.

**Ingestion.** Each book's description is (a) fed into a **lexical (keyword) index**
through Db2 Text Search, and (b) **vectorized** by a lightweight text-embedding model
running locally, called from SQL via Db2's `TO_EMBEDDING`. The rows and both indexes
are stored in Db2.

**Search.** A query runs through both legs — the **lexical index** for keyword search
and **vector search** for dense retrieval — and a single Db2 SQL query combines both
result sets into one unified ranking (see [How the fusion works](#how-the-fusion-works-and-why-not-rrf)).
An **optional reranker** can refine this: the application layer sends the top ~20
hybrid results to a locally running cross-encoder and presents the reranker's
top matches.

This README takes you from **a bare Red Hat machine to a running app**, one command
at a time. No prior Db2, OpenSearch, or embeddings experience assumed. Every install
command is on its own line so you can copy and run them one at a time and watch each
result before moving on.

---

## Contents

- [What it does & why](#what-it-does--why)
- [Architecture](#architecture-one-row-two-representations)
- [Full setup on a fresh RHEL box](#full-setup-on-a-fresh-rhel-box) ← the main guide
  - [Step 1 — Db2 12.1.5 + instance](#step-1--db2-1215--instance)
  - [Step 2 — OpenSearch](#step-2--opensearch-the-text-search-backend)
  - [Step 3 — Enable Db2 Text Search + register OpenSearch](#step-3--enable-db2-text-search--register-opensearch)
  - [Step 4 — llama.cpp + the three models](#step-4--llamacpp--the-three-models)
  - [Step 5 — Get the code](#step-5--get-the-code)
  - [Step 6 — Python project](#step-6--python-project)
  - [Step 7 — Configure `.env`](#step-7--configure-env)
  - [Step 8 — Start services & verify](#step-8--start-services--verify)
- [Run the pipeline](#run-the-pipeline-ingest--search)
- [Run the app](#run-the-app)
- [Try it: example queries](#try-it-example-queries)
- [Measure search quality](#measure-search-quality)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Recipe layout](#recipe-layout)

---

## What it does & why

Most "AI search" demos do only half the job. Real retrieval works best when you
combine **two** ways of finding text, because each has a blind spot:

- **Lexical** (keyword / BM25) — great at exact terms: names, titles, error codes,
  identifiers. Blind to paraphrases.
- **Semantic** (vector embeddings) — great at meaning: synonyms and descriptions.
  Blind to exact tokens it can't place (a bare narrator name embeds to noise).

This project stores each row of a CSV corpus in Db2 with **both** representations,
searches with both, and **fuses** the two rankings so each leg covers the other's
blind spot. It uses Db2 12.1.5 features end to end:

- **Db2 Text Search** (OpenSearch-backed) for the lexical/BM25 index, and
- **native `VECTOR` columns + in-database `TO_EMBEDDING`** (via a registered
  OpenAI-compatible model — a local llama.cpp `bge-small-en-v1.5` server) for the
  semantic index.

The shipped corpus is a personal audiobook library (92 books; `chunk_text` =
title + authors + narrators + full description). Both retrieval legs index this
text — BM25 over all of it, the vector over the first ~1500 chars (the embedding
model's 512-token limit). Bring your own by matching that schema.

## Architecture: one row, two representations

```
CSV corpus (chunk_id, chunk_text)
        │  1_ingest.sql
        ▼
Db2 table  (chunk_id, chunk_text, embedding)
       ├── chunk_text → Db2 Text Search index (OpenSearch)      → BM25 / CONTAINS · SCORE
       └── embedding  → native VECTOR column (local bge-small)  → cosine · VECTOR_DISTANCE
                            │
                            ▼
       fuse both legs (gated, score-normalized weighted sum) — all in one Db2 SQL query
```

The fusion is **not** plain Reciprocal Rank Fusion — see
[How the fusion works](#how-the-fusion-works-and-why-not-rrf).

---

## Full setup on a fresh RHEL box

**What you're building, in order:** Db2 (the database + vector engine) → OpenSearch
(the keyword-index backend) → Db2 Text Search enabled → a local llama.cpp server +
models → the project code → the Python project → your data ingested → the app.

**Time & footprint:** ~30–45 min, mostly downloads. CPU-only is fine (no GPU).
Budget ~2 GB RAM for OpenSearch and a few GB for Db2. Developed on **RHEL 10**.

**You will need:** root/sudo (for the installs), the **Db2 12.1.5 server install
media** (requires an IBM entitlement — everything else downloads freely), and
internet access. `git`, `cmake`, `gcc-c++`, `wget`, and Python 3.12 are used along
the way and already ship on RHEL 10 — install any that are missing on your box.

The whole stack runs as **one user, `db2inst1`** (the Db2 instance owner). Steps 1–2
are system-level, run as **root**; from Step 3 on you work as `db2inst1`
(`su - db2inst1`). Each step is marked **(root)** or **(db2inst1)** so you always
know which identity to use.

---

### Step 1 — Db2 12.1.5 + instance

**(root)** You provide the Db2 12.1.5 server install media (an IBM entitlement — the
example assumes the tarball `v12.1.5_linuxx64_server_dec.tar.gz`).

**1.1 — Install the one Db2 prerequisite.** On RHEL 10 the only missing library is
`libxcrypt-compat` (it provides the legacy `libcrypt.so.1`; without it `db2_install`
fails with `DBT3507E`):

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

`db2ls` lists the installed Db2 copy (e.g. under `/opt/ibm/db2/V12.1`) — a quick
confirmation that `db2_install` succeeded.

> **Reading `db2_install`'s prerequisite check — `E` vs `W`:** `db2_install` runs its
> own prerequisite check; watch its output. A `DBT3507E` (**error**, e.g. missing
> `libxcrypt-compat`) aborts the install and must be fixed. `DBT3514W` (**warnings**)
> for the 32-bit `.i686` libraries are *"only required for 32-bit non-SQL routines"* —
> this stack uses none, so **ignore them**.

**1.3 — Create the instance owner and the instance** (`db2inst1` is also the fenced
user, and the single account the whole stack runs as):

```bash
useradd db2inst1
passwd db2inst1
cd /opt/ibm/db2/V12.1/instance
./db2icrt -u db2inst1 -nosharedgroup db2inst1
```

The Db2 software is installed and the `db2inst1` instance exists. You configure and
start it in Step 3 (after OpenSearch is in place).

---

### Step 2 — OpenSearch (the Text Search backend)

**(root)** OpenSearch is the backend for Db2's lexical/BM25 leg; you register it with
Db2 in Step 3. Version **3.7.0** is the one validated with Db2 12.1.5 Text Search.
Security is **off** and it binds to `127.0.0.1` only (local use) — keep it that way.
It runs as `db2inst1` (created in Step 1); OpenSearch can't run as root.

**2.1 — Raise the memory-map limit** (OpenSearch won't start without it):

```bash
echo 'vm.max_map_count=262144' | sudo tee /etc/sysctl.d/99-opensearch.conf
sudo sysctl -p /etc/sysctl.d/99-opensearch.conf
```

**2.2 — Download and unpack into `/opt/opensearch`, owned by db2inst1:**

```bash
cd /opt
sudo wget https://artifacts.opensearch.org/releases/bundle/opensearch/3.7.0/opensearch-3.7.0-linux-x64.tar.gz
sudo tar -xzf opensearch-3.7.0-linux-x64.tar.gz
sudo mv opensearch-3.7.0 opensearch
sudo rm opensearch-3.7.0-linux-x64.tar.gz
sudo chown -R db2inst1:db2inst1 /opt/opensearch
```

**2.3 — Write the config** (single-node, security off). This one block writes the
whole file as db2inst1:

```bash
sudo -u db2inst1 tee /opt/opensearch/config/opensearch.yml >/dev/null <<'YML'
cluster.name: db2-text-search-cluster
node.name: node-1
network.host: 127.0.0.1
http.port: 9200
discovery.type: single-node
plugins.security.disabled: true
YML
```

**2.4 — Start it as db2inst1 and verify** (first start takes ~1 min):

```bash
sudo -u db2inst1 /opt/opensearch/bin/opensearch -d -p /opt/opensearch/opensearch.pid
until curl -s -o /dev/null http://localhost:9200; do sleep 2; done
curl http://localhost:9200
```

You should see JSON with `"cluster_name" : "db2-text-search-cluster"` and version
`3.7.0`. Then stop it:

```bash
sudo -u db2inst1 kill "$(cat /opt/opensearch/opensearch.pid)"
```

---

### Step 3 — Enable Db2 Text Search + register OpenSearch

**(db2inst1)** Switch to the instance owner and configure Db2. From here on
everything runs as `db2inst1`:

```bash
su - db2inst1
```

**3.1 — Configure and start the instance** — TCP listener, **vector indexing on**
(required for `CREATE VECTOR INDEX` at ingest), a port, then build the `SAMPLE`
database:

```bash
db2set DB2COMM=TCPIP
db2set DB2_VECTOR_INDEXING=YES
db2start
db2 update dbm cfg using SVCENAME 25010
db2stop
db2start
db2sampl
```

**3.2 — Test the database** (five rows means Db2 is up):

```bash
db2 connect to sample
db2 "SELECT * FROM employee FETCH FIRST 5 ROWS ONLY"
```

**3.3 — Enable Text Search and register OpenSearch as its backend** (still connected
to `sample`). This is the step manual installs most often miss — without it the
vector leg works but ingest's `SYSTS_CREATE`/`SYSTS_UPDATE` fail with `CIE00323 … not
enabled for text` and there is **no lexical or hybrid search**:

```bash
db2 "CREATE TABLESPACE systoolspace"
db2 "CALL SYSPROC.SYSTS_ENABLE('en_US', ?)"
db2 "CALL SYSPROC.SYSTS_CREATE_SERVER('localhost', 9200, 'dummyuser:dummypassword', 'dummymasterkey2024', 'OPENSEARCH', 0, 2, 0, 'en_US', ?, ?)"
db2 "SELECT SERVERID, PORT FROM SYSIBMTS.TSSERVERS WHERE ENGINETYPE='OPENSEARCH'"
db2 connect reset
```

The `SELECT` must show the server as **`SERVERID 1`** — `scripts/1_ingest.sql`
hard-codes `'SERVERID 1'`. On a fresh database the first server registered gets ID 1;
if yours differs, edit the `SERVERID` in `1_ingest.sql` to match.

> `CREATE TABLESPACE systoolspace` may report "already exists" (if `db2sampl` made
> it) — harmless. `SYSTS_CREATE_SERVER`'s `dummyuser`/`dummypassword`/`dummymasterkey`
> are placeholders: OpenSearch security is off, so they're never used. Find your Db2
> port any time with `db2 get dbm cfg | grep 'SVCENAME'`.

---

### Step 4 — llama.cpp + the three models

**(db2inst1)** Db2's `TO_EMBEDDING` calls a local llama.cpp server — no API keys, no
network egress, no per-call cost. Run these **as db2inst1** so `llama.cpp` and the
models land in its home (`~`), where the service scripts look for them.

**4.1 — Build `llama-server`** (CPU; pinned to a known-good tag — the start scripts
depend on its `--pooling`/`--reranking` flag names):

```bash
git clone --depth 1 --branch b9913 https://github.com/ggml-org/llama.cpp.git ~/llama.cpp
cmake -S ~/llama.cpp -B ~/llama.cpp/build -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF -DGGML_NATIVE=ON
cmake --build ~/llama.cpp/build --target llama-server -j"$(nproc)"
```

**4.2 — Download the embedding model** (bge-small-en-v1.5, ~37 MB, **required**):

```bash
mkdir -p ~/models/bge-small-en-v1.5
curl -fSL -o ~/models/bge-small-en-v1.5/bge-small-en-v1.5-q8_0.gguf "https://huggingface.co/CompendiumLabs/bge-small-en-v1.5-gguf/resolve/main/bge-small-en-v1.5-q8_0.gguf"
```

**4.3 — Download the reranker model** (bge-reranker-v2-m3, ~438 MB, optional — the
Search tab's Rerank button):

```bash
mkdir -p ~/models/bge-reranker-v2-m3
curl -fSL -o ~/models/bge-reranker-v2-m3/bge-reranker-v2-m3-Q4_K_M.gguf "https://huggingface.co/gpustack/bge-reranker-v2-m3-GGUF/resolve/main/bge-reranker-v2-m3-Q4_K_M.gguf"
```

**4.4 — Download the generation model** (Qwen2.5-3B-Instruct, ~2 GB, optional —
query-understanding):

```bash
mkdir -p ~/models/qwen2.5-3b-instruct
curl -fSL -o ~/models/qwen2.5-3b-instruct/Qwen2.5-3B-Instruct-Q4_K_M.gguf "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf"
```

**4.5 — Sanity-test the embedding model** (start on a throwaway port :8099, embed
once, stop). `--pooling cls` is **required** — the wrong pooling silently degrades
quality:

```bash
~/llama.cpp/build/bin/llama-server -m ~/models/bge-small-en-v1.5/bge-small-en-v1.5-q8_0.gguf --embedding --pooling cls --ctx-size 512 --host 127.0.0.1 --port 8099 >/tmp/sanity.log 2>&1 &
until curl -s -o /dev/null http://127.0.0.1:8099/health; do sleep 1; done
curl -s http://127.0.0.1:8099/v1/embeddings -H 'Content-Type: application/json' -d '{"input":"hello"}' | python3 -c "import sys,json;print('dim', len(json.load(sys.stdin)['data'][0]['embedding']))"
fuser -k 8099/tcp
```

Expect `dim 384`. **4.6 — Sanity-test the reranker** (higher score for the relevant
document):

```bash
~/llama.cpp/build/bin/llama-server -m ~/models/bge-reranker-v2-m3/bge-reranker-v2-m3-Q4_K_M.gguf --reranking --pooling rank --ctx-size 2048 --host 127.0.0.1 --port 8099 >/tmp/sanity.log 2>&1 &
until curl -s -o /dev/null http://127.0.0.1:8099/health; do sleep 1; done
curl -s http://127.0.0.1:8099/v1/rerank -H 'Content-Type: application/json' -d '{"query":"building good habits","documents":["a book about tiny habits and behaviour change","a book about cooking pasta"]}' | python3 -c "import sys,json;print('scores', [round(r['relevance_score'],3) for r in json.load(sys.stdin)['results']])"
fuser -k 8099/tcp
```

The habits document should score higher than the pasta one. **4.7 — Sanity-test the
generation model:**

```bash
~/llama.cpp/build/bin/llama-server -m ~/models/qwen2.5-3b-instruct/Qwen2.5-3B-Instruct-Q4_K_M.gguf --ctx-size 2048 --host 127.0.0.1 --port 8099 >/tmp/sanity.log 2>&1 &
until curl -s -o /dev/null http://127.0.0.1:8099/health; do sleep 1; done
curl -s http://127.0.0.1:8099/v1/chat/completions -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"Reply with one word: hello"}]}' | python3 -c "import sys,json;print('reply:', json.load(sys.stdin)['choices'][0]['message']['content'])"
fuser -k 8099/tcp
```

A short reply means it works. (If a `curl` fails, the server's log is in
`/tmp/sanity.log`.) These were throwaway servers — Step 8 starts the real ones on
their proper ports.

---

### Step 5 — Get the code

**(db2inst1)** Clone the cookbook into db2inst1's home and enter this recipe — the
Python package, the service scripts, and the corpus all live here:

```bash
cd ~
git clone https://github.com/IBM/db2-ai-cookbook.git
cd db2-ai-cookbook/02-hybrid-search/sql-fusion-local-models
```

Every path from here on is relative to that folder.

---

### Step 6 — Python project

**(db2inst1)** A Python 3.12 venv installs the engine (`ibm_db`, FastAPI, uvicorn)
and makes `hybrid_search` importable:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
```

> The headless UI test needs Playwright + Chromium:
> `pip install playwright` then `python -m playwright install chromium`.

---

### Step 7 — Configure `.env`

**(db2inst1)**

```bash
cp .env.example .env
$EDITOR .env
```

The pipeline and app connect **locally as the instance owner** (fast, no password),
so most defaults are fine. Set `DB2_PASSWORD`, and `DB2_PORT` if you'll ever connect
over TCP (find it with `db2 get dbm cfg | grep 'SVCENAME'`). `.env` is git-ignored —
real credentials are never committed. See `.env.example` for every key.

---

### Step 8 — Start services & verify

**(db2inst1)** One command starts Db2, OpenSearch, the embedding server, and (if its
model is present) the reranker — all with no sudo:

```bash
./scripts/0_start-services.sh
```

Confirm each service is up:

```bash
db2gcf -s
curl -s -o /dev/null -w "opensearch: %{http_code}\n" http://localhost:9200
curl -s -o /dev/null -w "embeddings: %{http_code}\n" http://127.0.0.1:8085/health
```

`DB2 State : Available` and two `200`s means you're ready to ingest. That's the
one-time setup — **everything below is the day-to-day workflow.**

---

## Run the pipeline (ingest → search)

Ingest your corpus into Db2, then search it. Run these as `db2inst1`, from this
recipe's folder, with the services up (Step 8).

```bash
./scripts/preflight.sh
db2 -tvf scripts/1_ingest.sql
```

**Always run `preflight.sh` first.** It waits for OpenSearch and the embedding server
and fails with a clear message if either is down. Skipping it is the single most
confusing way to break setup — a stopped OpenSearch makes ingest reject *every row as
a duplicate key*, which looks like a data problem but is really a stopped service.

`1_ingest.sql` drops any existing table/index (so it's re-runnable), imports
`data/corpus.csv`, builds the Db2 Text Search index, registers the local embedding
model, fills a `VECTOR` column via `TO_EMBEDDING`, and builds the vector index.
**You should see:** `92 rows … successfully inserted`, then several
`DB20000I … completed successfully`.

Now verify the whole engine end-to-end — services **and** a real search:

```bash
./scripts/smoke-test.sh
```

**You should see:** `SMOKE TEST: PASS`. (Run this only *after* ingest — it searches
the corpus, so it fails with `MYSCHEMA.CHUNKS_EMBED is an undefined name` if
`1_ingest.sql` hasn't run yet.)

Then run the reference search — all three legs for one query, in one Db2 statement:

```bash
db2 -tvf scripts/2_search.sql
```

It prints the **lexical**, **vector**, and **hybrid** rankings side by side. When
you're done for the day:

```bash
./scripts/3_stop-services.sh
```

> Using your own data? Match the CSV schema in `data/corpus.csv` (the `IMPORT` in
> `1_ingest.sql` is positional), or edit the `IMPORT FROM` line. For lexical-only,
> delete the model/embed/vector sections of `1_ingest.sql`.

---

## Run the app

A web demo that shows each retriever's blind spot and how hybrid covers it.

```bash
./ui/run.sh
./ui/run.sh --live
```

- **Offline** (`./ui/run.sh`) is the conference/demo path — it serves committed
  fixtures, so it runs anywhere with just Python 3 → http://127.0.0.1:8000
- **Live** (`./ui/run.sh --live`) answers ad-hoc queries against Db2 (needs Step 8's
  services up); API docs at `/docs`.

Both modes bind `127.0.0.1`, so on a remote box you reach the app by forwarding port
8000 to your laptop (VS Code Remote-SSH does this from its **PORTS** panel). `PORT`
and `HOST` override the defaults:

```bash
PORT=8100 ./ui/run.sh --live          # a different port
HOST=0.0.0.0 ./ui/run.sh --live       # every interface → http://<this-host-ip>:8000
```

`HOST=0.0.0.0` skips forwarding altogether, but publishes an **unauthenticated** app —
and the staged copy of `.env` holds the Db2 password. Trusted networks only.

See [ui/README.md](ui/README.md) for the tabs and design notes.

---

## Try it: example queries

For the shipped corpus. The principle is general: **exact terms favor keyword
search, paraphrases favor vectors, a mix favors hybrid.** Type one in the app's
Search tab, or use the Demo tab which runs curated cases automatically.

**Keyword wins** — an exact token the embedding can't place:
- `walter dixon` — the narrator's name; keyword nails it, the vector leg wanders off.
- `pragmatic programmer` — the exact title.

**Vector wins** — a description using none of the book's own words:
- `why we so often misjudge people we've just met` → *Talking to Strangers*.

**Hybrid wins** — an author/topic mix where both legs contribute:
- `how to build better habits` → *Atomic Habits* (keyword grabs a different
  self-help title; hybrid recovers the one you meant).
- `jason fung reversing type 2 diabetes` → *The Diabetes Code*.

## How the fusion works (and why not RRF)

Reciprocal Rank Fusion ranks by *position only*, so a leg that is essentially
guessing (vectors on an exact code, keywords on a pure paraphrase) injects its top
guesses with the same weight as the other leg's real hits — and they tie, so noise
floats up. Instead, the fusion (in [src/hybrid_search/core.py](src/hybrid_search/core.py)):

1. carries each leg's real score (BM25 `SCORE`, cosine similarity),
2. **gates** a leg out when its best score is below a threshold (off by default),
3. **max-normalizes** the survivors to `(0,1]`, and
4. takes a **weighted sum** (default `0.3·lexical + 0.7·vector`).

A document found by *both* legs is reinforced; a noisy leg is muted. Weights,
gates, and pool size are `.env`-tunable (`HYBRID_*`) — and **corpus-specific**;
re-tune with `eval.py` on your data.

## Measure search quality

```bash
DB2_HOST=local PYTHONPATH=src python scripts/eval.py
```

Scores the shipped **golden eval set** ([data/eval/golden_set.json](data/eval/golden_set.json))
against all three legs — MRR/Hits@1 for known-item queries, Recall@5/nDCG@5 for
topical — reported on a held-out slice (never tuned on), TRAIN, and ALL, with a
per-query-type diagnostic. Run it after any change to the corpus, embedding model,
or `HYBRID_*` knobs. Results and method: [docs/eval-results.md](docs/eval-results.md).

## Configuration

Everything is in [`.env`](.env.example): the Db2 connection and the optional
`HYBRID_*` fusion knobs (weights, gates, candidate-pool size). Embeddings are local
— no API keys. The schema/table names are fixed by the SQL scripts (see the note in
`.env.example`). The `QU_*` (query understanding) and `RERANK_*` (cross-encoder)
features ship **off**.

## Troubleshooting

The most common failure is running the pipeline with a service down — `preflight.sh`
and `smoke-test.sh` catch that. Symptom → cause → fix:

| Symptom | Cause | Fix |
|---|---|---|
| Ingest rejects **every** row: `SQL0803N` duplicate key (preceded by `SQL0601N`, `SQL20536N`) | **OpenSearch is down.** `SYSTS_DROP` fails → the text index survives → it blocks `DROP TABLE` → `CREATE TABLE` fails → `IMPORT` runs against the *old* table, so every row collides. The errors never mention the stopped service. | `./scripts/preflight.sh` before ingesting — it waits for OpenSearch/embeddings and says so plainly |
| Ingest: `CIE00323 … database not enabled for text` | Text Search was never enabled on the database | Run Step 3.3 (`SYSTS_ENABLE` + `SYSTS_CREATE_SERVER`), then re-ingest |
| Search: `CIE00701 Internal error` / `SQL20423N` on the text index | OpenSearch was reinstalled/wiped **after** the text index was built, orphaning it | Rebuild it: re-run `db2 -tvf scripts/1_ingest.sql` (drops + recreates the index on the current OpenSearch) |
| `MYSCHEMA.CHUNKS_EMBED is an undefined name` | The ingest hasn't run on this machine yet | `./scripts/preflight.sh` then `db2 -tvf scripts/1_ingest.sql` |
| `DB2_PORT` connection fails | real instances vary — don't assume 50000 | `db2 get dbm cfg \| grep 'SVCENAME'`, then look it up in `/etc/services` |
| `ModuleNotFoundError: ibm_db` / `hybrid_search` | package not installed in that python | `pip install -e .` as db2inst1, in the venv |
| `ibm_db` TCP connect hangs ~40s | slow TCP path on this setup | use `DB2_HOST=local` for the fast local connection |
| `TO_EMBEDDING` fails during ingest/search | embedding server not up on `:8085` | `./scripts/0_start-services.sh`; re-run the Step 4.5 sanity test |
| Embedding sanity prints a dim other than 384 | wrong model file or missing `--pooling cls` | re-download the GGUF and pass the flag |
| Reranker returns near-zero / identical scores | a broken GGUF conversion | use the `gpustack` bge-reranker-v2-m3 GGUF above; avoid unverified Qwen3-Reranker GGUFs |
| Browser won't load the app (blank page or "can't connect") while the terminal shows `Uvicorn running on http://127.0.0.1:8000` | **A stale VS Code port forward.** One created while the server was down — or surviving a restart — keeps showing as forwarded but tunnels nothing. The app is fine; requests never reach it | Delete the port entry in the VS Code **PORTS** panel, restart the app, let VS Code forward it again. See the check below before hunting for app bugs |

`run.sh --live` runs uvicorn in the **foreground** — it prints `Uvicorn running …` and
sits there without returning to a prompt. That is success, not a hang.

Before debugging the app, confirm requests are arriving at all. On the host, while
reloading the browser:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/   # 200 = app is fine
ss -tn state established | grep ':8000'                           # empty = nothing reaches it
```

A 200 with no connections means the fault is between the browser and the tunnel, not in
the app. Then, on your laptop: try `http://127.0.0.1:8000` rather than
`http://localhost:8000` (browsers resolving `localhost` to IPv6 `::1` miss an IPv4-only
forwarder), check the **Local Address** column in the PORTS panel in case VS Code
remapped the local port, and make sure a corporate proxy isn't intercepting localhost.

## Recipe layout

```
src/hybrid_search/   core.py (engine + fusion) · evalset.py (golden-set resolver)
                     understanding.py · rerank.py (optional stages, off by default)
scripts/   services: 0_start-services.sh · 3_stop-services.sh
           pipeline: preflight.sh · 1_ingest.sql · 2_search.sql
           quality:  eval.py · smoke-test.sh
           corpus:   build_chunk_text.py · fetch_covers.py · fetch_descriptions.py  (regenerate data/corpus.csv)
           query-understanding/ · rerank/   (optional; off by default)
data/      corpus.csv (the audiobook corpus) · eval/golden_set.json (eval queries)
ui/        run.sh · build_*.sh · api.py · static/ (Start · Search · Demo · Eval · Architecture)
tests/     README.md + test_*.py  (skip cleanly without Db2 / browser)
docs/      eval-results.md
```

## Docs

- [tests/README.md](tests/README.md) — how to run the test suites.
- [docs/eval-results.md](docs/eval-results.md) — search-quality evaluation.
- [ui/README.md](ui/README.md) — the demo UI internals.
- [scripts/query-understanding/README.md](scripts/query-understanding/README.md) · [scripts/rerank/README.md](scripts/rerank/README.md) — optional stages (off by default).

## License

[Apache-2.0](LICENSE) — the same licence the [cookbook](../../LICENSE) carries. This
recipe keeps its own copy because it is an installable package: `pyproject.toml`
reads `license = { file = "LICENSE" }`.

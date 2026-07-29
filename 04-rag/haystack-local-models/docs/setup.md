# Setup — from a bare RHEL box to a running recipe

[← back to the recipe](../README.md)

Everything here is one-time. Once it is done, the recipe is two commands — see
[Run the pipeline](../README.md#run-the-pipeline-ingest--search).

## Overview

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
cd db2-ai-cookbook/04-rag/haystack-local-models
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
[`.env.example`](../.env.example) for every key.

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
[Troubleshooting](troubleshooting.md).

That's the one-time setup — **everything below is the day-to-day workflow.**

---

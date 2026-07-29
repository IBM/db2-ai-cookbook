# Test plan

Scope: the ingestion and search layers of this repo, the Db2 integration they depend on, and the
setup instructions in [README.md](../README.md).

This is a teaching repo, so the goal of testing is not a production SLA. It is:

1. **A reader following the README reaches a working system** — the setup steps are correct and
   complete on a clean machine.
2. **The two pipelines still work after a change** — swapping the PDF, the model, `top_k`, or the
   chunk budget does not silently break retrieval.
3. **The known failure modes stay fixed** — each bug found while building this has a test.

---

## The one property that shapes every test

Measured on this implementation, repeating the same query twice:

| Layer | Deterministic? | Evidence |
| --- | --- | --- |
| Embedding + retrieval | **Yes** | Same query → identical ranking and identical scores (`0.308 / 0.418 / 0.430`) on repeated runs |
| Generation, `temperature: 0` | **Yes, after the first request** | Runs 2 and 3 byte-identical; **run 1 after a server restart differs** — a cold prompt cache changes the numerics enough to alter the sampled path |
| Generation, sampling on (the old default) | **No** | Same chunks → different wording every run |

**Two rules follow.**

1. **Warm up before asserting on generated text.** Discard the first generation after
   `llama-servers.sh start`; from the second onward it repeats exactly.
2. **Still prefer asserting on retrieval and on *properties* of the answer** (non-empty, declines,
   contains a term from a retrieved chunk) rather than exact strings — exact text is stable within
   one model build but not across a model, llama.cpp, or prompt change.

A second caveat: embedding scores can drift in the **third decimal** across re-ingests, because
embeddings are recomputed and CPU batching is not bit-stable. Assert on *ordering* and on
thresholds (`< 0.45`), never on exact score equality.

---

## Preconditions

Every test below assumes: Db2 started (`db2start`), both llama.cpp servers up
(`scripts/llama-servers.sh status`), `.env` filled in, and `PYTHONPATH=src`.

`ENV-*` tests verify exactly those preconditions and should run first — everything else fails
confusingly when they do not hold.

---

## Level 0 — Environment (`ENV`)

| ID | What it checks | How | Expected |
| --- | --- | --- | --- |
| ENV-01 | Db2 is new enough for `VECTOR` | `db2level` | `DB2 v12.1.2` or later |
| ENV-02 | TCP listener enabled | `db2set -all \| grep DB2COMM` | `DB2COMM=TCPIP` |
| ENV-03 | `VECTOR` type actually usable | Create a throwaway table with `VECTOR(4, FLOAT32)`, insert 2 rows, run `VECTOR_DISTANCE(..., COSINE)`, drop it | Aligned vector ranks first; no SQL error |
| ENV-04 | Credentials in `.env` work, table writable | The Step 7 stack check in the README | `Db2 OK — N chunks in the table` |
| ENV-05 | Embedding server up and correct | `POST /v1/embeddings` on `:8081` | 200, embedding length **384** |
| ENV-06 | Chat server up | `POST /v1/chat/completions` on `:8080` | 200, non-empty `choices[0].message.content` |
| ENV-07 | Embedding dim matches the table | `EMBED_DIM` in `settings.py` vs `SYSCAT.COLUMNS.LENGTH` for `EMBEDDING` | Both **384** |

---

## Level 1 — Components (`CMP`)

Each is one pipeline stage in isolation, so a failure points at one component.

| ID | What it checks | How | Expected |
| --- | --- | --- | --- |
| CMP-01 | Docling parses and chunks | Run `DoclingConverter` alone on the sample PDF | **70** `Document`s (this PDF), all with non-empty `content` |
| CMP-02 | Metadata is present and flat | Inspect `doc.meta` of every chunk | Every chunk has `page_number` (int) and `headings` (str); **no `dl_meta`**, no key starting with `$` |
| CMP-03 | Chunk budget is respected | Tokenize each chunk with `BAAI/bge-small-en-v1.5` | **Max ≤ 512**; on this PDF median ≈ 331, max ≈ 456 |
| CMP-04 | Document embedder | `OpenAIDocumentEmbedder.run()` on one Document | `len(doc.embedding) == 384`, all floats |
| CMP-05 | Text embedder + query prefix | `OpenAITextEmbedder.run(text=...)` | Length 384; the bge query prefix is applied |
| CMP-06 | Store round-trip | Write 1 Document, read it back with `filter_documents()` | Same `id`, `content`, `meta`; embedding preserved |
| CMP-07 | Retriever ranking | `IBMDb2EmbeddingRetriever.run(query_embedding=...)` | Exactly `top_k` Documents, `score` ascending (cosine **distance**) |
| CMP-08 | Metadata filter | Same, with `filters={"field": "meta.page_number", "operator": "==", "value": 4}` | Every returned doc has `page_number == 4`; count ≤ `top_k` |
| CMP-09 | Prompt rendering | `ChatPromptBuilder.run(documents=[...], question=...)` | One `ChatMessage`; contains each doc's content and the question |
| CMP-10 | Generator | `OpenAIChatGenerator.run([ChatMessage...])` | Non-empty `replies[0].text` |

---

## Level 2 — Integration (`INT`)

| ID | What it checks | How | Expected |
| --- | --- | --- | --- |
| INT-01 | Ingest end to end | `python -m haystack_db2_rag.ingest data/M-Lean_Article.pdf` | `Stored 70 chunks in HAYSTACK_DOCUMENTS.`, exit 0 |
| INT-02 | Rows landed | `SELECT COUNT(*) FROM HAYSTACK_DOCUMENTS` | **70** |
| INT-03 | Stored natively as vectors | `SELECT TYPENAME, LENGTH FROM SYSCAT.COLUMNS WHERE COLNAME='EMBEDDING'` | `VECTOR`, `384` |
| INT-04 | Ingest is re-runnable | Run INT-01 twice, then INT-02 | Still **70**, not 140 — `recreate_table=True` drops first |
| INT-05 | Search end to end | `python -m haystack_db2_rag.search "What is M-Lean?"` | Exit 0; prints `Q:`, `A:` with non-empty text, and 3 `Retrieved:` lines |
| INT-06 | Citations are well-formed | Same output | Each retrieved line has a score, `p.<int>`, and a heading string |
| INT-07 | SQL-only search works | The `ORDER BY VECTOR_DISTANCE(...)` query from the README | 3 rows, no error — proves the data is usable without Haystack |
| INT-08 | A different document works | Ingest another PDF, then search it | Chunk count > 0; answers cite that document |

---

## Level 3 — Retrieval behaviour (`RET`)

The tests that actually measure whether the system is *good*, not merely running.

| ID | What it checks | How | Expected |
| --- | --- | --- | --- |
| RET-01 | Known-answer retrieval | Ask `"What is M-Lean?"` | Top hit is the title/abstract chunk from **p.1**; top score **< 0.45** |
| RET-02 | Ranking is deterministic | Run RET-01 twice | Identical ordering and identical `id`s (scores may differ in the 3rd decimal only after a re-ingest) |
| RET-03 | Filter narrows correctly | `search "..." 4` | **All** hits `p.4`; result set is a subset of the unfiltered run |
| RET-04 | Grounding holds | Ask `"What is the capital of France?"`, **10 times** | All 10 decline; none asserts "Paris". This test found a real regression: with the refusal sentence missing from the prompt and sampling on, 5 of 6 runs answered "The capital of France is Paris" |
| RET-05 | `top_k` is honoured | Set `top_k` to 1 and 10 | Exactly 1 and 10 retrieved lines |
| RET-06 | Query prefix matters | Remove the bge query prefix and re-run RET-01 | Scores change measurably — documents the prefix is doing work (informational, not pass/fail) |

RET-04 is the single most important regression test in this plan: it is the one that fails when a
prompt edit quietly turns a grounded RAG system back into a chatbot.

---

## Level 4 — Failure modes (`FAIL`)

Each asserts that a *predictable* break produces the *documented* error — these are what keep the
README's troubleshooting table honest.

| ID | Induce | Expected error | README row |
| --- | --- | --- | --- |
| FAIL-01 | Wrong `DB2_PASSWORD` | `SQL30082N … reason "24"` | "USERNAME AND/OR PASSWORD INVALID" |
| FAIL-02 | `db2stop` then search | **`SQL30081N`** communication error (the Python client is over TCP; only the `db2` CLI says `SQL1032N`) | "Db2 isn't running" |
| FAIL-03 | Embedding server stopped | Connection refused on `:8081` | "Connection refused on :8081 or :8080" |
| FAIL-04 | Chat server stopped | Connection refused on `:8080` | same row |
| FAIL-05 | Search before any ingest | `Nothing was retrieved` warning, then a decline — never a confident answer | "Nothing was retrieved" |
| FAIL-06 | `PYTHONPATH` unset | `ModuleNotFoundError: haystack_db2_rag` | "The package lives in src/" |

---

## Level 5 — Regression tests for bugs already found (`REG`)

Every one of these was a real failure during development. They are the highest-value tests here
because each has already happened once.

| ID | Bug | Test | Expected |
| --- | --- | --- | --- |
| REG-01 | Docling's `$ref` keys break Db2's BSON metadata → **every** insert fails with `SQL0443N … JSON2BSON` | Remove `meta_extractor=SimpleMeta()` and ingest | Ingest fails. With `SimpleMeta`, all 70 rows insert |
| REG-02 | A chunk exceeded the 512-token window and was silently truncated | CMP-03 with `EMBED_MAX_TOKENS = 512` | At 512 at least one chunk > 512 tokens on this PDF; at 448, none |
| REG-03 | `curl -s` treats `/health`'s 503 as ready, so scripts race the model load | `scripts/llama-servers.sh start` from cold, immediately `status` | Reports up only when genuinely ready; never a `KeyError: 'choices'` |
| REG-04 | llama.cpp build pulls a mismatched prebuilt web UI | Build with the two `-DLLAMA_*_UI=OFF` flags | `Built target llama-server`, no `loading.html` error |
| REG-06 | One zero-vector row silently kills **all** search | Write a Document with `embedding=[0.0]*384`, run any query, then delete it and re-query | With the row: **0 hits** (and `SQL0801N` division by zero if the same ranking query is run in the `db2` CLI). Without it: `top_k` hits again |
| REG-05 | Class names drifted from the blog (`Db2DocumentStore` → `IBMDb2DocumentStore`) | `python -c "from haystack_integrations.document_stores.ibm_db import IBMDb2DocumentStore"` | Imports cleanly; pinned by `requirements.txt` |

---

## Level 6 — Documentation (`DOC`)

The README is the product here, so it gets tests too.

| ID | What it checks | How |
| --- | --- | --- |
| DOC-01 | Every internal anchor resolves | Extract `](#...)` links, compare against generated heading slugs |
| DOC-02 | Every relative file link exists | Extract `](path)` links, `os.path.exists` |
| DOC-03 | Every external link is alive | `curl -sIL -o /dev/null -w "%{http_code}"` per URL → 200 |
| DOC-04 | Every `.env` key named in the README exists in `.env.example`, and every key in `.env.example` is read by `settings.py` | grep both directions — catches settings that silently do nothing |
| DOC-05 | Commands in the README match reality | Module names in README == modules in `src/haystack_db2_rag/` |

DOC-04 exists because three dead keys (`DISTANCE_METRIC`, `EMBED_DIM`, `LLAMACPP_API_KEY`) were
once advertised in `.env.example` and read by nothing.

---

## Harness gotchas (learned the hard way)

Any automation written against this stack must avoid two traps that produced false failures on the
first run of this plan:

- **Db2 CLP connections do not survive `$( )`.** Command substitution forks a subshell, and the
  CLP back-end process is keyed to the shell's PID, so a `db2 connect` in the parent is invisible
  inside `$(db2 -x "SELECT …")`. Put the `connect` *inside* the same substitution.
- **Never count SQL rows with `grep -c .`** — stored `CONTENT` is a CLOB containing newlines, so
  one row can print as several lines. Use `SELECT COUNT(*)` over a subquery.

## Out of scope

- Db2 installation itself (Step 1) — needs licensed media and a clean machine; verify manually
- Model quality benchmarking — no golden eval set here; RET-01/04 are sanity checks, not metrics
- Concurrency, load, failover — single-user tutorial
- Windows/macOS — Db2 server install is Linux here

---

## How to run this today

There is no test framework installed; `requirements.txt` deliberately has four entries. Two
options:

**Option A — a shell smoke test** (fits the repo's minimalism). One `scripts/smoke-test.sh`
running ENV-01…07, INT-01…03, INT-05, and RET-03/04, printing `SMOKE TEST: PASS`. No new
dependencies, and it doubles as the "did my setup work" script a reader wants anyway.

**Option B — pytest** (better if this repo keeps growing):

```
tests/
  conftest.py      fixtures: the store, a converted-once PDF (session-scoped — parsing is slow)
  test_env.py      ENV-*     skip cleanly when Db2 or a server is unreachable
  test_components.py CMP-*
  test_integration.py INT-*, RET-*
  test_regressions.py REG-*
  test_docs.py     DOC-*     pure-python, no services needed — runs in CI
```

with `pip install pytest` added as a dev extra. Mark service-dependent tests so
`pytest -m "not needs_db2"` still runs the documentation and chunking tests anywhere.

**Cost note:** CMP-01 and anything ingesting takes ~50 s (warm) because parsing runs on CPU —
convert the PDF **once** per session and share it via a fixture, or the suite will take minutes.

## Exit criteria

A change is safe to commit when: all ENV pass, INT-01…06 pass, RET-01/03/04 pass, and every REG
test still passes. DOC-01…05 should pass before any README edit is pushed.

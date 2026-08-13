# RAG on IBM Db2 12.1.2+ with Haystack, Docling, and local models

> **Last checked 2026-08-12** — verified: 70 chunks ingested, a grounded answer with citations, metadata filtering (10 table chunks, 33 sections) with both model servers stopped, and the grounding check declining an unanswerable question 10 times out of 10.  
> Checked on: Db2 12.1.5.0 · RHEL 10 · Python 3.12.

[← Db2 AI Cookbook](../../README.md) · [← RAG module](../README.md)

This tutorial builds **retrieval-augmented generation over your own PDF**, using IBM Db2 as the
vector database and nothing but local models:

- **Vector storage** — native Db2 `VECTOR` columns
- **Vector similarity** — `VECTOR_DISTANCE` (cosine), through Haystack's Db2 integration
- **Metadata filtering** — the same rows also answer structured queries (by section, page, or
  "contains a table"), either on their own or as a pre-filter for the vector search
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
- [Setup](#setup) → the full seven steps live in [docs/setup.md](docs/setup.md)
- [Run the pipeline](#run-the-pipeline-ingest--search)
- [Try it: example questions](#try-it-example-questions)
  - [More questions to try](#more-questions-to-try)
- [How the PDF is chunked](#how-the-pdf-is-chunked-and-why-not-documentsplitter)
- [Verify the vectors in Db2](#verify-the-vectors-in-db2)
- [Metadata filtering: the other half of the table](#metadata-filtering-the-other-half-of-the-table)
  - [Filtering on numbers](#filtering-on-numbers)
- [Deterministic generation](#deterministic-generation)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting) → [docs/troubleshooting.md](docs/troubleshooting.md)
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
| 1 | `converter` | `DoclingConverter` | Parses the PDF, chunks it with `HybridChunker`, attaches the [filterable metadata](#metadata-filtering-the-other-half-of-the-table) — page, section, `has_table` — via `SimpleMeta`. Out: 70 `Document`s with text and metadata, no vectors yet |
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
(**384**), the distance metric (**cosine**), and the metadata keys (`page_number`, `section`,
`has_table` and the rest — see [Metadata filtering](#metadata-filtering-the-other-half-of-the-table)).
Change one on one side only and retrieval breaks — silently.

Two llama.cpp servers, because one `llama-server` process serves one model.

---

## Setup

One-time, and it is the long part: Db2, the two local models, the Python project and the
servers. It lives in its own page so this one stays about the recipe.

**→ [docs/setup.md](docs/setup.md)**

Already have Db2 12.1.2+ and llama.cpp running? You need `.env` filled in and both servers
up, then continue below.

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

Add a flag to filter on metadata *before* the vector search — Db2 narrows the rows, then ranks only
those:

```bash
.venv/bin/python -m haystack_db2_rag.search "What does the proposed framework look like?" --page 4
.venv/bin/python -m haystack_db2_rag.search "What is in Table 1?" --tables-only
```

`--page`, `--section`, `--tables-only` and `--top-k` are all optional and combine. `--top-k` is
bounded by the chat server's context window: each chunk is up to 448 tokens, so `--top-k 10` needs
about 3.2k and the server is started with `--ctx-size 8192` to leave room.
[Metadata filtering](#metadata-filtering-the-other-half-of-the-table) covers what you can filter on
and how to query it without asking a question at all.

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
  [0.309] p.1 M-Lean: An end-to-end development framework...: Mona Nashaat a , ∗ , Aindrila...
  [0.418] p.4 5. Proposed framework design: Table 1 Proposed framework vs. Lean Startup...
  [0.430] p.4 5. Proposed framework design: build-measure-learn loop is the core of...
```

Lower scores are closer — they are cosine **distances**, not similarities.

**A metadata-filtered question** — the page filter runs in Db2 before the similarity search, so
every hit comes from page 4:

```
$ .venv/bin/python -m haystack_db2_rag.search "What does the proposed framework look like?" --page 4

A: The proposed framework looks like a structured process divided into three phases, each
   with specific objectives, research questions, and methods for data collection...

Retrieved:
  [0.298] p.4 5. Proposed framework design: Table 1 Proposed framework vs. Lean Startup...
  [0.302] p.4 5.1. Getting more from business data...: The framework starts with a...
  [0.315] p.4 5.1. Getting more from business data...: Table 2 Outlines of the framework...
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
| *What are the phases of the M-Lean framework?* | Instructive **imperfection**: retrieval favours the build-measure-learn chunk, so the answer describes that loop's stages rather than the paper's exploratory/improving phases. Compare `--top-k` values, or add `--section "5. Proposed framework design"`, and watch the answer change |

That last row is worth running deliberately. It shows the thing that matters most in RAG: the
answer is only ever as good as the chunks the retriever chose, and a confident-sounding answer
can still be aimed at the wrong part of the document. It depends on **both** halves of the
generator setup: the "do not use any other knowledge" sentence in the prompt, *and*
`temperature: 0`. With sampling left on, this same question answered "The capital of France is
Paris" in 5 of 6 runs.

> **On reproducibility:** at `temperature: 0` the same question gives byte-identical answers, with
> one exception — see [Deterministic generation](#deterministic-generation).

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
`SimpleMeta` extractor that flattens what it needs — pages, section, `has_table` — into plain keys.
Without it **every** insert fails with `SQL0443N … JSON2BSON`. What survives is what you can filter
on: see [Metadata filtering](#metadata-filtering-the-other-half-of-the-table).

## Verify the vectors in Db2

> **This section is the one place the tutorial leaves Python.** Nothing here is application code —
> you never write SQL to build this system, and the two chapters around this one don't. It is here
> to prove a point that the Python API cannot: that Db2 is storing these vectors *natively*.

The vectors are ordinary Db2 data — you can inspect them from the `db2` CLI, with no application
running:

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

Your data is not locked inside a framework — but you never need this to *use* it. Back to Python
for the rest of the recipe.

## Metadata filtering: the other half of the table

Vector search is one way to query this table. The other is the **metadata Docling extracted**,
stored as BSON in the `META` column and queried with ordinary SQL predicates — no embeddings, no
model servers, no question. A vector database that is also a relational database gives you both,
and they compose.

`ingest.py` writes seven fields per chunk, all flat and all filterable:

| Field | Type | Example |
| --- | --- | --- |
| `source` | text | `M-Lean_Article.pdf` |
| `page_number` · `page_start` · `page_end` | integer | `4` · `4` · `5` — 11 of the 70 chunks straddle a page break |
| `section` | text | `5. Proposed framework design` |
| `headings` | text | `5. Proposed framework design > 5.1. Getting more from business data` |
| `has_table` | boolean | `true` for the 10 chunks that contain a table |

Run [metadata.py](src/haystack_db2_rag/metadata.py) to explore them. **Neither llama.cpp server has
to be running** — this is Db2 answering on its own:

```bash
.venv/bin/python -m haystack_db2_rag.metadata
```

```
Metadata fields:
  has_table        boolean
  page_number      integer
  section          text
  ...

33 sections, from 'Information and Software Technology' to 'References':

has_table == True — 10 chunks
  p.11  6.3. Phase 2 first development ite Table 5 MVM preliminary results in the first
  p.4   5. Proposed framework design       build-measure-learn loop is the core of the
```

The filters are plain dicts, and the operators come from the Db2 integration:

| Operator | Notes |
| --- | --- |
| `==` `!=` | any type; `!=` also matches chunks where the field is absent |
| `>` `>=` `<` `<=` | numbers and ISO date strings only — **see the caveat below** |
| `in` `not in` | takes a list; the reliable way to express a set of pages |
| `AND` `OR` `NOT` | take a `conditions` list, and nest |

The same dict either **queries metadata alone**:

```python
store.filter_documents({"field": "meta.has_table", "operator": "==", "value": True})
store.count_documents_by_filter({"field": "meta.section", "operator": "==", "value": "8. Conclusions"})
```

…or **narrows a vector search**, where Db2 applies it *before* ranking, so similarity is computed
only over rows that already match:

```bash
.venv/bin/python -m haystack_db2_rag.search "What is in Table 1?" --tables-only
.venv/bin/python -m haystack_db2_rag.search "What are the phases?" --section "5. Proposed framework design"
```

You never write SQL for any of this. The integration turns these dicts into predicates against the
`META` column, opens and closes the connection, and hands back `Document` objects — the same way
`DocumentWriter` put them there in the first place.

### Filtering on numbers

One behaviour to know about. Metadata comparisons in `ibm-db-haystack` 0.2.0 are made as **strings**,
so the `>` `>=` `<` `<=` operators sort lexicographically:

```python
store.filter_documents({"field": "meta.page_number", "operator": ">=", "value": 2})
# pages 2-9 only (29 chunks) — 10 to 15 are silently dropped, because "10" < "2" as text
store.filter_documents({"field": "meta.page_number", "operator": "<=", "value": 12})
# pages 1, 10, 11, 12 (21 chunks) — not pages 1 through 12
```

No error, just quietly wrong results — the failure mode worth knowing about before you trust a
range filter. `==`, `in`, and ranges within one digit width (`4 <= p <= 6`) are all correct.

**The fix is `in` with an explicit list** — it compares each value on its own, so text ordering
never enters into it:

```python
store.filter_documents(
    {"field": "meta.page_number", "operator": "in", "value": [10, 11, 12, 13, 14, 15]}
)  # 34 chunks — every chunk on pages 10 to 15
```

`get_metadata_field_min_max("page_number")` gives you the bounds to build that list from.

## Deterministic generation

RAG is easier to trust, and far easier to test, when the same question gives the same answer. This
recipe pins every layer it can:

| Layer | Deterministic? | Why |
| --- | --- | --- |
| Embedding + retrieval | **Yes** | Same question → identical ranking and identical scores (`0.298 / 0.302 / 0.315` for the page-4 example above, run after run) |
| Generation | **Yes**, after the first request | `generation_kwargs={"temperature": 0}` in [search.py](src/haystack_db2_rag/search.py) — greedy decoding, no sampling |

`temperature: 0` is doing more than making output repeatable. It is half of what keeps the system
**grounded**: with sampling left on, *"What is the capital of France?"* answered "Paris" in 5 of 6
runs despite the prompt's instruction to use only the excerpts. The instruction and the temperature
are both load-bearing.

Two caveats when comparing outputs:

- **Discard the first generation after `llama-servers.sh start`.** Its prompt cache is cold, and the
  numerics differ just enough to change the sampled path. From the second request onward, answers
  are byte-identical.
- **Embedding scores can drift in the third decimal after a re-ingest**, because embeddings are
  recomputed and CPU batching is not bit-stable. Assert on ordering and thresholds, never on exact
  score equality.

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

Symptom → cause → fix, including the failures that cost the most time here — the WebUI build
abort, the `/health` 503 race, and `SQL0443N … JSON2BSON`.

**→ [docs/troubleshooting.md](docs/troubleshooting.md)**

## Recipe layout

```
src/haystack_db2_rag/   settings.py (all config, from .env) · store.py (the Db2 connection)
                        ingest.py    converter → embedder → writer
                        search.py    text_embedder → retriever → prompt_builder → generator
                        metadata.py  filtering on its own — no embeddings, no model servers
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

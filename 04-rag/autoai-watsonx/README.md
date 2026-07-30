# RAG whose pattern was chosen by AutoAI

> **Last checked 2026-07-29** — *partially* verified: runs as far as submitting the AutoAI experiment, which then fails server-side with `BXNIM0415E` (see [Troubleshooting](#troubleshooting)).  
> Checked on: Db2 12.1.5.0 · RHEL 10 · Python 3.12.

[← RAG](../README.md) · [← Db2 AI Cookbook](../../README.md)

> Instead of picking the chunk size, the embedding model and the retrieval depth yourself, let
> **watsonx.ai AutoAI RAG** search that space, benchmark the candidates against your own
> questions, and hand you the winner. Then materialise the winning pattern into a Db2 `VECTOR`
> column and query it with plain SQL.

![Db2](https://img.shields.io/badge/store-Db2%2012.1.2%2B%20VECTOR-054ada)
![watsonx.ai](https://img.shields.io/badge/AutoAI%20RAG-watsonx.ai-0f62fe)
![Cloud](https://img.shields.io/badge/needs-IBM%20Cloud%20COS-important)

The other three recipes in this module are hand-built pipelines — you choose every parameter. This
one automates the choosing and, unlike them, comes with an **evaluation harness**: a question set,
a benchmark file, and answer-correctness scoring, so "which pattern is better" is measured rather
than assumed.

The corpus is a set of published Db2 machine-learning articles, and the questions are about their
content.

> **Verification status.** Everything up to and including experiment *submission* is verified on
> Db2 12.1.5 with watsonx.ai: credentials, data-asset upload, the optimizer run being created and
> polled. The experiment itself then failed server-side with `BXNIM0415E` (see
> [Troubleshooting](#troubleshooting)) — an environment/permissions matter, not a code defect. The
> Db2 half of the recipe has therefore not been executed end to end.

## Quick start

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # watsonx.ai key + project, and your COS connection
jupyter lab autoai-rag.ipynb
```

> **This is the only recipe in the cookbook that cannot run from one box.** AutoAI RAG reads its
> training and evaluation data from an **IBM Cloud Object Storage** bucket, so you need a COS
> instance and a connection asset in your watsonx.ai project, on top of the runtime itself.

The notebook downloads [`db2.ipynb`](https://github.com/IBM/db2-jupyter) on first run — that is
what provides the `%sql` magic.

## Expected output

The notebook runs in two halves.

**1 — AutoAI searches for a pattern.** It uploads the corpus and the benchmark questions to COS,
runs the experiment, then prints the best pattern it found — the chunking settings, the embedding
model, the retrieval depth and the answer-correctness score it achieved.

**2 — You rebuild that pattern against Db2.** The winning configuration is applied by hand: chunk
the articles, embed them with the chosen model, and write them into a table you own:

```sql
CREATE TABLE DB2ML_BLOGS(
  chunk     VARCHAR(1024),
  embedding VECTOR(1024, FLOAT32)
)
```

Questions are then answered with a single SQL retrieval feeding a watsonx.ai model:

```sql
SELECT CHUNK,
       VECTOR_DISTANCE(VECTOR('…query vector…', 1024, FLOAT32), EMBEDDING, EUCLIDEAN) AS DISTANCE
FROM DB2ML_BLOGS
ORDER BY DISTANCE ASC
FETCH FIRST 5 ROWS ONLY
```

> **The saved outputs of the five question cells have been cleared and need regenerating.** They
> were produced before the ordering fix described below, so they no longer match the code. Run the
> notebook with your own credentials to repopulate them.

## Concepts

### What AutoAI RAG actually automates

A RAG pipeline has a dozen knobs — chunk size, overlap, embedding model, number of chunks
retrieved, the prompt. Tuning them by hand means guessing, and most tutorials simply pick values
and move on. AutoAI RAG treats it as a search problem: it generates candidate patterns, scores
each against a benchmark you supply, and ranks them.

What you get back is a *configuration*, not a service. That is why the second half of the notebook
exists — the pattern is re-implemented against Db2, so the vectors live in your database and
retrieval is ordinary SQL.

### Lower distance means closer

`VECTOR_DISTANCE` returns a **distance**: 0 is identical, larger is further apart. Retrieval must
therefore sort **ascending**.

This is worth stating plainly because the original notebook did the opposite — it aliased the
distance as `SIMILARITY` and sorted `DESC`, which returns the *least* related chunks. The five
question cells were feeding the model the worst five matches in the corpus; several of the saved
answers had degenerated into multiple-choice quizzes, which is what a model does when the context
is irrelevant. The queries here sort `ASC` and the alias is `DISTANCE`.

### 1024 dimensions

The embedding model AutoAI selected produces 1024-dimension vectors, so the column is
`VECTOR(1024, FLOAT32)`. Change the model and that number changes with it.

---

## Appendix

### Credentials

`.env` holds `WATSONX_APIKEY`, `WATSONX_PROJECT`, and your COS connection details; it is
gitignored, and `.env.example` shows the shape. Db2 is reached as the local instance owner
through the `%sql` magic.

### Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `ModelInference.txt` shrinks to ~75 bytes containing "Redirecting to v1.6.0/…" | The training corpus is scraped live from `ibm.github.io/watsonx-ai-python-sdk/fm_model_inference.html`, which now serves a **client-side redirect**. `WebBaseLoader` captures the redirect stub, not the documentation, and overwrites the file — so AutoAI would train on 75 bytes of nothing | Skip the scrape cell and keep the committed `ModelInference.txt`, or point the loader at the versioned URL it redirects to (`…/v1.6.0/fm_model_inference.html`) |
| The AutoAI experiment reaches `failed` with `BXNIM0415E … Provided API key could…` | The **training job**, running server-side, cannot authenticate back to a service. Your key can be perfectly valid for SDK calls and still fail here | Check that the project has a **watsonx.ai Runtime instance associated** and that the API key carries the permissions the training job needs. Verified: SDK-level calls (`data_assets.list()`, `AutoAI.runs()`, embeddings, generation) all succeed while the job still fails |
| `ModuleNotFoundError: tqdm` on the first import cell | `ibm_watsonx_ai.experiment` imports `tqdm` without declaring it | Already pinned in `requirements.txt` — do not remove it |
| `ModuleNotFoundError: pysqlite3` | Loaded dynamically via `__import__('pysqlite3')`, so it is invisible to dependency scanners | `pysqlite3-binary` is pinned in `requirements.txt` |
| `ModuleNotFoundError: matplotlib` midway through | pandas imports matplotlib lazily when `.plot()` is called | `matplotlib` is pinned in `requirements.txt` |
| `Model '<id>' is not supported for this environment` | watsonx retires and versions model IDs on a published lifecycle | List what your project can actually use with `client.foundation_models.get_model_specs()`; this recipe targets `meta-llama/llama-3-3-70b-instruct` and `ibm/granite-embedding-278m-multilingual` |
| The AutoAI experiment fails to start | No COS connection asset in the watsonx.ai project | Create the connection, then put its ID in `.env` |
| `%sql` is not defined | `db2.ipynb` did not download | Fetch it from [IBM/db2-jupyter](https://github.com/IBM/db2-jupyter) into this folder |
| Answers look like quiz questions, or ignore the corpus | Retrieval returned irrelevant chunks — check the `ORDER BY` is `ASC` | Distances sort ascending; closest first |
| `SQL0601N  DB2ML_BLOGS already exists` | A previous run created it | Drop it before re-running the create cell |
| Vector dimension mismatch on insert | The column and the embedding model disagree | Both must be 1024 for the model used here |

### Files

```
autoai-rag.ipynb                          the recipe
questions.csv                             the benchmark questions
benchmarking_data_ModelInference.json     the benchmark definition
ModelInference.txt                        the corpus text
output.csv                                AutoAI experiment results
export/                                   db2ml_blogs_ddl.sql · mlblogs_data.csv
requirements.txt                          pinned
.env.example                              watsonx.ai + COS credentials template
```

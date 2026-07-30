# Tabular similarity search with watsonx.ai embeddings

> **Last checked 2026-07-29** — verified: watsonx embedded 20 rows at 1024-dim into a Db2 `VECTOR` column; `VECTOR_SERIALIZE`, `VECTOR_DIMENSION_COUNT`, `VECTOR_NORM` and `VECTOR_DISTANCE` all exercised.  
> Checked on: Db2 12.1.5.0 · RHEL 10 · Python 3.12.

[← Tabular search](../README.md) · [← Db2 AI Cookbook](../../README.md)

> Turn each row of a table into a vector with the watsonx.ai embedding API, store it in a Db2
> `VECTOR` column, and explore the four in-database vector functions from a Jupyter notebook.

![Db2](https://img.shields.io/badge/store-Db2%2012.1.2%2B%20VECTOR-054ada)
![watsonx.ai](https://img.shields.io/badge/embeddings-watsonx.ai%20cloud-0f62fe)
![Python](https://img.shields.io/badge/Python-3.12-blue)

Where [pure-sql](../pure-sql/) starts from vectors that already exist, this recipe **makes
them**: it concatenates each patient's columns into a sentence, sends the batch to
`multilingual-e5-large` on watsonx.ai, and writes the resulting 1024-dimension vectors back into
Db2. Same table, same question — the other half of the story.

## Quick start

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then add your watsonx.ai API key and project ID
jupyter lab similar-patients-search.ipynb    # or open it in VS Code
```

The notebook downloads [`db2.ipynb`](https://github.com/IBM/db2-jupyter) on first run — that is
what provides the `%sql` magic it uses to talk to Db2.

> ⚠️ **This recipe rebuilds the `PATIENTS` table** with a `VECTOR(1024)` column. Where `SAMPLE`
> ships its own `PATIENTS` — verified on Db2 12.1.5 — this **replaces that table**, whose vectors
> are 768 dimensions — which is what [pure-sql](../pure-sql/) reads. Run this recipe against its own
> database, or expect to rebuild the sample table afterwards.

## Expected output

The notebook walks four functions. Given patient 2 (Noah Rhodes), you should see:

| Function | Returns |
| --- | --- |
| `VECTOR_SERIALIZE` | The stored vector as readable text — `[0.016166046, -0.024523495, …]` |
| `VECTOR_DIMENSION_COUNT` | `1024` for every row |
| `VECTOR_NORM(EMBEDDING, EUCLIDEAN)` | The vector's length — useful for spotting rows that never got embedded |
| `VECTOR_DISTANCE` | The patients nearest to the one you picked, ranked |

## Concepts

### Embedding a row, not a document

A row is not prose, so it has to be turned into something an embedding model can read. The
notebook joins each patient's fields into one string, then embeds the batch:

```python
patient_vectors = embeddings.embed_documents(texts=row_combined)
```

That choice — which columns to include, and how to phrase them — is the whole design decision in
tabular search. Include a column and it influences similarity; leave it out and it cannot. Age,
gender, cholesterol, blood pressure and smoking status all go in here.

### 1024 dimensions, not 768

`multilingual-e5-large` returns 1024 floats, so the column is `VECTOR(1024, FLOAT32)`. The
dimension is dictated by the model — change the model and the column definition changes with it.
That is why the two recipes in this module cannot share a table.

### Where the vectors live

```
watsonx.ai embedding API  ──▶  1024 floats per row  ──▶  Db2 VECTOR(1024, FLOAT32)
                                                              │
                              VECTOR_DISTANCE / _NORM / _SERIALIZE / _DIMENSION_COUNT
```

Generation happens in the cloud; everything afterwards is SQL against your own database. Once the
vectors are stored, no further calls to watsonx.ai are needed to search.

### The data

20 synthetic patient records — names, ages, cholesterol levels and blood pressures generated with
[Faker](https://faker.readthedocs.io/). No real person, no clinical data.

- `patients-data.csv` — the source rows
- `patients.csv` — the same rows **with the embedding column**, written by the notebook and used
  for the bulk `IMPORT`. Ships with the recipe so you can load the table without spending
  watsonx.ai calls

---

## Appendix

### Credentials

`.env` holds `WATSONX_APIKEY` and `WATSONX_PROJECT`; it is gitignored, and `.env.example` shows
the shape. Nothing else in this recipe needs a secret — Db2 is reached as the local instance
owner through the `%sql` magic.

### Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `SQL0601N  PATIENTS already exists` | The table is there from `db2sampl` or the other recipe | Drop it first — `dbsetup.sh` does — but read the warning above before dropping the sample table |
| `VECTOR_DIMENSION_COUNT` returns 768, not 1024 | You are querying the table shipped with `SAMPLE`, not the one this notebook built | Rebuild, or point at your own database |
| Rows exist but `VECTOR_DISTANCE` returns nothing | A row whose embedding is all zeros makes cosine distance undefined and aborts the query | Check with `VECTOR_NORM` — a norm of 0 is the giveaway — and re-embed that row |
| `WATSONX_APIKEY` errors | `.env` missing or not loaded | `cp .env.example .env`, fill it in, restart the kernel |
| `%sql` is not defined | `db2.ipynb` did not download | Fetch it manually from [IBM/db2-jupyter](https://github.com/IBM/db2-jupyter) into this folder |

### Files

```
similar-patients-search.ipynb   the recipe
dbsetup.sh                      create PATIENTS and import the rows
patients-data.csv               20 synthetic patient records
patients.csv                    the same rows plus the 1024-dim embedding column
requirements.txt                pinned
.env.example                    watsonx.ai credentials template
```

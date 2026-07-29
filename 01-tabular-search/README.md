# Tabular search

[← Db2 AI Cookbook](../README.md)

> Similarity search over the rows of an ordinary table. Give Db2 a vector per row, and
> `VECTOR_DISTANCE` will rank rows by closeness — with normal SQL predicates applied in the same
> statement.

![Db2](https://img.shields.io/badge/store-Db2%2012.1.2%2B%20VECTOR-054ada)
![Status](https://img.shields.io/badge/purpose-learning%20%2F%20reference-success)

This is the simplest thing you can do with a `VECTOR` column, and the foundation the other
modules build on. The embedding here stands for a **whole row** — a patient record — rather than
a chunk of a document, and the vectors are pre-computed, so nothing distracts from the Db2 side.

```mermaid
flowchart LR
    ROW["a table row<br/>age · gender · cholesterol · BP"] --> EMB["pre-computed vector"]
    EMB --> DB[("Db2 table<br/>ordinary columns + VECTOR(768)")]
    REF["pick a reference row"] --> DB
    DB -->|"VECTOR_DISTANCE — ranked"| FILTER["+ WHERE on ordinary columns"]
    FILTER --> OUT["the most similar rows,<br/>within the filter"]
```

The point is the last two steps happening **together**. A dedicated vector store returns nearest
neighbours; answering *"similar to this row, but only where age is 35–40"* then needs a second
system and glue code. Keeping the vector in the row makes it one query.

## Recipes

| Recipe | Stack | What it shows |
|---|---|---|
| [pure-sql](pure-sql/) | `db2` CLP only — no Python, no framework | `VECTOR`, `VECTOR_DISTANCE`, `VECTOR_SERIALIZE`, `VECTOR_DIMENSION_COUNT` across seven `.sql` files, over a 20-row patient table |

## Prerequisites

Db2 **12.1.2 or later** — that is where the `VECTOR` type lands — and a database to run against.
Nothing else: no Python, no virtualenv, no models, no services. On Db2 12.1's `SAMPLE` database
the demo table already exists with its embeddings, so this module runs with zero setup.

## Where to go next

- [02-multimodal-embedding](../02-multimodal-embedding/) — produce the vectors yourself, from text and images
- [03-hybrid-search](../03-hybrid-search/) — combine vector ranking with keyword search
- [04-rag](../04-rag/) — the same `VECTOR_DISTANCE` retrieval, over document chunks, feeding a language model

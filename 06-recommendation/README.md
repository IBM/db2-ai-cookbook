# Recommendation

[← Db2 AI Cookbook](../README.md)

> "Find me something like this one — that I can actually get." Item-to-item recommendation where
> the similarity comes from a vector and the availability comes from a `WHERE` clause, both in the
> same Db2 query.

![Db2](https://img.shields.io/badge/store-Db2%2012.1.2%2B%20VECTOR-054ada)
![watsonx.ai](https://img.shields.io/badge/embeddings-watsonx.ai%20cloud-0f62fe)

Where [01-tabular-search](../01-tabular-search/) introduces row similarity on its own, this module
puts it in a retail setting, and the business constraint is the interesting part: a
recommendation nobody can buy is worthless, so store, size and stock filter the results while the
vector ranks them.

```mermaid
flowchart LR
    CAT["product catalogue<br/>brand · model · category · description"] --> TXT["join attributes into text"]
    TXT --> EMB["watsonx.ai embedding"]
    EMB --> DB[("Db2<br/>inventory columns + VECTOR")]
    PICK["the product you chose"] --> DB
    DB -->|"VECTOR_DISTANCE ranks"| FILTER["WHERE location · size · in stock"]
    FILTER --> OUT["similar products<br/>you can actually buy"]
```

## Recipes

| Recipe | Stack | What it shows |
|---|---|---|
| [shoe-search-watsonx](shoe-search-watsonx/) | Jupyter + watsonx.ai embeddings | Pick a men's size 12 running shoe in Ottawa, then find the closest match in the Toronto store's inventory — followed by a walkthrough of the vector column, the attribute-to-text step, and the `VECTOR_DISTANCE` query behind it |

## Prerequisites

Db2 **12.1.2 or later**, Python 3.12, and a watsonx.ai API key for generating embeddings. The
pre-computed vectors ship with the recipe, so you can run the search without calling watsonx.ai
at all — the key is only needed to regenerate the catalogue.

## Where to go next

- [01-tabular-search](../01-tabular-search/) — the same primitive with nothing else around it
- [03-hybrid-search](../03-hybrid-search/) — add keyword matching when the query is words rather than an item

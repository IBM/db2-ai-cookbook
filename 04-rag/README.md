# RAG

[← Db2 AI Cookbook](../README.md)

> Retrieval-augmented generation with Db2 as the vector database: parse a document, store its
> chunks and embeddings in a native `VECTOR` column, retrieve the closest ones with
> `VECTOR_DISTANCE`, and let a language model answer from those excerpts alone.

![Db2](https://img.shields.io/badge/store-Db2%2012.1.2%2B%20VECTOR-054ada)
![Python](https://img.shields.io/badge/Python-3-blue)
![Status](https://img.shields.io/badge/purpose-learning%20%2F%20reference-success)

Where the [multimodal embedding](../02-multimodal-embedding/) module stops at *producing and
storing* a vector, this module closes the loop: retrieve the right vectors for a question, and
ground an answer in them.

```mermaid
flowchart LR
    DOC["PDF / DOCX / HTML<br/>or a web article"] --> PARSE["parse + chunk"]
    PARSE --> EMB["embed each chunk"]
    EMB --> DB[("Db2 VECTOR<br/>text + metadata + vector")]
    Q["question"] --> QEMB["embed the question"]
    QEMB --> DB
    DB -->|"VECTOR_DISTANCE — top k"| PROMPT["prompt with excerpts"]
    PROMPT --> LLM["language model"]
    LLM --> ANS["answer, with citations"]
```

## Recipes

| Recipe | Framework | Source document | Chunking | Models | Form |
|---|---|---|---|---|---|
| [haystack-local-models](haystack-local-models/) | [Haystack](https://haystack.deepset.ai/) pipelines | a **PDF**, parsed by [Docling](https://github.com/docling-project/docling) | `HybridChunker`, on section boundaries | via [llama.cpp](https://github.com/ggml-org/llama.cpp), OpenAI-compatible API · 384-d | Python scripts |
| [langchain-local-models](langchain-local-models/) | [LangChain](https://python.langchain.com/) + the `langchain-db2` connector | a **web article**, extracted by [trafilatura](https://trafilatura.readthedocs.io/) | spaCy sentences, 200 words / 50 overlap | Granite 30M + Qwen2.5 3B via `LlamaCpp` · 384-d | Jupyter notebook |
| [plain-python-watsonx](plain-python-watsonx/) | **none** — plain Python over raw SQL | a **blog post**, extracted by [trafilatura](https://trafilatura.readthedocs.io/) | spaCy, sentence-aware with overlap | Granite 30M local; answers from **hosted watsonx.ai** | Jupyter notebook |
| [autoai-watsonx](autoai-watsonx/) | **watsonx.ai AutoAI RAG** chooses the pattern | **Db2 ML articles**, loaded from COS | whatever AutoAI selects — that is the point | selected by AutoAI, hosted on watsonx.ai · 1024-d | Jupyter notebook |

The first two run entirely on your own machine — no API keys, no cloud, no per-call cost. The
third keeps embeddings local but calls a hosted model to write the answer. The fourth is fully
hosted and additionally needs an IBM Cloud Object Storage bucket, but it is the only one that
**measures** its retrieval quality rather than assuming it.

### Which one should I use?

| If you want… | Use |
|---|---|
| A command-line walkthrough you can run step by step, over your own PDFs, with a test plan | **haystack-local-models** |
| To read the whole pipeline top to bottom in one notebook — with saved outputs, so it makes sense before you run anything — over web articles | **langchain-local-models** |
| To see what a framework is actually doing for you, written out longhand — or to use a hosted LLM instead of running one | **plain-python-watsonx** |

All three solve the same problem with different tools, so reading two of them is the fastest way
to see which parts of a RAG pipeline are essential and which are framework flavour. Reading
**plain-python-watsonx** against either of the others is the sharpest version of that comparison:
same ingestion, same chunker, same embedding model, same database — one with a framework, one
without.

## Prerequisites

**Db2 ≥ 12.1.2.** The native `VECTOR` type and `VECTOR_DISTANCE` were introduced in 12.1.2; on
anything older these recipes cannot work, because the table they create has a `VECTOR` column.
Check with `db2level`.

Each recipe's README covers the rest — model downloads, server setup, and its own `.env`.

## Quick start

- **[haystack-local-models →](haystack-local-models/README.md#full-setup-on-a-fresh-rhel-box)** — takes a bare Red Hat machine to answered questions, one command at a time.
- **[langchain-local-models →](langchain-local-models/README.md)** — download two GGUF models, point `.env` at Db2, open the notebook.
- **[plain-python-watsonx →](plain-python-watsonx/README.md)** — run `setup.sh`, add watsonx credentials to `.env`, open the notebook.

## Module layout

```
04-rag/
├── haystack-local-models/     # Haystack + Docling, PDF in, Python scripts
├── langchain-local-models/    # LangChain + trafilatura, web article in, notebook
├── plain-python-watsonx/      # no framework, raw SQL, hosted watsonx generation
└── README.md                  # you are here
```

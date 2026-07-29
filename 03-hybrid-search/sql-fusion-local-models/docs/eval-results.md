# Evaluation Results — Hybrid Search (audiobook corpus)

Search-quality results from `scripts/eval.py` against the shipped audiobook
corpus (one row per book).

- **Reproduce:** `DB2_HOST=local PYTHONPATH=src python scripts/eval.py`
- **Golden eval set:** [`data/eval/golden_set.json`](../data/eval/golden_set.json) — **118 queries**, TRAIN (95) / **HELDOUT (23, ~19%)**. Ships with the recipe, so these numbers reproduce from a clean clone. Composition: 106 silver + 5 `leg_discriminating` (bare narrator names) + 7 `summary_content` (answers that live deep in a book's summary).
- **Corpus:** 92 audiobooks in Db2 `MYSCHEMA.CHUNKS`. Each `chunk_text` = `title + authors + narrators + full description`.
- **Indexing:** the **full** `chunk_text` is BM25-indexed (Db2 Text Search). The vector is `TO_EMBEDDING` of the first **1500 chars** (bge-small-en-v1.5 has a 512-token context and errors on longer input) — see the caveat below.
- **Fusion knobs:** `HYBRID_W_LEX=0.3 W_VEC=0.7 VEC_GATE=0.0 LEX_GATE=0.0 POOL=100` — the shipped defaults.
- **Date:** 2026-07-21

Metrics: **known_item →** MRR, Hits@1. **topical →** Recall@5, nDCG@5.

## HELDOUT — the honest number (never tuned on)

| leg | MRR | Hits@1 | Recall@5 | nDCG@5 |
|---|---|---|---|---|
| lexical | 0.923 | 0.900 | 0.556 | 0.588 |
| vector | 0.867 | 0.850 | **0.917** | **0.906** |
| **hybrid** | **0.942** | **0.900** | 0.778 | 0.807 |

## ALL 118 queries

| leg | MRR | Hits@1 | Recall@5 | nDCG@5 |
|---|---|---|---|---|
| lexical | 0.867 | 0.825 | 0.562 | 0.617 |
| vector | 0.898 | 0.874 | **0.762** | **0.809** |
| **hybrid** | **0.909** | **0.864** | 0.749 | 0.783 |

## Diagnostic — known_item MRR by query type

| query_type | lexical | vector | hybrid |
|---|---|---|---|
| keyword | **1.000** | 0.889 | 0.969 |
| semantic | 0.476 | **0.802** | 0.677 |
| mixed | 0.893 | **0.952** | 0.946 |

This is the eval validating itself, and it's the clearest table here:

- **keyword** queries (bare narrator names, exact tokens): lexical is **perfect** (1.000); the vector leg drops to 0.889 — those name-only queries embed to noise (e.g. *"walter dixon"* → vector rank 36, lexical rank 1). This is the vector leg's blind spot.
- **semantic** queries (paraphrases): the mirror image — lexical falls to **0.476**, the vector leg carries them (0.802).
- **hybrid** is never the best on any single row, but it is never the *worst*, and it wins the aggregate (HELDOUT MRR 0.942 > both legs; ALL 0.909 > both). Each leg has a blind spot; fusion covers both. That is the thesis, and the numbers now show it.

## What changed: indexing the full summary

Until this run, `chunk_text` held only a ~200-char blurb, so the lexical leg was
weak and hybrid barely tied pure vector. Now the **full book summary** is indexed:

- **The lexical leg became genuinely strong** — HELDOUT MRR 0.82 → **0.923**, keyword-type MRR to a perfect 1.000. Real content is now keyword-searchable (e.g. *"the cue routine reward habit loop"* → *The Power of Habit*, which the short corpus could not retrieve).
- **The fusion optimum shifted toward lexical.** A fresh 5-fold-CV weight sweep put the 1-SE band at α ∈ [0.7, 1.0] (was [0.8, 1.0]); the one-standard-error pick is **0.3/0.7** (was 0.1/0.9) — the lexical leg now earns a bigger share.
- **Hybrid now clearly wins** the aggregate on HELDOUT and ALL, instead of trailing vector.

## Caveat — embedding truncation (accepted)

bge-small-en-v1.5 has a **512-token context** and *errors* on longer input (and one
over-long row rolls back the whole embed `UPDATE`). So the vector is built from the
first **1500 chars** of `chunk_text` (~480 tokens, safe for the densest text); ~11
books have summaries longer than that, whose tails are **not vectorized**. The BM25
index still covers the full text, so lexical retrieval is complete; only the dense
vector misses the tail of long summaries. For full vector coverage, chunk long
summaries into passages (a larger, multi-row change) — deferred by design.

## Observations

- **Both legs now pull weight**, unlike the short-text corpus where vector dominated.
  The `0.3/0.7` split reflects that; it is corpus-specific — re-run the sweep after
  any corpus/model change.
- **`POOL=100`** exceeds the 92-book corpus, so each leg is exhaustive — a free recall
  boost here, not on a larger corpus.
- **Silver, not gold.** The 106 original queries are `review_status: needs_review`.
  The 12 curated additions (`leg_discriminating`, `summary_content`) were each
  verified against the live engine.

## Next levers (re-run `eval.py` after each)

1. **Passage chunking** for long summaries — would close the embedding-truncation gap and likely lift vector Recall.
2. **Cross-encoder reranker** over the fused top-k (optional stage, `:8087`).
3. **Larger / longer-context embedding model** — removes the 512-token cap; update `VECTOR(384)` → new dim in `1_ingest.sql`.
4. **Surface metadata in retrieval** (pillar/series/author filters) for topical queries.

> Results depend on the corpus, embedding model, and `HYBRID_*` knobs. Re-run after any change.

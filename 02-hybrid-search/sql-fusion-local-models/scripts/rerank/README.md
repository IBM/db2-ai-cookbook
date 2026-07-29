# Post-fusion cross-encoder reranking

An **app-layer** stage on top of Db2 hybrid fusion. Db2 stays responsible for
retrieval + fusion; after it returns the fused top-N, this stage re-scores those
candidates with a local **cross-encoder** and cuts to the top-K shown in the Search
tab. Off by default — it ships only because the A/B on the golden set justifies it.

## How it works

```
UI query → Db2 (lexical + vector → gated fusion) → top-N candidates
         → rerank stage: one batched POST to the cross-encoder → reorder → top-K → UI
```

- **Model**: `bge-reranker-v2-m3` (Q4_K_M GGUF), the best CPU cross-encoder in the spec.
- **Server**: its own `llama-server --reranking` on **:8087** — separate from the
  embedding server (`--reranking` and `--embeddings` are mutually exclusive at launch).
  Start it with `scripts/rerank/start_rerank_server.sh`.
- **Stage**: `src/hybrid_search/rerank.py` — one batched request per query, an LRU score
  cache keyed by (normalized query, candidate id), and a hard timeout → **fusion-order
  fallback** (search never fails because rerank did). Endpoint path is auto-detected
  (`/v1/reranking` on this build).
- **Wiring**: `ui/build_fixtures.py:responses_for(..., rerank=)` on the **hybrid** response
  only; `/api/search` passes `RERANK_ON`. The Demo tab never reranks. With the flag off the
  output is byte-for-byte identical to before (verified).

Config (`.env`): `RERANK_ON`, `RERANK_URL`, `RERANK_MODEL`, `RERANK_N`, `RERANK_K`,
`RERANK_TIMEOUT`, `RERANK_DOC_CHARS`, `RERANK_PATH`.

## A/B results (golden set, 112 queries, bge-reranker-v2-m3)

All arms start from the **same** Db2 fusion pool; rerank only reorders it.

```
MRR       | keyword | semantic | mixed | topical | overall
----------|---------|----------|-------|---------|--------
FUSION    |  0.988  |  0.667   | 0.946 |  0.898  |  0.915
RERANK@20 |  1.000  |  0.688   | 0.946 |  0.938  |  0.929   ← best
RERANK@50 |  1.000  |  0.666   | 0.946 |  0.922  |  0.923

Hits@1    | keyword | semantic | mixed | topical | overall
FUSION    |  0.977  |  0.562   | 0.892 |  0.875  |  0.875
RERANK@20 |  1.000  |  0.562   | 0.892 |  0.875  |  0.884
RERANK@50 |  1.000  |  0.500   | 0.892 |  0.875  |  0.875

Recall@5  | keyword | semantic | mixed | topical | overall
FUSION    |  1.000  |  0.812   | 1.000 |  0.615  |  0.918
RERANK@20 |  1.000  |  0.812   | 1.000 |  0.731  |  0.935
RERANK@50 |  1.000  |  0.875   | 1.000 |  0.678  |  0.936

nDCG@5    | keyword | semantic | mixed | topical | overall
FUSION    |  0.991  |  0.696   | 0.960 |  0.687  |  0.895
RERANK@20 |  1.000  |  0.712   | 0.960 |  0.790  |  0.916   ← best
RERANK@50 |  1.000  |  0.716   | 0.960 |  0.751  |  0.911
```

**Candidate-pool Recall@N** (the ceiling — gold must be *in* the pool to rerank):
`pool@20 = 0.977`, `pool@50 = 0.997` overall (gaps: semantic pool@20 0.938, topical
pool@20 0.898). So fusion@20 already contains almost all gold; the lift is reranking
quality, not deeper pools.

**Added latency** (mean/query, cold cache): RERANK@20 **964 ms**, RERANK@50 2214 ms.
**Fallbacks**: 0. (Warm-cache repeats are ~0 ms.)

## Recommendation

**Enable at N=20, K=3** (`RERANK_N=20` is set; flip `RERANK_ON=1`). The reranker earns
its place:
- Lifts overall MRR +0.014, nDCG +0.021, Recall@5 +0.017 — **no regression on any group**.
- Biggest wins where a cross-encoder should help: **topical** (MRR +0.040, Recall@5
  +0.116, nDCG +0.103) and it even **perfects keyword** (0.988→1.000). Semantic nudges up.
- **N=20 beats N=50**: the deeper pool adds distractors the cross-encoder occasionally
  ranks above a borderline gold (semantic Hits@1 drops at @50), for 2.3× the latency and
  no quality gain. Since pool@20 is already 0.977, going deeper buys almost nothing.
- Cost is ~1 s added latency per (cold) query — a UX tradeoff, so it's left as a flag.

Left **off by default** pending your call on the latency budget. Turn it on:
```bash
scripts/rerank/start_rerank_server.sh        # reranker on :8087
# set RERANK_ON=1 in .env, then ./ui/run.sh --live
```

## Reproduce

```bash
scripts/rerank/start_rerank_server.sh
PYTHONPATH=src:scripts/query-understanding DB2_HOST=local RERANK_URL=http://127.0.0.1:8087 \
  .venv/bin/python scripts/rerank/rerank_eval.py
```
Unit tests (no server/Db2 needed): `PYTHONPATH=src .venv/bin/python tests/test_rerank.py`

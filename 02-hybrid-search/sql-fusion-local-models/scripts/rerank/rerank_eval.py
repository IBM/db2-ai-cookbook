#!/usr/bin/env python3
"""A/B/C evaluation of the post-fusion cross-encoder reranker on the golden set.

Arms (all start from the same Db2 fusion candidate pool):
  FUSION     — fusion order, no rerank (baseline)
  RERANK@20  — rerank the fusion top-20, re-order, evaluate
  RERANK@50  — rerank the fusion top-50, re-order, evaluate

Per query_type reports MRR / Hits@1 / Recall@5 / nDCG@5 and the added rerank latency.
Also reports candidate-pool Recall@N (was the gold answer even in the fusion top-N) —
the reranker can only reorder what fusion already found, so a miss there is a retrieval
problem, not a rerank one, and the table must attribute it correctly.

Prereq: reranker server up (llama-server --reranking on RERANK_URL), Db2 up.
Run: PYTHONPATH=src:scripts/query-understanding DB2_HOST=local \
     RERANK_URL=http://127.0.0.1:8087 .venv/bin/python scripts/rerank/rerank_eval.py
"""
import glob
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))
import ibm_db
from hybrid_search import core as h
from hybrid_search import evalset
from hybrid_search import understanding as qu
from hybrid_search import rerank as rr

N_MAX, N1, N2, K = 50, 20, 50, 5


def load_golden():
    # was: glob(~/out/eval/...)[-1] -> bare IndexError on a fresh clone
    path = evalset.resolve()
    return path, json.load(open(path))


def rrank(ranked, gold):
    for i, c in enumerate(ranked, 1):
        if c in gold:
            return 1.0 / i
    return 0.0

def hit1(ranked, gold):
    return 1.0 if ranked and ranked[0] in gold else 0.0

def recall_at(ranked, gold, k):
    return len(set(ranked[:k]) & gold) / len(gold) if gold else 0.0

def ndcg_at(ranked, gold, k):
    dcg = sum(1.0 / math.log2(i + 1) for i, c in enumerate(ranked[:k], 1) if c in gold)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(gold), k) + 1))
    return dcg / idcg if idcg else 0.0

def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def main():
    path, golden = load_golden()
    conn = h.connect()

    # warm the model so the first query isn't cold-penalized in the latency numbers
    rr.clear_cache()
    rr.rerank("warmup query about habits", [(0, "a book about building better habits")], n=1, k=1)

    rows = []   # per-query records
    for it in golden:
        q = it["query"]; gold = set(it["gold_ids"])
        grp = "topical" if it["query_class"] == "topical" else it["query_type"]
        lex_q = qu.lexical_of(conn, q)
        fusion = h.hybrid_split(conn, lex_q, q, N_MAX)
        fusion_ids = [cid for cid, _ in fusion]
        pairs = [(cid, h.snippet(conn, cid, rr.RERANK_DOC_CHARS)) for cid, _ in fusion]

        # rerank arms (patch the query used by rerank via a tiny closure per call)
        def do(n):
            rr.clear_cache()
            reordered, meta = rr.rerank(q, pairs[:n], n=n, k=n)
            ids = [cid for cid, _t, _s in reordered] + fusion_ids[n:]
            return ids, meta["latency_ms"], meta["fell_back"]

        r20_ids, lat20, fb20 = do(N1)
        r50_ids, lat50, fb50 = do(N2)

        rows.append({
            "grp": grp, "gold": gold,
            "FUSION":     fusion_ids,
            "RERANK@20":  r20_ids,
            "RERANK@50":  r50_ids,
            "lat": {"FUSION": 0.0, "RERANK@20": lat20, "RERANK@50": lat50},
            "fb": fb20 + fb50,
            "pool@20": recall_at(fusion_ids, gold, N1),
            "pool@50": recall_at(fusion_ids, gold, N2),
        })
        sys.stderr.write(".")
    sys.stderr.write("\n")
    ibm_db.close(conn)

    arms = ["FUSION", "RERANK@20", "RERANK@50"]
    groups = ["keyword", "semantic", "mixed", "topical"]

    def cell(arm, grp, fn):
        return mean(fn(r[arm], r["gold"]) for r in rows if r["grp"] == grp)

    print(f"\nGolden set: {os.path.basename(path)}   ·   post-fusion reranker A/B  "
          f"(reranker={rr.RERANK_MODEL})\n")
    for metric_name, fn in (("MRR", rrank), ("Hits@1", hit1),
                            (f"Recall@{K}", lambda r, g: recall_at(r, g, K)),
                            (f"nDCG@{K}", lambda r, g: ndcg_at(r, g, K))):
        hdr = f"{metric_name:9} | " + " | ".join(f"{g:>9}" for g in groups) + " |   overall"
        print(hdr); print("-" * len(hdr))
        for arm in arms:
            cells = " | ".join(f"{cell(arm, g, fn):9.3f}" for g in groups)
            overall = mean(fn(r[arm], r["gold"]) for r in rows)
            print(f"{arm:9} | {cells} | {overall:9.3f}")
        print()

    # candidate-pool recall (retrieval ceiling — reranker can't beat this)
    print("Candidate-pool Recall@N (the ceiling — gold must be IN the pool to rerank):")
    for grp in groups:
        p20 = mean(r["pool@20"] for r in rows if r["grp"] == grp)
        p50 = mean(r["pool@50"] for r in rows if r["grp"] == grp)
        print(f"  {grp:9}  pool@20 {p20:.3f}   pool@50 {p50:.3f}")
    print(f"  {'overall':9}  pool@20 {mean(r['pool@20'] for r in rows):.3f}   "
          f"pool@50 {mean(r['pool@50'] for r in rows):.3f}")

    # cost
    print("\nAdded latency (mean per query, cold cache) & fallbacks:")
    for arm in ("RERANK@20", "RERANK@50"):
        print(f"  {arm:9}  {mean(r['lat'][arm] for r in rows):7.0f} ms")
    print(f"  fallbacks (reranker errored -> fusion order): {sum(r['fb'] for r in rows)}")

    # verdict
    print("\nVERDICT — RERANK@50 vs FUSION (per group, MRR):")
    for grp in groups:
        a = cell("FUSION", grp, rrank); c = cell("RERANK@50", grp, rrank)
        tag = "helps ✓" if c > a + 1e-9 else ("no change" if abs(c - a) < 1e-9 else "REGRESSION ✗")
        print(f"  {grp:9}: {c:.3f} vs {a:.3f}  ->  {tag}")


if __name__ == "__main__":
    main()

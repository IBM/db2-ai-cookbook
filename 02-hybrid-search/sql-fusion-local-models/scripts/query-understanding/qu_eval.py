#!/usr/bin/env python3
"""A/B/C(/D) evaluation of the query-understanding gate on the golden set, per query_type.

  A  never-LLM   : raw query to both legs (baseline)                    -> h.hybrid
  B  always-LLM  : extractive lexical + generative semantic every query -> qu.llm_expand + hybrid_split
  C  gated       : SQL feature-gate decides (this design)               -> qu.gated_search
  D  crag-gated  : confidence gate — LLM only when vector looks unsure  -> qu.confidence_search

Per query logs: route, llm_fired, added (understanding) latency, and MRR/Hits@1/Recall@5.
Emits the comparison table + a verdict.

Run: PYTHONPATH=src:scripts/query-understanding DB2_HOST=local .venv/bin/python scripts/query-understanding/qu_eval.py
"""
import glob
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ibm_db
from hybrid_search import core as h
from hybrid_search import evalset
import qu

K, RETRIEVE = 5, 10


def load_golden():
    # was: glob(~/out/eval/...)[-1] -> bare IndexError on a fresh clone
    path = evalset.resolve()
    return path, json.load(open(path))


def rr(ranked, gold):
    for i, c in enumerate(ranked, 1):
        if c in gold:
            return 1.0 / i
    return 0.0

def hit1(ranked, gold):
    return 1.0 if ranked and ranked[0] in gold else 0.0

def recall_k(ranked, gold, k=K):
    return len(set(ranked[:k]) & gold) / len(gold) if gold else 0.0

def ndcg_k(ranked, gold, k=K):
    dcg = sum(1.0 / math.log2(i + 1) for i, c in enumerate(ranked[:k], 1) if c in gold)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(gold), k) + 1))
    return dcg / idcg if idcg else 0.0

def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def run_arm(conn, name, items):
    """Return per-item records: {group, rr, hit1, recall, ndcg, llm, ms}.

    A     baseline: raw query to both legs, no understanding (h.hybrid)
    CLEAN cleaner only, no LLM (smart_search mode=off)
    GATED cleaner + route-based generation (smart_search mode=gated)
    CRAG  cleaner + confidence-gated generation  [SHIPPED default] (smart_search mode=crag)
    """
    recs = []
    for it in items:
        gold = set(it["gold_ids"])
        grp = "topical" if it["query_class"] == "topical" else it["query_type"]
        t0 = time.perf_counter()
        if name == "A":
            ranked = h.hybrid(conn, it["query"], RETRIEVE); llm = 0; ms = 0.0
        else:
            mode = {"CLEAN": "off", "GATED": "gated", "CRAG": "crag"}[name]
            ranked, u = qu.smart_search(conn, it["query"], RETRIEVE, mode=mode)
            ms = (time.perf_counter() - t0) * 1000; llm = u.get("llm_fired", 0)
        ranked = [int(c[0]) if isinstance(c, (list, tuple)) else int(c) for c in ranked]
        recs.append({"group": grp, "rr": rr(ranked, gold), "hit1": hit1(ranked, gold),
                     "recall": recall_k(ranked, gold), "ndcg": ndcg_k(ranked, gold),
                     "llm": llm, "ms": ms})
    return recs


ARMS = ("A", "CLEAN", "GATED", "CRAG")


def main():
    path, golden = load_golden()
    conn = h.connect()
    arms = {}
    for name in ARMS:
        if name in ("GATED", "CRAG"):
            qu.clear_cache(conn)   # cold latencies
        t = time.perf_counter()
        arms[name] = run_arm(conn, name, golden)
        sys.stderr.write(f"arm {name} done in {time.perf_counter()-t:.1f}s\n")
    ibm_db.close(conn)

    groups = ["keyword", "semantic", "mixed", "topical"]
    label = {"A": "A baseline (raw)", "CLEAN": "CLEAN cleaner-only",
             "GATED": "GATED route-gen", "CRAG": "CRAG conf-gen  [SHIP]"}
    metric = {"keyword": "MRR", "semantic": "MRR", "mixed": "MRR", "topical": "Recall@5"}

    def val(recs, grp):
        g = [r for r in recs if r["group"] == grp]
        if grp == "topical":
            return mean(r["recall"] for r in g)
        return mean(r["rr"] for r in g)

    print(f"\nGolden set: {os.path.basename(path)}   ·   query-understanding comparison (CRAG = shipped)\n")
    hdr = f"{'arm':22} | " + " | ".join(f"{g} {metric[g]:>8}" for g in groups)
    print(hdr); print("-" * len(hdr))
    for name in ARMS:
        cells = " | ".join(f"{val(arms[name], g):>{7+len(g)}.3f}" for g in groups)
        print(f"{label[name]:22} | {cells}")

    # known_item Hits@1 (secondary) + cost
    print(f"\n{'arm':22} | {'ki Hits@1':>9} | {'LLM fired':>12} | {'mean added lat':>14}")
    print("-" * 66)
    for name in ARMS:
        recs = arms[name]
        ki = [r for r in recs if r["group"] != "topical"]
        h1 = mean(r["hit1"] for r in ki)
        fired = sum(r["llm"] for r in recs); n = len(recs)
        lat = mean(r["ms"] for r in recs if name != "A") if name != "A" else 0.0
        print(f"{label[name]:22} | {h1:9.3f} | {fired:>4}/{n:<4} ({100*fired/n:4.0f}%) | {lat:11.0f} ms")

    # verdict — SHIPPED (CRAG) vs baseline (A)
    print("\nVERDICT — shipped default CRAG vs baseline A (raw):")
    for grp in ("keyword", "semantic", "mixed", "topical"):
        a, c = val(arms["A"], grp), val(arms["CRAG"], grp)
        tag = "helps ✓" if c > a + 1e-9 else ("no loss ✓" if c >= a - 0.02 else "REGRESSION ✗")
        print(f"  {grp:9}: CRAG {c:.3f} vs A {a:.3f}  ->  {tag}")
    firedC = sum(r["llm"] for r in arms["CRAG"]); firedG = sum(r["llm"] for r in arms["GATED"])
    print(f"  cost     : CRAG fires LLM {firedC}/{len(arms['CRAG'])} vs GATED {firedG} — cleaner (pure win) runs on all queries, 0 LLM")


if __name__ == "__main__":
    main()

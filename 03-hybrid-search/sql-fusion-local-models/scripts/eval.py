#!/usr/bin/env python3
"""Score retrieval quality against the golden eval set, per leg (lexical / vector /
hybrid) and per query class:

  known_item (one correct book)  -> MRR, Hits@1
  topical    (many correct books) -> Recall@K, nDCG@K

Numbers are reported for the HELDOUT slice (the honest signal — never tune on it),
TRAIN, and ALL, plus a per-query-type diagnostic (keyword should favor the lexical
leg, semantic the vector leg, mixed the fusion).

Golden set: JSON array of items with gold_ids referencing the corpus `id`
(= table chunk_id). Resolved from, in order: $GOLDEN_SET, argv[1], the newest
data/eval/golden_set.json (shipped). If data/eval/gold_core.template.json has a
non-empty my_memory_queries, those are merged in.

Run:  DB2_HOST=local PYTHONPATH=src python scripts/eval.py
      (or `pip install -e .` first, then drop PYTHONPATH)
"""
import glob
import json
import math
import os
import sys

import ibm_db
from hybrid_search import core as h
from hybrid_search import evalset

K = 5          # cutoff for Recall@K / nDCG@K (topical)
RETRIEVE = 10  # depth pulled from each leg (MRR sees ranks up to here)


# ---------- load ----------
def resolve_path():
    # Ships at data/eval/golden_set.json; $GOLDEN_SET and argv still override.
    return evalset.resolve(sys.argv[1] if len(sys.argv) > 1 else None)


def load_items():
    path = resolve_path()
    items = json.load(open(path))
    # merge personal-memory gold queries, if the user has filled them in
    tmpl = evalset.template_path()
    merged = 0
    if tmpl:
        mine = json.load(open(tmpl)).get("my_memory_queries", [])
        for m in mine:
            m.setdefault("split", "holdout")   # personal gold defaults to heldout
            items.append(m)
            merged += 1
    for it in items:
        it["gold_ids"] = [int(g) for g in it["gold_ids"]]
        it.setdefault("split", "train")
    return path, items, merged


# ---------- metrics ----------
def rr(ranked, gold):
    for i, cid in enumerate(ranked, start=1):
        if cid in gold:
            return 1.0 / i
    return 0.0

def hit1(ranked, gold):
    return 1.0 if ranked and ranked[0] in gold else 0.0

def recall_at_k(ranked, gold, k=K):
    return len(set(ranked[:k]) & gold) / len(gold) if gold else 0.0

def ndcg_at_k(ranked, gold, k=K):
    dcg = sum(1.0 / math.log2(i + 1) for i, cid in enumerate(ranked[:k], start=1) if cid in gold)
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(gold), k) + 1))
    return dcg / ideal if ideal else 0.0

def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


# ---------- run ----------
def main():
    path, items, merged = load_items()
    legs = {"lexical": h.lexical, "vector": h.vector, "hybrid": h.hybrid}

    conn = h.connect()
    # ranked[(leg, item_id)] = [chunk_id, ...]
    ranked = {}
    for it in items:
        for name, fn in legs.items():
            ranked[(name, it["id"])] = [int(cid) for cid, _ in fn(conn, it["query"], RETRIEVE)]
    ibm_db.close(conn)

    def block(subset, title):
        rows = [it for it in items if subset(it)]
        ki = [it for it in rows if it["query_class"] == "known_item"]
        tp = [it for it in rows if it["query_class"] == "topical"]
        print(f"\n{title}  (known_item={len(ki)}, topical={len(tp)})")
        print(f"  {'leg':8} | {'MRR':>6} {'Hits@1':>7} | {'Recall@'+str(K):>9} {'nDCG@'+str(K):>7}")
        print(f"  {'-'*8}-+-{'-'*6}-{'-'*7}-+-{'-'*9}-{'-'*7}")
        for name in legs:
            g = lambda it: set(it["gold_ids"])
            mrr = mean(rr(ranked[(name, it["id"])], g(it)) for it in ki)
            h1  = mean(hit1(ranked[(name, it["id"])], g(it)) for it in ki)
            rec = mean(recall_at_k(ranked[(name, it["id"])], g(it)) for it in tp)
            ndg = mean(ndcg_at_k(ranked[(name, it["id"])], g(it)) for it in tp)
            print(f"  {name:8} | {mrr:6.3f} {h1:7.3f} | {rec:9.3f} {ndg:7.3f}")

    print(f"\nGolden set: {os.path.basename(path)}  ·  {len(items)} queries"
          + (f"  (+{merged} personal-memory)" if merged else ""))
    block(lambda it: it["split"] == "holdout", "HELDOUT  ← the honest number (never tuned on)")
    block(lambda it: it["split"] == "train",   "TRAIN")
    block(lambda it: True,                      "ALL")

    # diagnostic: known_item MRR by query_type — does each leg win where it should?
    print("\nDIAGNOSTIC — known_item MRR by query_type (expect keyword→lexical, semantic→vector, mixed→hybrid)")
    types = ["keyword", "semantic", "mixed"]
    print(f"  {'type':9} | " + " ".join(f"{n:>8}" for n in legs))
    print(f"  {'-'*9}-+-" + "-".join("-"*8 for _ in legs))
    for t in types:
        ki = [it for it in items if it["query_class"] == "known_item" and it["query_type"] == t]
        cells = []
        for name in legs:
            cells.append(f"{mean(rr(ranked[(name, it['id'])], set(it['gold_ids'])) for it in ki):8.3f}")
        print(f"  {t:9} | " + " ".join(cells))
    print()


if __name__ == "__main__":
    main()

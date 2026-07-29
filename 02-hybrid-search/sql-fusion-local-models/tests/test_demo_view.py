#!/usr/bin/env python3
"""Phase-2 quality gate for the demo view's outcome-translation (the highest-risk
new code). Deterministic: pure logic over synthetic + frozen fixtures, no Db2.
An optional live smoke runs only if Db2 is reachable.

Run:  PYTHONPATH=src python tests/test_demo_view.py
Exit code 0 = all green; non-zero prints the exact failing check.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "ui"))
import demo_view as dv  # noqa: E402

PASS, FAIL = [], []
def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + ("" if cond else f"  << {detail}"))

LOOKUP = {75: {"title": "The Psychology of Money", "author": "Morgan Housel"},
          21: {"title": "The Total Money Makeover", "author": "Dave Ramsey"},
          97: {"title": "Hunting Adeline", "author": "H. D. Carlton"}}

def row(rank, cid, gold, score=0.5, stype="cosine", **extra):
    return dict(rank=rank, chunk_id=cid, snippet="s", text=f"Book{cid} by Author{cid}. blah.",
                score=score, score_type=stype, is_gold=gold, **extra)

def resp(gold_ids, results, k=5):
    gr = next((r["rank"] for r in results if r["is_gold"]), None)
    return {"query": "q", "mode": "vector", "k": k,
            "gold_chunk_ids": sorted(gold_ids), "gold_rank": gr, "results": results}

# ---------------- B. outcome-translation unit tests (table-driven) ----------------
print("\nB. Outcome-translation (every branch):")
# gold within top k -> found
r = dv.verdict_for(resp([75], [row(1, 21, False), row(2, 75, True)]), LOOKUP)
check("gold in top k -> 'found'", r["verdict"] == dv.VERDICT_FOUND, r)
check("found shows the GOLD item, not the top row", r["shown"]["chunk_id"] == 75, r["shown"])
check("found labels via id lookup (title/author)", r["shown"]["title"] == "The Psychology of Money", r["shown"])
# gold absent + non-gold top -> wrong, shown == top result
r = dv.verdict_for(resp([75], [row(1, 21, False), row(2, 30, False)]), LOOKUP)
check("gold absent + results -> 'wrong'", r["verdict"] == dv.VERDICT_WRONG, r)
check("wrong shows the TOP (confidently wrong) result", r["shown"]["chunk_id"] == 21, r["shown"])
# empty -> nothing
r = dv.verdict_for(resp([75], []), LOOKUP)
check("empty results -> 'nothing'", r["verdict"] == dv.VERDICT_NOTHING and r["shown"] is None, r)
# boundary: gold exactly at rank k (in) vs k+1 (out)
kk = 5
inb = resp([9], [row(i, i, i == kk) for i in range(1, kk + 1)], k=kk)   # gold at rank k
outb = {"query": "q", "mode": "v", "k": kk, "gold_chunk_ids": [99], "gold_rank": None,
        "results": [row(i, i, False) for i in range(1, kk + 1)]}         # gold would be k+1 -> absent
check("gold exactly at rank k -> 'found'", dv.verdict_for(inb, LOOKUP)["verdict"] == dv.VERDICT_FOUND)
check("gold at rank k+1 (absent) -> 'wrong'", dv.verdict_for(outb, LOOKUP)["verdict"] == dv.VERDICT_WRONG)

# ---------------- A. contract / shape (fixture-based) ----------------
print("\nA. Contract / shape:")
lookup_path = os.path.join(REPO, "data", "corpus.csv")
book_lookup = dv.load_book_lookup(lookup_path) if os.path.exists(lookup_path) else LOOKUP
fx_path = os.path.join(REPO, "ui", "static", "demo_fixtures.json")
FX = json.load(open(fx_path)) if os.path.exists(fx_path) else None
check("demo_fixtures.json exists (run ui/build_demo.py)", FX is not None, fx_path)
if FX:
    for qid, vm in FX["view_models"].items():
        strat = vm["strategies"]
        check(f"q{qid}: has all 3 strategies", set(strat) == set(dv.STRATS), list(strat))
        for s in dv.STRATS:
            st = strat[s]
            ok = "verdict" in st and "gold_rank" in st and isinstance(st.get("results"), list)
            check(f"q{qid}/{s}: verdict + gold_rank + results list", ok, st.keys())
            for rr in st["results"]:
                good = all(kk in rr for kk in ("rank", "chunk_id", "is_gold", "score", "title"))
                check(f"q{qid}/{s}: row has rank/is_gold/score/title", good, rr)
                break  # one representative row per strategy is enough for the contract
# edge inputs (synthetic): empty query response, gold-outside-topk, zero-results strategy
check("edge: zero-results strategy -> 'nothing'",
      dv.verdict_for({"results": [], "gold_rank": None, "gold_chunk_ids": [1]}, LOOKUP)["verdict"] == "nothing")
check("edge: gold outside top k -> 'wrong' (non-empty)",
      dv.verdict_for({"results": [row(1, 2, False)], "gold_rank": None, "gold_chunk_ids": [1]}, LOOKUP)["verdict"] == "wrong")

# ---------------- C. ground-truth / honesty ----------------
print("\nC. Ground-truth / honesty:")
# verdict_for is pure: same input -> same output; and NO per-query hardcoding in the module source
src = open(os.path.join(REPO, "ui", "demo_view.py")).read()
deck = json.load(open(os.path.join(REPO, "ui", "demo_queries.json")))
q_leak = [d["query"] for d in deck if d["query"].lower() in src.lower()]
check("no deck query strings hardcoded in demo_view.py", not q_leak, q_leak)
title_leak = [book_lookup[g]["title"] for d in deck for g in d["gold_chunk_ids"]
              if g in book_lookup and book_lookup[g]["title"] and book_lookup[g]["title"].lower() in src.lower()]
check("no gold book TITLES hardcoded in demo_view.py", not title_leak, title_leak)
# determinism: pure over (resp, lookup)
r1 = dv.verdict_for(resp([75], [row(1, 21, False), row(2, 75, True)]), LOOKUP)
r2 = dv.verdict_for(resp([75], [row(1, 21, False), row(2, 75, True)]), LOOKUP)
check("verdict_for is pure/deterministic", r1 == r2)
if FX:
    vms = FX["view_models"]
    reps = FX.get("representative", [])
    v = {rid: {s: vms[rid]["strategies"][s]["verdict"] for s in dv.STRATS} for rid in reps}
    # The two lead slots must jointly demonstrate BOTH complementary blind spots
    # (one lexical-blind, one vector-blind), and hybrid must save both. Order is
    # NOT pinned: full-summary indexing made the lexical blind spot rare, so the
    # deck now leads with the vector blind spot (bare names) — assert the invariant,
    # not a fixed slot order.
    def is_lex_blind(d):  # lexical misses, vector + hybrid save
        return d["lexical"] != "found" and d["vector"] == "found" and d["hybrid"] == "found"
    def is_vec_blind(d):  # vector misses, lexical + hybrid save
        return d["vector"] != "found" and d["lexical"] == "found" and d["hybrid"] == "found"
    lead = [v[reps[0]], v[reps[1]]]
    check("lead pair covers the lexical blind spot (lexical NOT found, vector+hybrid found)",
          any(is_lex_blind(d) for d in lead), lead)
    check("lead pair covers the vector blind spot (vector NOT found, lexical+hybrid found)",
          any(is_vec_blind(d) for d in lead), lead)
    check("hybrid never blanks across the representative set",
          all(vms[rid]["strategies"]["hybrid"]["verdict"] == "found" for rid in reps),
          {rid: vms[rid]["strategies"]["hybrid"]["verdict"] for rid in reps})
    # baked representative scoreboard tally == counted found verdicts (no double counting)
    sb = FX["representative_scoreboard"]["per_strategy"]
    for s in dv.STRATS:
        want = sum(1 for rid in reps if vms[rid]["strategies"][s]["verdict"] == "found")
        check(f"rep scoreboard '{s}' found == counted ({want})", sb[s]["found"] == want, sb[s])
    # Shuffle pool: golden-only, non-empty, and disjoint from the representative queries
    pool_ids = [i for ids in FX["pool_by_type"].values() for i in ids]
    rep_q = {vms[rid]["query"] for rid in reps}
    check("shuffle pool non-empty (>= 9)", len(pool_ids) >= 9, len(pool_ids))
    check("shuffle pool disjoint from representative queries",
          not (rep_q & {vms[i]["query"] for i in pool_ids}))

print(f"\n{'='*54}\nRESULT: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILURES:", FAIL)
    sys.exit(1)
print("ALL GREEN")

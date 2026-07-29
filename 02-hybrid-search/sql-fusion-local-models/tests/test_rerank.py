#!/usr/bin/env python3
"""Unit tests for the post-fusion reranking stage (hybrid_search.rerank).

Pure-logic tests: the reranker HTTP call is monkeypatched, so these need neither
the reranker server nor Db2. Covers the sort-and-cut logic (index mapping,
descending sort, negative scores, ties), the timeout->fusion-fallback path, and the
LRU score cache (hit/miss). A live end-to-end + off-flag byte-for-byte identity is
proven separately by scripts/rerank/rerank_eval.py and the API smoke.

Run: PYTHONPATH=src .venv/bin/python tests/test_rerank.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from hybrid_search import rerank as rr

PASS, FAIL = [], []
def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + ("" if cond else f"  << {detail}"))

rr._endpoint = "/v1/reranking"   # skip endpoint auto-detection in tests
CANDS = [(10, "a"), (11, "b"), (12, "c"), (13, "d")]   # fusion order, best-first


def fake_scores(score_by_index):
    """Return a _request stand-in that scores documents by their input index."""
    def _req(path, query, documents, timeout):
        return {"results": [{"index": i, "relevance_score": score_by_index[i]}
                            for i in range(len(documents))]}
    return _req


print("\n1. sort-and-cut (index mapping · descending · negatives · ties):")
# idx: 0=-1.0  1=5.0  2=5.0  3=0.0  -> desc with stable tie-break -> [11,12,13,10]
rr._request = fake_scores([-1.0, 5.0, 5.0, 0.0])
rr.clear_cache()
out, meta = rr.rerank("q", CANDS, n=10, k=3)
ids = [cid for cid, _t, _s in out]
check("descending sort by relevance_score", ids == [11, 12, 13], ids)
check("cut to k=3", len(out) == 3, len(out))
check("ties keep fusion order (11 before 12 at score 5.0)", ids[0] == 11 and ids[1] == 12, ids)
check("negative scores handled (10 last, -1.0)", 10 not in ids, ids)
check("scores attached and mapped to right candidate", out[0] == (11, "b", 5.0), out[0])
check("meta reranked/no-fallback", meta["reranked"] and not meta["fell_back"], meta)

# reversed input scores -> full reversal
rr._request = fake_scores([4.0, 3.0, 2.0, 1.0])
rr.clear_cache()
out, _ = rr.rerank("q", CANDS, n=10, k=4)
check("monotonic input preserves order", [c for c, _, _ in out] == [10, 11, 12, 13])
rr._request = fake_scores([1.0, 2.0, 3.0, 4.0])
rr.clear_cache()
out, _ = rr.rerank("q", CANDS, n=10, k=4)
check("reversed input fully reorders", [c for c, _, _ in out] == [13, 12, 11, 10])


print("\n2. timeout -> fusion fallback (never raises):")
def raiser(*a, **k):
    raise TimeoutError("simulated reranker timeout")
rr._request = raiser
rr.clear_cache()
try:
    out, meta = rr.rerank("q", CANDS, n=10, k=2)
    raised = False
except Exception:
    raised = True
check("does not raise on reranker failure", not raised)
check("falls back to fusion order", [c for c, _, _ in out] == [10, 11], [c for c, _, _ in out])
check("fallback cut to k", len(out) == 2, len(out))
check("fallback scores are None (not fabricated)", all(s is None for _, _, s in out))
check("meta.fell_back set", meta["fell_back"] and not meta["reranked"], meta)


print("\n3. n cap and empty:")
rr._request = fake_scores([9.0, 8.0, 7.0, 6.0])
rr.clear_cache()
out, meta = rr.rerank("q", CANDS, n=2, k=5)   # only first 2 candidates are eligible
check("n caps the candidate pool", meta["n"] == 2 and {c for c, _, _ in out} == {10, 11}, (meta, out))
out, meta = rr.rerank("q", [], n=10, k=3)
check("empty candidates -> empty, no call", out == [] and meta["n"] == 0)


print("\n4. LRU cache (hit/miss · one batched request):")
calls = {"n": 0, "docs": 0}
def counting(path, query, documents, timeout):
    calls["n"] += 1
    calls["docs"] += len(documents)
    return {"results": [{"index": i, "relevance_score": -float(i)} for i in range(len(documents))]}
rr._request = counting
rr.clear_cache()
rr.rerank("Building Habits", CANDS, n=10, k=4)
after_first = dict(calls)
check("first query issues exactly ONE batched request", after_first["n"] == 1, after_first)
check("one request carried all candidates (batched, not per-doc)", after_first["docs"] == 4, after_first)
out, meta = rr.rerank("building   habits", CANDS, n=10, k=4)   # same query normalized -> all cached
check("repeat query: no new request (cache hit)", calls["n"] == after_first["n"], calls)
check("meta.cached counts all candidates on hit", meta["cached"] == 4, meta)
# a partial-overlap query: only the new candidate triggers a request
rr.rerank("building habits", CANDS + [(14, "e")], n=10, k=5)
check("partial cache: only the uncached doc is re-requested", calls["docs"] == after_first["docs"] + 1, calls)


print(f"\n{'='*54}\nRESULT: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILURES:", FAIL); sys.exit(1)
print("ALL GREEN")

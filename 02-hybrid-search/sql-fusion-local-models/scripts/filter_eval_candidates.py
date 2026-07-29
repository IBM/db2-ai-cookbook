#!/usr/bin/env python3
"""filter_eval_candidates.py — round-trip filter for golden-set query candidates.

Takes candidate queries (each with a KNOWN target book), runs all three retrieval
legs against Db2, and:
  - REJECTS any query whose target book isn't retrievable (not in the candidate pool)
    — a query the engine can't answer is worthless for eval;
  - AUTO-LABELS query_type (keyword / semantic / mixed) from the lexical-vs-vector
    rank gap — the label your diagnostic table needs to isolate a leg;
  - emits golden-set-shaped entries (review_status=needs_review, split=train), each
    carrying the measured ranks so a human can review, verify, and merge.

This automates the manual "write a query -> check it against the live engine -> keep
only the leg-discriminating ones" loop. The keep-only-if-retrieved rule is
consistency / round-trip filtering, as in Promptagator (Dai et al. 2022) and InPars
(Bonifacio et al. 2022): a generated query is kept only if its source doc is
retrieved for it.

Run (local Db2 connection, like scripts/eval.py):
    DB2_HOST=local PYTHONPATH=src python scripts/filter_eval_candidates.py CANDIDATES.json

CANDIDATES is a JSON list (or JSONL). Each item has a "query" and a target — one of:
    {"query": "...", "gold_ids": [66]}                  # corpus id(s) directly
    {"query": "...", "target_asin": "B07GBGQJSW"}
    {"query": "...", "target_title": "Atomic Habits"}   # case-insensitive substring

Output: data/eval/generated_candidates.json (accepted) + a reject report on stderr.
Tunables (env): FOUND_K (default 10) = rank at/above which a leg "found" it;
TYPE_GAP (default 5) = min lexical-vs-vector rank gap to call one leg the winner.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "src"))
os.environ.setdefault("DB2_HOST", "local")   # fast local connection, like eval.py

import ibm_db                                 # noqa: E402
from hybrid_search import core as h           # noqa: E402

FOUND_K = int(os.environ.get("FOUND_K", "10"))    # "found" = gold rank <= this
TYPE_GAP = int(os.environ.get("TYPE_GAP", "5"))   # min lex-vs-vec gap to pick a winner
MIN_TOP = int(os.environ.get("MIN_TOP", "3"))     # keep only if the target reaches top-N on SOME leg

# NOTE on small corpora: with POOL >= corpus size, EVERY query "retrieves" the target
# somewhere in the pool, so mere retrievability can't reject a mislabeled pair (a
# nonsense query can still rank the wrong book at, say, #6). We therefore require the
# target to reach the top MIN_TOP on at least one base leg — a genuine known-item
# answer. Even so, rank alone can't tell a weak-but-valid query from a wrong one on a
# tiny corpus: review the emitted ranks. (Round-trip filtering is stronger the larger
# the corpus.)


def load_corpus_maps(conn):
    """asin(upper)->cid, [(title,cid)], cid->title — for resolving targets by asin/title."""
    asin2cid, title_pairs, cid2title = {}, [], {}
    st = ibm_db.exec_immediate(conn, "SELECT CHUNK_ID, ASIN, TITLE FROM MYSCHEMA.CHUNKS")
    r = ibm_db.fetch_assoc(st)
    while r:
        cid = r["CHUNK_ID"]
        asin = (r["ASIN"] or "").strip()
        title = r["TITLE"] or ""
        if asin:
            asin2cid[asin.upper()] = cid
        title_pairs.append((title, cid))
        cid2title[cid] = title
        r = ibm_db.fetch_assoc(st)
    return asin2cid, title_pairs, cid2title


def resolve_gold(item, asin2cid, title_pairs):
    if item.get("gold_ids"):
        return [c for c in item["gold_ids"] if c is not None]
    if item.get("target_asin"):
        cid = asin2cid.get(item["target_asin"].strip().upper())
        return [cid] if cid else []
    if item.get("target_title"):
        sub = item["target_title"].lower()
        return [cid for (t, cid) in title_pairs if sub in (t or "").lower()][:1]
    return []


def rank_of(rows, golds):
    """1-based rank of the best gold id in a leg's (cid, score) results; None if absent."""
    best = None
    for i, (cid, _score) in enumerate(rows, 1):
        if cid in golds:
            best = i if best is None else min(best, i)
    return best


def classify(rl, rv, pool):
    """keyword / semantic / mixed from the lexical (rl) vs vector (rv) ranks."""
    sl = rl if rl is not None else pool + 1
    sv = rv if rv is not None else pool + 1
    lex_found = rl is not None and rl <= FOUND_K
    vec_found = rv is not None and rv <= FOUND_K
    gap = sv - sl                      # > 0: lexical ranks it higher (better)
    if lex_found and not vec_found:
        return "keyword"
    if vec_found and not lex_found:
        return "semantic"
    if lex_found and vec_found:
        if abs(gap) < TYPE_GAP:
            return "mixed"
        return "keyword" if gap > 0 else "semantic"
    return "mixed"                     # retrievable in pool but neither in top FOUND_K


def difficulty(rh):
    if rh == 1:
        return "easy"
    if rh is not None and rh <= 3:
        return "medium"
    return "hard"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("candidates", help="JSON list (or JSONL) of {query, gold_ids|target_asin|target_title}")
    ap.add_argument("-o", "--out", default=os.path.join(REPO, "data/eval/generated_candidates.json"))
    ap.add_argument("--source", default="generated", help="source tag for emitted entries")
    ap.add_argument("--golden", default=os.path.join(REPO, "data/eval/golden_set.json"),
                    help="existing golden set — read only, to continue id numbering")
    args = ap.parse_args()

    raw = open(args.candidates, encoding="utf-8").read().strip()
    try:
        cands = json.loads(raw)
        if isinstance(cands, dict) and "queries" in cands:
            cands = cands["queries"]
    except json.JSONDecodeError:
        cands = [json.loads(line) for line in raw.splitlines() if line.strip()]

    next_id = 1
    if os.path.exists(args.golden):
        g = json.load(open(args.golden, encoding="utf-8"))
        g = g["queries"] if isinstance(g, dict) and "queries" in g else g
        next_id = max((x.get("id", 0) for x in g), default=0) + 1

    conn = h.connect()
    asin2cid, title_pairs, cid2title = load_corpus_maps(conn)
    pool = h.POOL

    kept, rejects = [], []
    counts = {"keyword": 0, "semantic": 0, "mixed": 0}
    weak = 0
    for item in cands:
        q = item["query"]
        golds = resolve_gold(item, asin2cid, title_pairs)
        if not golds:
            rejects.append((q, "target not resolved (check gold_ids / target_asin / target_title)"))
            continue
        rl = rank_of(h.lexical(conn, q, pool), golds)
        rv = rank_of(h.vector(conn, q, pool), golds)
        rh = rank_of(h.hybrid_split(conn, q, q, pool), golds)
        best = min((x for x in (rl, rv) if x is not None), default=None)
        if best is None or best > MIN_TOP:
            rejects.append((q, f"target not a top-{MIN_TOP} answer on any leg "
                               f"(lex #{rl or 'NF'}, vec #{rv or 'NF'}) — weak/mislabeled pair"))
            continue
        qtype = classify(rl, rv, pool)
        counts[qtype] += 1
        is_weak = best > FOUND_K
        weak += is_weak
        title = cid2title.get(golds[0], "?")
        kept.append({
            "id": next_id,
            "query": q,
            "gold_ids": golds,
            "query_class": item.get("query_class", "known_item" if len(golds) == 1 else "topical"),
            "query_type": qtype,
            "difficulty": difficulty(rh),
            "rationale": (f"auto: '{title[:40]}' — lexical #{rl or 'NF'}, vector #{rv or 'NF'}, "
                          f"hybrid #{rh or 'NF'}" + (" (WEAK: best rank low)" if is_weak else "")),
            "review_status": "needs_review",
            "source": args.source,
            "split": "train",   # never auto-add to holdout; that slice stays hand-verified
            "diag": {"lex_rank": rl, "vec_rank": rv, "hyb_rank": rh, "weak": is_weak},
        })
        next_id += 1

    json.dump(kept, open(args.out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

    print(f"candidates: {len(cands)}  kept: {len(kept)}  rejected: {len(rejects)}  (weak-but-kept: {weak})",
          file=sys.stderr)
    print(f"  by query_type: {counts}", file=sys.stderr)
    for q, why in rejects:
        print(f"  REJECT  {q!r}: {why}", file=sys.stderr)
    print(f"wrote {len(kept)} entries -> {os.path.relpath(args.out, REPO)}", file=sys.stderr)
    print("  Review 'WEAK' entries and query_type labels, set review_status, then merge into golden_set.json.",
          file=sys.stderr)


if __name__ == "__main__":
    main()

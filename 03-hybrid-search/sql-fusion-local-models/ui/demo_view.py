#!/usr/bin/env python3
"""Outcome-translation for the mixed-audience demo view.

PURE over (three-strategy search response, gold ids). No per-query hardcoding:
every verdict and every shown book is derived from the response + the corpus
lookup, so the same code drives offline fixtures (ui/build_demo.py) and the live
endpoint (ui/api.py /api/demo). Unit-tested in tests/test_demo_view.py.

Response shape consumed (unchanged, from build_fixtures.responses_for):
  { "lexical": R, "vector": R, "hybrid": R }
  R = { query, mode, k, gold_chunk_ids, gold_rank, results:[row...] }
  row = { rank, chunk_id, snippet, text, score, score_type, is_gold,
          (hybrid only) found_by, per_leg, contribution }
"""
import csv
import re

K_DEFAULT = 5
STRATS = ("lexical", "vector", "hybrid")
STRAT_LABEL = {"lexical": "Lexical", "vector": "Semantic", "hybrid": "Hybrid"}
LEG_WORD = {"bm25": "lexical", "vector": "semantic"}

VERDICT_FOUND = "found"       # gold within top k
VERDICT_WRONG = "wrong"       # gold absent, but a confident non-gold top result exists
VERDICT_NOTHING = "nothing"   # no results at all


def load_book_lookup(corpus_csv):
    """{chunk_id: {'title','author'}} from the corpus CSV (id == chunk_id)."""
    look = {}
    with open(corpus_csv) as f:
        for r in csv.DictReader(f):
            look[int(r["id"])] = {"title": r.get("title", ""), "author": r.get("authors", "")}
    return look


_BY_RE = re.compile(r"^\s*(?P<title>.+?)\s+by\s+(?P<author>.+?)\.", re.S)


def label_for(chunk_id, text, lookup):
    """Real title/author by id; fall back to parsing 'Title by Author.' off the
    front of chunk_text. Never returns the raw description as the label."""
    b = (lookup or {}).get(chunk_id)
    if b and b.get("title"):
        return {"title": b["title"], "author": b.get("author", "")}
    m = _BY_RE.match(text or "")
    if m:
        return {"title": m.group("title").strip(), "author": m.group("author").strip()}
    t = (text or "").strip()
    return {"title": t[:60] if t else f"#{chunk_id}", "author": ""}


def _shown(row, lookup):
    if not row:
        return None
    lab = label_for(row["chunk_id"], row.get("text", ""), lookup)
    out = {"title": lab["title"], "author": lab["author"],
           "rank": row.get("rank"), "chunk_id": row.get("chunk_id"),
           "score": row.get("score"), "score_type": row.get("score_type"),
           "is_gold": bool(row.get("is_gold")), "cover": row.get("cover", "")}
    if "found_by" in row:
        out["found_by"] = row["found_by"]
    return out


def verdict_for(resp, lookup):
    """The core translation. Pure over (resp, lookup). Returns
    {verdict, shown, gold_rank}."""
    results = resp.get("results") or []
    gold_rank = resp.get("gold_rank")
    if gold_rank is not None:
        shown = next((r for r in results if r.get("is_gold")), results[0] if results else None)
        return {"verdict": VERDICT_FOUND, "shown": _shown(shown, lookup), "gold_rank": gold_rank}
    if results:
        return {"verdict": VERDICT_WRONG, "shown": _shown(results[0], lookup), "gold_rank": None}
    return {"verdict": VERDICT_NOTHING, "shown": None, "gold_rank": None}


def _fusion_note(shown):
    fb = (shown or {}).get("found_by") or []
    if not fb:
        return ""
    return "found by " + " + ".join(LEG_WORD.get(x, x) for x in fb)


def view_model(responses, deck_item, lookup, k=K_DEFAULT):
    """Full per-query view model for the demo page."""
    strategies = {}
    for s in STRATS:
        resp = responses[s]
        v = verdict_for(resp, lookup)
        v["k"] = resp.get("k", k)
        v["gold_ids"] = resp.get("gold_chunk_ids", [])
        v["results"] = [_shown(r, lookup) for r in (resp.get("results") or [])]  # technical: full list
        if s == "hybrid":
            v["fusion_note"] = _fusion_note(v.get("shown"))
        strategies[s] = v
    return {
        "id": deck_item.get("id"),
        "query": deck_item.get("query"),
        "query_type": deck_item.get("query_type"),
        "query_class": deck_item.get("query_class", "known_item"),
        "scenario": deck_item.get("scenario", ""),
        "gold_ids": deck_item.get("gold_chunk_ids", []),
        "strategies": strategies,
    }


def scoreboard(view_models):
    """Session tally, graded found/not-found (the headline). MRR/Hits@1 are the
    technical extras and only count single-gold (known_item) queries."""
    per = {s: {"found": 0, "blank": 0, "total": 0} for s in STRATS}
    mrr = {s: 0.0 for s in STRATS}
    hits1 = {s: 0 for s in STRATS}
    ki = 0
    for vm in view_models:
        is_ki = vm.get("query_class", "known_item") == "known_item"
        if is_ki:
            ki += 1
        for s in STRATS:
            st = vm["strategies"][s]
            per[s]["total"] += 1
            if st["verdict"] == VERDICT_FOUND:
                per[s]["found"] += 1
                if is_ki and st.get("gold_rank"):
                    mrr[s] += 1.0 / st["gold_rank"]
                    if st["gold_rank"] == 1:
                        hits1[s] += 1
            else:
                per[s]["blank"] += 1
    kd = ki or 1
    return {
        "n": len(view_models),
        "known_item": ki,
        "per_strategy": per,
        "mrr": {s: round(mrr[s] / kd, 3) for s in STRATS},
        "hits1": {s: round(hits1[s] / kd, 3) for s in STRATS},
    }

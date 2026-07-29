#!/usr/bin/env python3
"""Freeze the demo into ui/static/demo_fixtures.json (offline-safe):

  - a POOL of golden eval queries (known_item, per type) that the Shuffle button
    samples from — so shuffling pulls a genuinely new set of golden queries;
  - the curated REPRESENTATIVE set (ui/demo_queries.json, with scenarios) shown on
    load and by the "Representative set" button.

Every query is run through all three strategies (build_fixtures.responses_for) and
the outcome-translation (demo_view.view_model). Reuses those unchanged.

Run: PYTHONPATH=src DB2_HOST=local .venv/bin/python ui/build_demo.py
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # ui/
import ibm_db
from hybrid_search import core as h
from hybrid_search import evalset
import build_fixtures as bf
import demo_view as dv

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PER_TYPE = 12   # golden queries per type in the shuffle pool


def golden_path():
    # Ships at data/eval/golden_set.json (see hybrid_search.evalset).
    return evalset.resolve()


def main():
    curated = json.load(open(os.path.join(HERE, "demo_queries.json")))
    golden = json.load(open(golden_path()))
    lookup = dv.load_book_lookup(os.path.join(REPO, "data", "corpus.csv"))
    curated_q = {c["query"] for c in curated}

    # entries: (uid, deck_item). Curated -> r1..rN (with scenarios). Golden pool -> g<id>.
    entries = [(f"r{i}", c) for i, c in enumerate(curated, 1)]
    by_type = {"keyword": [], "semantic": [], "mixed": []}
    for g in golden:
        if g.get("query_class") != "known_item" or g.get("query_type") not in by_type:
            continue
        if g["query"] in curated_q:
            continue                       # avoid duplicating a curated query
        by_type[g["query_type"]].append(g)
    for t, arr in by_type.items():
        for g in arr[:PER_TYPE]:
            entries.append((f"g{g['id']}", {
                "id": f"g{g['id']}", "query": g["query"], "query_type": t,
                "query_class": "known_item", "gold_chunk_ids": g["gold_ids"], "scenario": ""}))

    conn = h.connect()
    vms = {}
    try:
        for uid, item in entries:
            responses = bf.responses_for(conn, item["query"], set(item["gold_chunk_ids"]))
            vm = dv.view_model(responses, item, lookup, k=bf.K)
            vm["id"] = uid
            vms[uid] = vm
    finally:
        ibm_db.close(conn)

    # Shuffle pool = GOLDEN queries only (g-ids), by type. Representative = curated (r-ids).
    pool_by_type = {"keyword": [], "semantic": [], "mixed": []}
    for uid, vm in vms.items():
        if uid.startswith("g"):
            pool_by_type[vm["query_type"]].append(uid)
    representative = [f"r{i}" for i in range(1, len(curated) + 1)]

    out = {
        "meta": {"k": bf.K, "weights": {"lexical": h.W_LEX, "vector": h.W_VEC},
                 "vec_gate": h.VEC_GATE, "lex_gate": h.LEX_GATE, "pool": h.POOL,
                 "per_type": PER_TYPE},
        "view_models": vms,
        "pool_by_type": pool_by_type,
        "representative": representative,
        "representative_scoreboard": dv.scoreboard([vms[i] for i in representative]),
    }
    with open(os.path.join(HERE, "static", "demo_fixtures.json"), "w") as f:
        json.dump(out, f, indent=2)

    print(f"wrote static/demo_fixtures.json — {len(vms)} view models "
          f"({len(representative)} representative + pool)")
    print("  shuffle pool per type:", {t: len(ids) for t, ids in pool_by_type.items()})
    sb = out["representative_scoreboard"]["per_strategy"]
    print("  representative coverage:", {s: f"{sb[s]['found']}/{sb[s]['total']}" for s in dv.STRATS})


if __name__ == "__main__":
    main()

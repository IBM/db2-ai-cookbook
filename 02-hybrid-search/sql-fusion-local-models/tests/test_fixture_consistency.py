#!/usr/bin/env python3
"""Catch STALE FIXTURES and STALE SCENARIO TEXT.

The frozen artifacts under ui/static/ are built from Db2 by ui/build_*.py. Nothing
detected when they drifted out of sync with the live engine, so the offline demo
could confidently show numbers the engine no longer produces — and the curated
scenario text could claim "keyword finds nothing" after keyword started finding
something. Both happened during development; the existing E2E suite passed
happily through it, because it only checks that the UI renders.

Two checks:
  1. FIXTURE FRESHNESS  — re-run each demo query through the live engine and
     compare the per-leg verdict (found / wrong / nothing) against the frozen
     demo_fixtures.json. Any difference means the fixtures need rebuilding.
  2. SCENARIO TRUTH     — assert each curated scenario's claim about a leg matches
     that leg's measured verdict, so prose can't contradict the data.

Needs Db2 + the embedding server. SKIPS (exit 0) when they're unavailable, so it
never fails a machine that simply isn't running the stack.

Run: DB2_HOST=local PYTHONPATH=src python tests/test_fixture_consistency.py
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "src"))
sys.path.insert(0, os.path.join(REPO, "ui"))

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + ("" if cond else f"  << {detail}"))


def main():
    os.environ.setdefault("DB2_HOST", "local")
    try:
        from hybrid_search import core as h
        conn = h.connect()
    except Exception as e:
        print(f"SKIP — Db2/engine unavailable ({type(e).__name__}). "
              f"Start services: ./scripts/0_start-services.sh")
        return 0

    fx_path = os.path.join(REPO, "ui", "static", "demo_fixtures.json")
    if not os.path.exists(fx_path):
        print("SKIP — ui/static/demo_fixtures.json not built yet")
        return 0
    fx = json.load(open(fx_path))
    deck = json.load(open(os.path.join(REPO, "ui", "demo_queries.json")))

    K = 5  # must match build_fixtures.K — the "found" cutoff

    def live_verdict(query, gold):
        """Reproduce demo_view's verdict from the live engine."""
        out = {}
        legs = {"lexical": lambda q: h.lexical(conn, q, K),
                "vector":  lambda q: h.vector(conn, q, K),
                "hybrid":  lambda q: h.hybrid_split(conn, q, q, K)}
        for leg, fn in legs.items():
            res = fn(query)
            if not res:
                out[leg] = "nothing"
            elif any(cid in gold for cid, _ in res):
                out[leg] = "found"
            else:
                out[leg] = "wrong"
        return out

    print(f"Fixture freshness (live engine vs ui/static/demo_fixtures.json), "
          f"W_LEX={h.W_LEX} W_VEC={h.W_VEC} POOL={h.POOL}:")
    for i, item in enumerate(deck, 1):
        vm = fx["view_models"].get(f"r{i}")
        if not vm:
            check(f"r{i} present in fixtures", False, "missing view model")
            continue
        gold = set(item["gold_chunk_ids"])
        live = live_verdict(item["query"], gold)
        frozen = {leg: vm["strategies"][leg]["verdict"] for leg in live}
        check(f"r{i} {item['query'][:34]!r} verdicts match",
              live == frozen, f"live={live} frozen={frozen} — rebuild: ui/build_demo.py")

    # ---- scenario prose must not contradict the measured verdict -------------
    # Only assert on unambiguous claims; prose is free-form elsewhere.
    CLAIMS = [
        (r"keyword (search )?(comes back empty|finds nothing)", "lexical", "nothing"),
        (r"keyword leg (keeps it|nails it)",                    "lexical", "found"),
        (r"vector leg (wanders|drifts)",                        "vector",  "wrong"),
    ]
    print("\nScenario text vs measured verdict:")
    for i, item in enumerate(deck, 1):
        vm = fx["view_models"].get(f"r{i}")
        if not vm:
            continue
        scen = (item.get("scenario") or "").lower()
        for pat, leg, expected in CLAIMS:
            if re.search(pat, scen):
                actual = vm["strategies"][leg]["verdict"]
                check(f"r{i} claims {leg}={expected}",
                      actual == expected,
                      f"scenario says {expected!r} but {leg} measured {actual!r} — "
                      f"fix ui/demo_queries.json")

    print(f"\n{'='*54}\nRESULT: {len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILURES:", FAIL)
        return 1
    print("ALL GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())

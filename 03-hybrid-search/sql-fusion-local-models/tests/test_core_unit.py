#!/usr/bin/env python3
"""Pure-logic unit tests for the engine — NO Db2, no server, no browser.

Covers the retrieval logic everything else depends on and that the rest of the
suite is blind to: a subtle break here produces plausible-but-wrong results while
the demo still renders and the E2E still passes. Specifically:

  1. keywords()      — stopword filtering + the "never send an empty CONTAINS" fallback
  2. embed_query()   — the bge retrieval prefix
  3. evalset.resolve() — golden-set path precedence
  4. config coherence — .env.example == core.py defaults == 2_search.sql, so the
                         four-way weight drift we hit can't recur silently

Parts 1-2 need `hybrid_search.core`, which imports ibm_db (installed by
`pip install -e .`; no database connection is made). If ibm_db is absent they SKIP.
Parts 3-4 need neither, so they run on a truly bare clone.

Run: PYTHONPATH=src python tests/test_core_unit.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "src"))

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + ("" if cond else f"  << {detail}"))


# ---------------------------------------------------------------- 1 & 2: engine
def test_keywords_and_embed():
    try:
        from hybrid_search import core as h
    except ImportError as e:
        print(f"  [SKIP] keywords()/embed_query() — {e} (run `pip install -e .`)")
        return

    print("keywords() — stopword filter + fallback:")
    exp = {
        "coping with stress": "coping OR stress",          # stopword 'with' dropped
        "The Willpower Instinct": "Willpower OR Instinct",  # case-insensitive drop of 'The'
        "habits": "habits",                                 # single content word, no OR
        "worry and. stress": "worry OR stress",             # punctuation-tolerant: 'and.' -> stopword
        "met.": "met.",                                     # content token keeps its punctuation
        "the and of": "the OR and OR of",                   # ALL stopwords -> fallback, never empty
        "AND": "AND",                                        # single stopword -> fallback to itself
        "find me a book on public speaking":
            "find OR book OR public OR speaking",           # 'book'/'find' are NOT stripped (post-UDF)
    }
    for q, want in exp.items():
        got = h.keywords(q)
        check(f"keywords({q!r})", got == want, f"got {got!r}, want {want!r}")

    # the fallback contract, stated directly: a non-empty query never yields an empty CONTAINS
    for q in ["the and of", "AND", "of the"]:
        check(f"keywords({q!r}) is non-empty (no empty CONTAINS)", h.keywords(q) != "")
    # 'book'/'find' explicitly retained — pins the deliberate removal of domain cleaning
    kw = h.keywords("find me a book about focus")
    check("'book' retained (domain filtering stays removed)", "book" in kw, kw)
    check("'find' retained", "find" in kw, kw)

    print("embed_query() — bge retrieval prefix:")
    check("prepends QUERY_PREFIX", h.embed_query("focus") == h.QUERY_PREFIX + "focus")
    check("prefix is the bge retrieval instruction",
          h.QUERY_PREFIX.startswith("Represent this sentence"))


# ---------------------------------------------------------------- 3: resolver
def test_evalset_resolve():
    from hybrid_search import evalset
    print("evalset.resolve() — path precedence:")

    saved = os.environ.pop("GOLDEN_SET", None)
    try:
        os.environ["GOLDEN_SET"] = "/tmp/override.json"
        check("$GOLDEN_SET wins over everything", evalset.resolve() == "/tmp/override.json")
        os.environ.pop("GOLDEN_SET")

        check("explicit arg wins when no env", evalset.resolve("/tmp/explicit.json") == "/tmp/explicit.json")

        got = evalset.resolve()
        check("defaults to the SHIPPED set", got == evalset.SHIPPED and os.path.exists(got),
              f"{got} (exists={os.path.exists(got)})")

        # not-found: message must name every place tried, not raise a bare IndexError
        s, g = evalset.SHIPPED, evalset.LEGACY_GLOB
        evalset.SHIPPED = "/nonexistent/golden_set.json"
        evalset.LEGACY_GLOB = "/nonexistent/golden_set.draft.v*.json"
        try:
            evalset.resolve()
            check("raises FileNotFoundError when nothing is found", False, "no exception raised")
        except FileNotFoundError as e:
            msg = str(e)
            check("not-found error names $GOLDEN_SET and the paths",
                  "GOLDEN_SET" in msg and "golden_set" in msg, msg[:80])
        except Exception as e:
            check("not-found raises FileNotFoundError (not IndexError)", False, type(e).__name__)
        finally:
            evalset.SHIPPED, evalset.LEGACY_GLOB = s, g
    finally:
        os.environ.pop("GOLDEN_SET", None)
        if saved is not None:
            os.environ["GOLDEN_SET"] = saved


# ---------------------------------------------------------------- 4: coherence
def test_config_coherence():
    """.env.example, core.py defaults, and 2_search.sql must agree — parsed from
    SOURCE (not imported), so this runs with no deps and isn't fooled by a local .env."""
    print("config coherence — .env.example == core.py == 2_search.sql:")
    keys = ["HYBRID_W_LEX", "HYBRID_W_VEC", "HYBRID_VEC_GATE", "HYBRID_LEX_GATE", "HYBRID_POOL"]

    env = open(os.path.join(REPO, ".env.example")).read()
    core = open(os.path.join(REPO, "src", "hybrid_search", "core.py")).read()

    env_vals, core_vals = {}, {}
    for k in keys:
        m = re.search(rf"^{k}=(\S+)", env, re.M)
        env_vals[k] = m.group(1) if m else None
        m = re.search(rf'setting\("{k}",\s*"([^"]+)"\)', core)
        core_vals[k] = m.group(1) if m else None
        ok = (env_vals[k] is not None and core_vals[k] is not None
              and float(env_vals[k]) == float(core_vals[k]))
        check(f"{k}: .env.example ({env_vals[k]}) == core.py default ({core_vals[k]})", ok)

    # 2_search.sql inlines the weights and pool — the file that actually drifted before.
    sql = open(os.path.join(REPO, "scripts", "2_search.sql")).read()
    wl, wv, pool = env_vals["HYBRID_W_LEX"], env_vals["HYBRID_W_VEC"], env_vals["HYBRID_POOL"]
    check(f"2_search.sql fuses {wl}*lex + {wv}*vec",
          f"{wl} * COALESCE(lex.n, 0) + {wv} * COALESCE(vec.n, 0)" in sql,
          "weight literals not found in the fusion expression")
    check(f"2_search.sql pools {pool} rows",
          f"FETCH FIRST {pool} ROWS" in sql and f"FETCH APPROX FIRST {pool} ROWS" in sql)


def main():
    test_config_coherence()
    test_evalset_resolve()
    test_keywords_and_embed()
    print(f"\n{'='*54}\nRESULT: {len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILURES:", FAIL)
        return 1
    print("ALL GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())

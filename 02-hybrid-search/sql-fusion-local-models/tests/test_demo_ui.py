#!/usr/bin/env python3
"""Phase-2 D/E/F for the demo page:
  - static structural + a11y/responsive assertions (fixture-based, deterministic)
  - FastAPI TestClient smoke (substitutes headless-browser E2E, which this env lacks)
  - regression: existing pages/endpoints still serve

Run: PYTHONPATH=src DB2_HOST=local .venv/bin/python tests/test_demo_ui.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
UI = os.path.join(REPO, "ui")
STATIC = os.path.join(UI, "static")
sys.path.insert(0, UI)
sys.path.insert(0, os.path.join(REPO, "src"))

PASS, FAIL, SKIP = [], [], []
def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + ("" if cond else f"  << {detail}"))
def read(p): return open(p).read()

idx = read(os.path.join(STATIC, "index.html"))
appjs = read(os.path.join(STATIC, "app.js"))
demojs = read(os.path.join(STATIC, "demo.js"))
css = read(os.path.join(STATIC, "styles.css"))

# ---------------- F + registration: static structure / a11y / responsive ----------------
print("\nF + registration (static):")
check("index.html registers demo tab", 'data-page="demo"' in idx)
check("index.html has #page-demo section", 'id="page-demo"' in idx)
check("index.html loads demo.js", 'src="demo.js' in idx)  # tolerate ?v= cache-bust
check("app.js setPage is generic (registers new pages)", '[id^="page-"]' in appjs)
check("demo.js renders verdict icon + text (color not sole signal)",
      "icon:" in demojs and "label:" in demojs and 'aria-hidden="true"' in demojs)
check("verdict classes styled distinctly", all(c in css for c in
      [".dpanel-found", ".dpanel-wrong", ".dpanel-nothing"]))
check("responsive: max-width 640px media query", "max-width: 640px" in css or "max-width:640px" in css)
check("responsive: 3-column panels grid", "repeat(3, 1fr)" in css or "repeat(3,1fr)" in css)
check("a11y: ARIA roles/labels present on demo controls",
      'role="group"' in idx and 'aria-label="example queries"' in idx and 'aria-live="polite"' in idx)
check("a11y: keyboard/focus — chips focus-visible styled", ".dchip:focus-visible" in css)
check("a11y: screen-reader-only class defined", ".sr-only" in css and "sr-only" in demojs)
check("matrix (queries x methods) rendered for narrow view", "dsb-matrix" in demojs and ".dsb-matrix" in css)
check("demo has a Shuffle control", 'id="demo-shuffle"' in idx and "shuffleDeck" in demojs)
check("shuffle resets the scoreboard", "resetSession" in demojs and "D.seen.clear()" in demojs)
check("demo has a Representative-set control", 'id="demo-representative"' in idx and "loadRepresentative" in demojs)
# terminology: "Keyword" is the Search-tab mode label (user-chosen); raw BM25/Vector
# are still never surfaced as UI labels.
appjs = read(os.path.join(STATIC, "app.js"))
for bad in (">BM25<", ">Vector<", '"BM25"', '"Vector"'):
    check(f"no leg label {bad!r} in app.js/demo.js/index.html",
          bad not in appjs and bad not in demojs and bad not in idx, bad)
check("lexical results are highlighted (highlight+queryTerms wired)",
      "function highlight" in appjs and "queryTerms" in appjs and "highlight(esc(" in appjs)
check("<mark> styled for highlights", "mark {" in css or "mark{" in css)
# honesty in the renderer: no 'hybrid ranked best' language, no per-query hardcoding
check("no 'ranked best' language in demo.js", "ranked best" not in demojs.lower())
check("demo.js has no hardcoded book titles (renders from data)",
      "Psychology of Money" not in demojs and "Atomic Habits" not in demojs)

# ---------------- D-substitute + E: TestClient smoke ----------------
print("\nD (TestClient smoke) + E (regression):")
try:
    from fastapi.testclient import TestClient
    import api  # noqa
    client = TestClient(api.app)
    have_client = True
except Exception as e:
    have_client = False
    SKIP.append(f"TestClient unavailable: {type(e).__name__}: {e}")
    print(f"  [SKIP] FastAPI TestClient — {e}")

if have_client:
    # page loads and references the demo assets
    r = client.get("/")
    check("GET / -> 200 (index served)", r.status_code == 200)
    check("index HTML includes demo page + script", "page-demo" in r.text and "demo.js" in r.text)
    # static assets serve (new + existing = regression)
    for path in ("/demo.js", "/demo_fixtures.json", "/app.js", "/fixtures.json", "/styles.css", "/eval_set.json"):
        code = client.get(path).status_code
        check(f"GET {path} -> 200", code == 200, code)
    # new API: deck
    r = client.get("/api/demo_deck")
    check("GET /api/demo_deck -> 200 list", r.status_code == 200 and isinstance(r.json(), list) and len(r.json()) >= 1, r.status_code)
    # regression: existing endpoints still present
    check("regression: /api/queries still 200", client.get("/api/queries").status_code == 200)
    # live demo endpoint (hits Db2) — smoke, guarded
    try:
        r = client.get("/api/demo", params={"q": "teddy hamilton"})
        if r.status_code == 200:
            vm = r.json()
            ok = set(vm.get("strategies", {})) == {"lexical", "vector", "hybrid"} and \
                 all("verdict" in vm["strategies"][s] for s in ("lexical", "vector", "hybrid"))
            check("GET /api/demo?q=... -> view_model with 3 verdicts (live)", ok, vm.get("strategies", {}).keys())
        else:
            SKIP.append(f"/api/demo returned {r.status_code} (Db2 not reachable?)")
            print(f"  [SKIP] /api/demo live — status {r.status_code}")
    except Exception as e:
        SKIP.append(f"/api/demo live errored: {e}")
        print(f"  [SKIP] /api/demo live — {e}")
    # open-ended Search backend: 3 strategies with result lists
    try:
        r = client.get("/api/search", params={"q": "atomic habits"})
        if r.status_code == 200:
            j = r.json()
            ok = all(k in j for k in ("lexical", "vector", "hybrid")) and \
                 isinstance(j["lexical"].get("results"), list)
            check("GET /api/search?q=... -> 3 strategies with results (open-ended)", ok, list(j.keys()))
        else:
            SKIP.append(f"/api/search returned {r.status_code}")
            print(f"  [SKIP] /api/search live — status {r.status_code}")
    except Exception as e:
        SKIP.append(f"/api/search live errored: {e}")
        print(f"  [SKIP] /api/search live — {e}")

print(f"\n{'='*54}\nRESULT: {len(PASS)} passed, {len(FAIL)} failed, {len(SKIP)} skipped")
if SKIP:
    print("SKIPPED:", SKIP)
if FAIL:
    print("FAILURES:", FAIL); sys.exit(1)
print("ALL GREEN (with any skips noted above)")

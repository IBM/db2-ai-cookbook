#!/usr/bin/env python3
"""Phase-2 D — REAL headless-browser E2E (Playwright + chromium) against the
offline static UI. Serves ui/static on a local port, drives the Demo page, and
asserts runtime behavior a static check can't: no console errors, tab switching
(the [hidden] fix), 3 panels, the Simple/Technical toggle, scoreboard increment,
the no-result path, and that the nav tabs do not overlap.

Run: .venv/bin/python tests/test_demo_e2e.py
"""
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
STATIC = os.path.join(REPO, "ui", "static")
PORT = 8137
URL = f"http://127.0.0.1:{PORT}/"

PASS, FAIL = [], []
def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + ("" if cond else f"  << {detail}"))

def overlap(a, b):
    if not a or not b:
        return False
    return not (a["x"] + a["width"] <= b["x"] or b["x"] + b["width"] <= a["x"] or
                a["y"] + a["height"] <= b["y"] or b["y"] + b["height"] <= a["y"])

INSTALL_HINT = ('  pip install -e ".[test]" && python -m playwright install chromium')

# Skip cleanly when the optional test deps are absent. Checked BEFORE starting the
# server so a fresh clone reports a one-line SKIP instead of an unhandled ImportError
# traceback (which is what happened previously — the import sat inside the try whose
# finally killed the server).
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print(f"SKIP — playwright not installed. Install the test extras:\n{INSTALL_HINT}")
    sys.exit(0)

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1",
                        "--directory", STATIC], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(50):
        try:
            urllib.request.urlopen(URL, timeout=1); break
        except Exception:
            time.sleep(0.1)

    with sync_playwright() as p:
        # playwright the package can be installed while the browser binary is not —
        # the usual state right after `pip install`. Skip with the fix, don't crash.
        try:
            browser = p.chromium.launch()
        except Exception as e:
            if "executable doesn't exist" in str(e).lower() or "playwright install" in str(e).lower():
                print(f"SKIP — chromium not downloaded. Run:\n{INSTALL_HINT}")
                srv.terminate()
                sys.exit(0)
            raise
        page = browser.new_page(viewport={"width": 1200, "height": 900})
        # JS errors (real) vs benign network 404s. app.js/demo.js probe /api/* to
        # detect live-vs-offline; on the static server those 404 by design.
        errors, bad404 = [], []
        page.on("console", lambda m: errors.append(m.text)
                if (m.type == "error" and "Failed to load resource" not in m.text) else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("response", lambda r: bad404.append(r.url) if r.status == 404 else None)

        page.goto(URL, wait_until="networkidle")
        page.wait_for_selector("#tabs .tab")

        # nav tabs do not overlap each other (the reported bug)
        boxes = [t.bounding_box() for t in page.query_selector_all("#tabs .tab")]
        check("5 nav tabs present", len(boxes) == 5, len(boxes))
        pairwise_ok = all(not overlap(boxes[i], boxes[j])
                          for i in range(len(boxes)) for j in range(i + 1, len(boxes)))
        check("nav tabs do not overlap each other", pairwise_ok, boxes)

        # default: Start here visible, others hidden
        check("default page-start visible", page.is_visible("#page-start"))
        check("default page-search hidden", not page.is_visible("#page-search"))
        check("default page-demo hidden", not page.is_visible("#page-demo"))

        # switch to Demo — the [hidden]-override fix: search must fully hide
        page.click('.tab[data-page="demo"]')
        check("Demo tab shows #page-demo", page.is_visible("#page-demo"))
        check("Demo tab HIDES #page-search (no page overlap)", not page.is_visible("#page-search"))
        check("Demo tab HIDES #page-eval", not page.is_visible("#page-eval"))
        db = page.query_selector("#page-demo").bounding_box()
        sb_ = page.query_selector("#page-search").bounding_box()  # hidden -> None
        check("hidden page-search has no box (truly display:none)", sb_ is None, sb_)

        # chips render; click first -> exactly 3 panels + scenario
        page.wait_for_selector(".dchip")
        chips = page.query_selector_all(".dchip")
        check("demo chips rendered (>=6)", len(chips) >= 6, len(chips))
        chips[0].click()
        page.wait_for_selector(".dpanel")
        check("exactly 3 strategy panels", len(page.query_selector_all(".dpanel")) == 3,
              len(page.query_selector_all(".dpanel")))
        check("scenario caption shown", page.is_visible("#demo-scenario") and
              len(page.inner_text("#demo-scenario").strip()) > 0)
        check("verdicts show icon + text (not color alone)",
              all(len(v.inner_text().strip()) > 1 for v in page.query_selector_all(".dverdict")))

        # Simple/Technical toggle shows/hides technical fields
        check("technical fields hidden in Simple mode", len(page.query_selector_all(".dtech")) == 0,
              len(page.query_selector_all(".dtech")))
        page.check("#demo-tech")
        check("technical fields appear in Technical mode", len(page.query_selector_all(".dtech")) == 3,
              len(page.query_selector_all(".dtech")))
        page.uncheck("#demo-tech")

        # scoreboard increments across successive queries
        rows1 = len(page.query_selector_all(".dsb-matrix tbody tr"))
        chips[2].click()
        page.wait_for_timeout(150)
        rows2 = len(page.query_selector_all(".dsb-matrix tbody tr"))
        check("scoreboard increments across queries", rows2 == rows1 + 1, f"{rows1}->{rows2}")

        # Shuffle: pulls a NEW set of golden queries (3/type), resets the scoreboard, still clickable
        base = sorted(c.inner_text() for c in page.query_selector_all(".dchip .dchip-q"))
        page.click("#demo-shuffle"); page.wait_for_timeout(120)
        newset = sorted(c.inner_text() for c in page.query_selector_all(".dchip .dchip-q"))
        types = [c.inner_text().strip().lower() for c in page.query_selector_all(".dchip .dchip-t")]
        check("shuffle keeps 9 chips", len(newset) == 9, len(newset))
        check("shuffle pulls a NEW set of queries", newset != base, "same set after shuffle")
        check("shuffle keeps 3 per type", sorted(types) == ["lexical"] * 3 + ["mixed"] * 3 + ["semantic"] * 3, types)
        check("shuffle resets the scoreboard", len(page.query_selector_all(".dsb-matrix tbody tr")) == 0)
        page.query_selector_all(".dchip")[0].click(); page.wait_for_selector(".dpanel")
        check("chips still work after shuffle", len(page.query_selector_all(".dpanel")) == 3)

        # Representative set: restores the curated set -> scoreboard only (no per-type breakdown)
        page.click("#demo-representative"); page.wait_for_timeout(120)
        repset = sorted(c.inner_text() for c in page.query_selector_all(".dchip .dchip-q"))
        check("representative restores the curated set", repset == base, "representative set differs from initial")
        check("representative fills scoreboard with all 9",
              len(page.query_selector_all(".dsb-matrix tbody tr")) == 9)
        check("representative shows scoreboard only (no breakdown)", page.query_selector(".rep") is None)

        # demo search box is display-only: no typing; selecting a chip fills it
        check("demo search box is readonly (no typing)",
              page.eval_on_selector("#demo-search", "e => e.readOnly") is True)
        page.query_selector_all(".dchip")[0].click(); page.wait_for_timeout(120)
        check("selecting a chip fills the search box", page.input_value("#demo-search") != "")

        # regression: other tabs still work (Search is now open-ended — no eval deck)
        page.click('.tab[data-page="search"]')
        check("Search tab renders open-ended box (deck removed)",
              page.is_visible("#page-search") and page.is_visible("#searchbox")
              and page.query_selector("#deck-list") is None)
        page.click('.tab[data-page="eval"]')
        check("Golden-eval tab still renders cards", page.is_visible("#page-eval") and
              len(page.query_selector_all(".eval-card")) >= 1)

        # no real JS errors; 404s only for the expected live-probe endpoints
        check("no JS errors (pageerror / non-network console errors)", not errors, errors)
        unexpected404 = [u for u in bad404
                         if not (u.endswith("/api/queries") or u.endswith("/api/demo_deck"))]
        check("only expected live-probe /api 404s (offline fallback by design)",
              not unexpected404, unexpected404)
        browser.close()
finally:
    srv.terminate()

print(f"\n{'='*54}\nRESULT: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILURES:", FAIL); sys.exit(1)
print("ALL GREEN")

# Tests

Plain scripts — no pytest, no runner. Each prints `RESULT: N passed, M failed`
and exits non-zero on failure. Run one with:

```bash
DB2_HOST=local PYTHONPATH=src python tests/<name>.py
```

Some tests need extra dependencies or the live stack. They **skip cleanly**
(exit 0 with a one-line reason) when something is missing, so a fresh clone can
run all six and see exactly what it's missing rather than a traceback.

## One-time: install the test extras

The runtime install (`pip install -e .`) intentionally omits the browser
automation stack. For the UI tests:

```bash
pip install -e ".[test]"          # playwright + httpx
python -m playwright install chromium   # ~150 MB browser binary
```

## The suites

| Test | Needs | What it checks |
|---|---|---|
| `test_core_unit.py` | — (ibm_db for parts 1–2) | `keywords()` stopwords + fallback, `embed_query()`, `evalset.resolve()`, and `.env.example`↔`core.py`↔`2_search.sql` config coherence |
| `test_rerank.py` | — | reranker scoring logic (HTTP monkeypatched) |
| `test_demo_view.py` | — | outcome→verdict translation (uses committed fixtures) |
| `test_demo_ui.py` | `.[test]` (httpx) | FastAPI `TestClient` API smoke |
| `test_understanding.py` | `.[test]` + Db2 (guarded) | query-understanding layer |
| `test_demo_e2e.py` | `.[test]` + chromium | real headless-browser E2E of the offline UI |
| `test_fixture_consistency.py` | Db2 + embedding server | frozen fixtures & demo scenarios match the live engine |

## Run everything

```bash
for t in tests/test_*.py; do
  echo "== $t =="
  DB2_HOST=local PYTHONPATH=src python "$t" || echo "  ^ FAILED"
done
```

`test_fixture_consistency.py` is the drift guard: run it after any corpus, weight,
or demo-deck change — it fails if `ui/static/*.json` or a curated scenario no
longer matches what Db2 actually returns.

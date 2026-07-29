# Demo UI — Hybrid Search on Db2 12.1.5

A minimalist web demo for a mixed room (executives, customers, developers) on a
projector. Four tabs: **Search**, **Demo**, **Golden eval set**, **Architecture**.

## Run it (one command, offline)

```bash
./ui/run.sh                 # http://127.0.0.1:8000  — static page + frozen fixtures
```

The offline talk path needs **no Db2, no embedding server, no pip** — just Python's
stdlib server reading `static/*.json`. Robust on a conference laptop.

```bash
./ui/run.sh --live          # FastAPI backend hits the real engine; Swagger at /docs
```

Live mode is needed for ad-hoc typed queries (they hit Db2) and the Search-tab
**Rerank** toggle.

## The tabs

- **Search** — type anything; see the top-3 **Hybrid** results, each tagged with
  which strategy found it (**Lexical** / **Semantic**) and at what rank in that
  strategy. Toggles: **Rerank** (post-fusion cross-encoder; live mode) and **Show
  scores** (raw BM25/cosine + normalized fusion contribution).
- **Demo** — *"Will search find my book?"* A left rail of example queries; each runs
  through all three strategies at once, translated to a plain verdict
  (found / wrong book / nothing). A session **scoreboard** shows coverage; **Shuffle**
  draws a fresh set of golden queries, **Representative set** loads the curated one.
- **Golden eval set** — the test questions behind the demo, each with its gold answer.
- **Architecture** — three flat diagram views (Components · Ingestion · Search funnel),
  drawn from the real system.

## Refreshing the frozen data

Fixtures are frozen results of every demo query. Regenerate them whenever the corpus,
embedding model, or fusion knobs change:

```bash
./ui/build_fixtures.sh                     # -> static/fixtures.json  (Search-tab curated set)
DB2_HOST=local python build_demo.py        # -> static/demo_fixtures.json  (Demo tab)
DB2_HOST=local python build_eval_set.py    # -> static/eval_set.json  (Golden eval tab)
```

Assets are cache-busted (`?v=N` in `index.html`) — a hard refresh loads the latest CSS/JS.

## Files

```
run.sh              one-command launcher (offline default | --live)
api.py              live backend (--live); same JSON shape as the fixtures
build_fixtures.py   freeze the curated Search set  -> static/fixtures.json
build_demo.py       freeze the Demo view-models    -> static/demo_fixtures.json
build_eval_set.py   freeze the golden eval set     -> static/eval_set.json
demo_view.py        outcome-translation (verdicts + book labels)
queries.json · demo_queries.json   curated decks + gold IDs
static/             index.html · styles.css · app.js · demo.js · arch.js · *.json
```

The search engine and the gated, score-normalized fusion live in
[`../src/hybrid_search/core.py`](../src/hybrid_search/core.py) (with
`understanding.py` for query cleaning and `rerank.py` for the optional reranker).
The fusion is **not** RRF — each leg's score is normalized and low-confidence legs are
gated out before a weighted sum. `scripts/eval.py` scores the golden set, not these
fixtures.

## Honesty

No weights, gates, chunk text, or results were tuned to make hybrid win. Ranks are
whatever the engine returns; the curated sets span the failure modes (exact-name,
paraphrase, and agree cases), including cases where hybrid does *not* win.

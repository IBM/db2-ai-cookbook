#!/usr/bin/env python3
"""Live backend for the demo (`./ui/run.sh --live`) — a thin wrapper over the
search engine returning the SAME JSON shape as fixtures.json, so the frontend is
identical offline or live. The default demo is offline (static page + fixtures);
this exists for ad-hoc queries during Q&A."""

import json
import logging
import os
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
import ibm_db

from hybrid_search import core as h
from hybrid_search import understanding as qu   # adaptive query-understanding layer
from hybrid_search import rerank as rr          # optional post-fusion cross-encoder stage
import build_fixtures as bf   # responses_for()
import demo_view as dv         # outcome-translation (verdicts + book labels)

# Log hybrid_search.core's SQL to the uvicorn console (reuse uvicorn's handler; fall
# back to a basic one if run standalone).
_uvicorn_handlers = logging.getLogger("uvicorn").handlers
if _uvicorn_handlers:
    h.log.handlers = _uvicorn_handlers
    h.log.propagate = False
else:
    logging.basicConfig(level=logging.INFO)
    h.log.propagate = True
h.log.setLevel(logging.INFO)

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "queries.json")) as f:
    DECK = json.load(f)
GOLD = {item["query"]: set(item["gold_chunk_ids"]) for item in DECK}

# Demo view (additive): its own deck + a book-id -> title/author lookup.
with open(os.path.join(HERE, "demo_queries.json")) as f:
    DEMO_DECK = json.load(f)
DEMO_GOLD = {d["query"]: set(d["gold_chunk_ids"]) for d in DEMO_DECK}
DEMO_ITEM = {d["query"]: d for d in DEMO_DECK}
# corpus.csv sits at <repo>/data/ when run from the repo, but --live runs from a
# staged copy (/tmp/hybrid-ui-<port>) where run.sh drops it at <stage>/data/. Try both,
# and say so when neither hits: without it label_for() silently falls back to parsing
# "Title by Author." off the chunk text, which is easy to mistake for working.
_CORPUS = next(
    (p for p in (os.path.join(HERE, "data", "corpus.csv"),
                 os.path.join(os.path.dirname(HERE), "data", "corpus.csv"))
     if os.path.exists(p)), None)
if _CORPUS:
    BOOK_LOOKUP = dv.load_book_lookup(_CORPUS)
else:
    BOOK_LOOKUP = {}
    logging.getLogger("uvicorn.error").warning(
        "corpus.csv not found under %s — book titles fall back to text parsing.", HERE)

app = FastAPI(title="Db2 Hybrid Search Demo", docs_url="/docs")


@app.get("/api/queries")
def queries():
    """The curated demo deck (query, type, gold chunk IDs, note)."""
    return DECK


@app.get("/api/search")
def search(q: str = Query(..., description="search text"), k: int = bf.K,
           rerank: Optional[bool] = Query(None, description="override the post-fusion reranker")):
    """All three strategy responses for a query (lexical, vector, hybrid).
    gold_chunk_ids come from the curated set when the query matches one.
    The Search tab's hybrid results pass through the post-fusion reranker when
    requested via `rerank` (the tab's toggle); absent that, the RERANK_ON env
    default applies. The Demo tab never reranks."""
    do_rerank = rr.RERANK_ON if rerank is None else bool(rerank)
    gold = GOLD.get(q, set())
    conn = h.connect()
    try:
        modes = bf.responses_for(conn, q, gold, rerank=do_rerank)
    finally:
        ibm_db.close(conn)
    # If reranking was requested but the reranker was unreachable, say so explicitly
    # rather than pass off fusion order as "reranked" — the UI shows an error.
    fell_back = do_rerank and modes.get("hybrid", {}).get("rerank_fell_back", False)
    out = {"query": q, "gold_chunk_ids": sorted(gold),
           "reranked": do_rerank and not fell_back, **modes}
    if fell_back:
        out["rerank_unavailable"] = True
    return out


@app.get("/api/smart_search")
def smart_search(q: str = Query(..., description="search text"), k: int = bf.K):
    """The shipped canonical path: extractive lexical cleaning always on, generative
    expansion gated by QU_MODE (default 'off'). Returns the ranked results plus the
    understanding metadata (route, whether the LLM fired, the two leg queries)."""
    conn = h.connect()
    try:
        ranked, meta = qu.smart_search(conn, q, k)
        results = [{"chunk_id": cid, "score": score,
                    "snippet": h.snippet(conn, cid)} for cid, score in ranked]
    finally:
        ibm_db.close(conn)
    return {"query": q, "mode": qu.MODE, "understanding": meta, "results": results}


@app.get("/api/demo_deck")
def demo_deck():
    """The curated demo deck (query, type, gold ids, scenario)."""
    return DEMO_DECK


@app.get("/api/demo")
def demo(q: str = Query(..., description="search text")):
    """Demo view model for a query: each strategy translated to a verdict
    (found / wrong / nothing) with the shown book's title + author."""
    gold = DEMO_GOLD.get(q, set())
    item = DEMO_ITEM.get(q, {"id": 0, "query": q, "query_type": None,
                             "query_class": "known_item", "scenario": "",
                             "gold_chunk_ids": sorted(gold)})
    conn = h.connect()
    try:
        responses = bf.responses_for(conn, q, gold)
    finally:
        ibm_db.close(conn)
    return dv.view_model(responses, item, BOOK_LOOKUP, k=bf.K)


class NoCacheHTML(StaticFiles):
    """StaticFiles, but HTML always revalidates. index.html carries the ?v= busters
    for the JS/CSS and nothing busts index.html itself, so a browser holding a stale
    copy pairs old markup with new scripts — startBoot() then finds no #start-canvas
    and returns silently, leaving a blank page and no console error. "no-cache" still
    permits a 304 via the ETag, so the revalidation is cheap."""

    def file_response(self, full_path, *args, **kwargs):
        resp = super().file_response(full_path, *args, **kwargs)
        if str(full_path).endswith(".html"):
            resp.headers["Cache-Control"] = "no-cache, must-revalidate"
        return resp


# Serve the same static UI; API routes above take precedence over this mount.
app.mount("/", NoCacheHTML(directory=os.path.join(HERE, "static"), html=True), name="static")

"""
hybrid_search/rerank.py — optional post-fusion cross-encoder reranking stage.

This lives in the APP layer, on top of Db2. Db2 returns the fused hybrid top-N;
this stage re-scores those candidates with a local cross-encoder (a llama-server
launched with --reranking on its own port) and cuts to the top-K shown to the user.
Db2 stays responsible for retrieval + fusion; reranking is a stage on top.

Off by default (RERANK_ON=0). When off, callers keep the fusion order untouched, so
the pipeline is byte-for-byte unchanged.

Robustness (this is a serving path):
  - ONE batched request per query (all uncached candidates in a single POST).
  - Wall-clock timeout; on any error/timeout fall back to the fusion order and log.
    Search must never fail because rerank did.
  - LRU score cache keyed by (normalized query, candidate id).

Config (env / .env, read via core.setting):
  RERANK_ON, RERANK_URL, RERANK_MODEL, RERANK_N, RERANK_K, RERANK_TIMEOUT,
  RERANK_DOC_CHARS, RERANK_PATH (endpoint override; else auto-detected).
"""
import json
import logging
import re
import time
import urllib.error
import urllib.request
from collections import OrderedDict

from . import core as h   # for setting()

log = logging.getLogger("hybrid_search.rerank")

RERANK_ON        = h.setting("RERANK_ON", "0").strip().lower() in ("1", "true", "yes", "on")
RERANK_URL       = h.setting("RERANK_URL", "http://127.0.0.1:8087").rstrip("/")
RERANK_MODEL     = h.setting("RERANK_MODEL", "reranker")
RERANK_N         = int(h.setting("RERANK_N", "25"))          # fusion candidates to rerank
RERANK_K         = int(h.setting("RERANK_K", "3"))           # final count returned to UI
RERANK_TIMEOUT   = float(h.setting("RERANK_TIMEOUT", "8.0"))  # seconds, wall clock
RERANK_DOC_CHARS = int(h.setting("RERANK_DOC_CHARS", "1200"))  # truncate long candidate text
RERANK_PATH      = h.setting("RERANK_PATH", "")              # e.g. '/v1/reranking'; else auto-detect

_CACHE_MAX = 4096
_cache = OrderedDict()      # (qnorm, cid) -> relevance_score
_endpoint = None            # detected endpoint path, cached


# ---------- helpers ----------
def _normalize(q):
    return re.sub(r"\s+", " ", str(q or "").strip().lower())[:500]


def _doc(text):
    return re.sub(r"\s+", " ", str(text or "").strip())[:RERANK_DOC_CHARS]


def _cache_get(key):
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    return None


def _cache_put(key, val):
    _cache[key] = val
    _cache.move_to_end(key)
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)


def clear_cache():
    _cache.clear()


def _request(path, query, documents, timeout):
    body = json.dumps({"model": RERANK_MODEL, "query": query,
                       "documents": documents, "top_n": len(documents)}).encode()
    req = urllib.request.Request(RERANK_URL + path, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _detect_endpoint():
    """llama.cpp serves the reranking endpoint under different paths across builds.
    Probe once (cheap) and cache. Honour RERANK_PATH override if set."""
    global _endpoint
    if RERANK_PATH:
        _endpoint = RERANK_PATH
        return _endpoint
    if _endpoint:
        return _endpoint
    for path in ("/v1/reranking", "/rerank", "/v1/rerank", "/reranking"):
        try:
            out = _request(path, "ping", ["pong"], timeout=4)
            if "results" in out or isinstance(out, list):
                _endpoint = path
                log.info("rerank endpoint detected: %s", path)
                return path
        except Exception:
            continue
    _endpoint = "/v1/reranking"   # sane default; the real call will surface errors
    return _endpoint


def _post_scores(query, documents):
    """One batched request. Returns [relevance_score] aligned to `documents` order.
    Raises on transport/parse error or if any document went unscored."""
    out = _request(_detect_endpoint(), query, documents, timeout=RERANK_TIMEOUT)
    results = out.get("results") if isinstance(out, dict) else out
    scores = [None] * len(documents)
    for item in results:
        idx = item["index"]
        if 0 <= idx < len(scores):
            scores[idx] = float(item["relevance_score"])
    if any(s is None for s in scores):
        raise ValueError("reranker did not score every document")
    return scores


# ---------- public API ----------
def rerank(query, candidates, n=None, k=None):
    """Re-score fusion candidates with the cross-encoder and return the top-K.

    candidates : [(cid, text), ...] in fusion order (best first).
    Returns (reordered, meta):
      reordered : [(cid, text, rerank_score), ...] sorted by score DESC, cut to k.
                  rerank_score is unbounded and may be negative. On fallback the
                  fusion order is preserved and scores are None.
      meta      : {reranked, fell_back, n, cached, latency_ms}
    Never raises: any reranker failure falls back to the fusion order.
    """
    n = RERANK_N if n is None else n
    k = RERANK_K if k is None else k
    pool = list(candidates)[:n]
    meta = {"reranked": False, "fell_back": False, "n": len(pool), "cached": 0, "latency_ms": 0.0}
    if not pool:
        return [], meta

    t0 = time.perf_counter()
    qn = _normalize(query)
    scores = [None] * len(pool)
    miss_idx, miss_docs = [], []
    for i, (cid, text) in enumerate(pool):
        cached = _cache_get((qn, cid))
        if cached is not None:
            scores[i] = cached
            meta["cached"] += 1
        else:
            miss_idx.append(i)
            miss_docs.append(_doc(text))

    try:
        if miss_docs:
            got = _post_scores(query, miss_docs)
            for j, i in enumerate(miss_idx):
                scores[i] = got[j]
                _cache_put((qn, pool[i][0]), got[j])
        meta["reranked"] = True
    except Exception as e:                       # timeout / transport / bad payload
        log.warning("rerank fell back to fusion order: %s", e)
        meta["fell_back"] = True
        meta["latency_ms"] = (time.perf_counter() - t0) * 1000
        return [(cid, text, None) for cid, text in pool[:k]], meta

    # descending by score; stable tie-break preserves the fusion order on ties.
    order = sorted(range(len(pool)), key=lambda i: (-scores[i], i))
    reordered = [(pool[i][0], pool[i][1], scores[i]) for i in order[:k]]
    meta["latency_ms"] = (time.perf_counter() - t0) * 1000
    return reordered, meta

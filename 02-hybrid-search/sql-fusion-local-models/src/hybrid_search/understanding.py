"""
hybrid_search/understanding.py — the adaptive query-understanding layer.

It sits in front of the fusion engine (core.hybrid_split) and decides, per query,
how much work each query deserves. Two things happen:

  1. EXTRACTIVE LEXICAL CLEANING — always on, pure SQL, no LLM. Strips filler and
     stopwords while preserving rare tokens/numbers/proper nouns. Measured a pure
     win on the golden set (semantic MRR +0.035, topical Recall@5 +0.044, zero
     regression on keyword/mixed) — so we apply it to EVERY query, unconditionally.

  2. GENERATIVE SEMANTIC EXPANSION — gated, local Qwen via Db2 TEXT_GENERATION.
     Built, robust, and OFF by default. When it fires we AUGMENT (embed raw query +
     expansion), never replace — replace regressed semantic MRR 0.62->0.48.

Robustness: the SQL procedure has a CONTINUE HANDLER that falls back to the raw
query on any LLM error, and every Python entry point wraps the call so search never
fails because the model was slow, down, or returned junk. Feature-gated calls are
memoized in MYSCHEMA.QU_CACHE.

The decision the evidence forced, stated plainly: we do NOT put the LLM on the hot
path just because we built it. On the golden set the deterministic cleaner ALONE was
the best config on every metric (semantic MRR 0.656, topical Recall@5 0.615, Hits@1
0.875) at ~0 cost; adding generation was neutral at best and, on the weak-retrieval
tail CRAG targets, actively *hurt* semantic queries (0.656 -> 0.604). So the SHIPPED
default is mode="off": cleaner on 100% of queries, zero LLM. The generative gates
(gated/crag) stay one env flag away for a larger / longer-document corpus where
expansion has more to gain — re-run scripts/query-understanding/qu_eval.py to decide.
"""
import ibm_db
from . import core as h

MODE     = h.setting("QU_MODE", "off").lower()           # off | gated | crag  (see module docstring)
SIM_GATE = float(h.setting("QU_SIM_GATE", "0.60"))       # CRAG: fire LLM below this top cosine
GEN_MODEL = f"{h.SCHEMA}.QU_GEN"

HYDE_PROMPT = ("You help search an audiobook library. Given a rough query, write a one-sentence "
               "back-cover-style description of the book the person is probably after — its topic, "
               "themes, and what it teaches — WITHOUT reusing their exact words where you can avoid it. "
               "20-30 words. Reply as JSON with one field q. Query: ")


def _scalar(conn, sql, arg):
    st = ibm_db.prepare(conn, sql)
    ibm_db.bind_param(st, 1, arg)
    ibm_db.execute(st)
    row = ibm_db.fetch_tuple(st)
    return row[0] if row else None


def lexical_of(conn, query):
    """Extractive keyword query (pure SQL, no LLM). Pure win — apply to every query."""
    try:
        out = _scalar(conn, "VALUES MYSCHEMA.QU_LEXICAL(CAST(? AS VARCHAR(4000)))", query)
        return out.strip() if out and out.strip() else query
    except Exception:
        return query


def route_of(conn, query):
    return _scalar(conn, "VALUES MYSCHEMA.QU_ROUTE(CAST(? AS VARCHAR(4000)))", query)


def llm_expand(conn, query):
    """Force a generative semantic rewrite. Falls back to the raw query on any error."""
    try:
        sql = "VALUES TRIM(JSON_VALUE(TEXT_GENERATION(CAST(? AS VARCHAR(4000)) USING " + GEN_MODEL + "), '$.q'))"
        out = _scalar(conn, sql, HYDE_PROMPT + query)
        return out.strip() if out and out.strip() else query
    except Exception:
        return query


def understand(conn, query):
    """Feature-gated understanding via MYSCHEMA.QU_UNDERSTAND (route -> conditional
    generation, cached). Returns dict; hard fallback to raw on any failure."""
    try:
        _, _, o_route, o_lex, o_sem, o_llm = ibm_db.callproc(
            conn, "MYSCHEMA.QU_UNDERSTAND", (query, "", "", "", 0))
        return {"route": o_route, "lexical_q": o_lex or query,
                "semantic_q": o_sem or query, "llm_fired": int(o_llm or 0)}
    except Exception as e:
        return {"route": "fallback", "lexical_q": query, "semantic_q": query,
                "llm_fired": 0, "error": str(e)}


def _augment(query, expansion):
    """Vector-leg text when the LLM fired: keep the raw query (already strong) and
    ADD the HyDE expansion, never swap it out."""
    return (query + ". " + expansion) if expansion and expansion.strip() and expansion != query else query


# ---------- search modes ----------
def gated_search(conn, query, limit=10):
    """Feature gating: the SQL router decides whether to spend the LLM (cached)."""
    u = understand(conn, query)
    ranked = h.hybrid_split(conn, u["lexical_q"], _augment(query, u["semantic_q"]) if u["llm_fired"] else query, limit)
    return ranked, u


def confidence_search(conn, query, limit=10, sim_ok=SIM_GATE):
    """CRAG-style confidence gating: always clean the lexical leg (pure win), run
    the vector leg on the raw query, and invoke the LLM only when the vector leg
    looks unsure (top cosine below sim_ok)."""
    lex = lexical_of(conn, query)                      # pure-win cleaner, always
    vtop = h.vector(conn, query, 1)
    if vtop and vtop[0][1] >= sim_ok:                  # confident -> no LLM
        return (h.hybrid_split(conn, lex, query, limit),
                {"route": "confident", "llm_fired": 0, "lexical_q": lex, "semantic_q": query})
    exp = llm_expand(conn, query)                      # weak tail -> expand + augment
    fired = 1 if exp and exp != query else 0
    return (h.hybrid_split(conn, lex, _augment(query, exp), limit),
            {"route": "crag_expanded", "llm_fired": fired, "lexical_q": lex, "semantic_q": _augment(query, exp)})


def smart_search(conn, query, limit=10, mode=None):
    """The recommended production entry point. Extractive cleaner always on; LLM
    generation gated per `mode` (env QU_MODE; default 'off'). Returns (ranked, meta).

      off   : cleaned lexical + raw vector, never any LLM   [default — best on this corpus]
      gated : route-based feature gate (fires ~62%, memoized)
      crag  : confidence gate, fires only on weak retrieval (~4%)
    """
    mode = (mode or MODE).lower()
    if mode == "off":
        lex = lexical_of(conn, query)
        return (h.hybrid_split(conn, lex, query, limit),
                {"route": "clean_only", "llm_fired": 0, "lexical_q": lex, "semantic_q": query})
    if mode == "gated":
        return gated_search(conn, query, limit)
    return confidence_search(conn, query, limit)       # crag (default)


def clear_cache(conn):
    ibm_db.exec_immediate(conn, "DELETE FROM MYSCHEMA.QU_CACHE")

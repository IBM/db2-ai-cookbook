"""
hybrid_search/core.py — the hybrid-search engine, used by eval.py (metrics) and the
live UI (ui/api.py). It has no command line of its own.

Three retrieval legs, all in Db2:
  - lexical : Db2 Text Search keyword match, ranked by BM25 SCORE()
  - vector  : Db2 VECTOR column vs the query embedded by the local model (TO_EMBEDDING)
  - hybrid  : a GATED, SCORE-NORMALIZED fusion of the two

Why not plain RRF?  RRF fuses on rank only and throws away each leg's
confidence, so a leg that is essentially guessing (vectors on an exact error
code, BM25 on a pure paraphrase) injects its top guesses with the same weight as
the other leg's real hits — and they tie. Instead we:
  1. carry each leg's real score (BM25 SCORE, cosine similarity),
  2. max-normalize it (s / max) within the query's candidate pool,
  3. GATE a leg out when its best score is below a threshold (a near-random leg
     contributes nothing), and
  4. take a weighted sum of the surviving normalized scores.
A document found by *both* legs is reinforced; a noisy leg is muted.
"""

import logging
import os
import ibm_db

# SQL sent to Db2 is logged here at INFO. Callers decide where it goes: the live
# UI (ui/api.py) routes this to the uvicorn console; the CLI/eval leave it
# unconfigured, so nothing is printed unless you opt in.
log = logging.getLogger("hybrid_search")


def _log_sql(sql, params=(), level=logging.INFO):
    """Log one statement (whitespace collapsed to a single line) plus its bound
    parameter values, so the log shows exactly what Db2 receives."""
    flat = " ".join(sql.split())
    if params:
        log.log(level, "Db2 SQL: %s -- params=%r", flat, list(params))
    else:
        log.log(level, "Db2 SQL: %s", flat)

# --- settings (.env best-effort; defaults work for local mode) ---------------
# Find the nearest .env by walking up from this module AND from cwd. The dirname
# depth to the repo root differs between the normal layout (repo/src/hybrid_search)
# and the staged live layout (/tmp/hybrid-ui/hybrid_search), so we can't hard-code a
# single parent level — we probe several. (Bug history: a fixed 2-level ROOT pointed
# at src/.env, so .env only loaded when cwd happened to be the repo root, and the
# fixture builders / staged server silently ran on code defaults instead.)
def _find_env():
    seen = set()
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(5):                       # module dir, then walk up
        p = os.path.join(d, ".env")
        if p not in seen:
            seen.add(p)
            if os.path.exists(p):
                return p
        d = os.path.dirname(d)
    return ".env" if os.path.exists(".env") else None   # fall back to cwd

_env = _find_env()
if _env:
    try:
        for _line in open(_env):
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip().strip("\"'"))
    except OSError:
        pass


def setting(name, default=None):
    return os.environ.get(name, default)


DATABASE = setting("DB2_DATABASE", "sample")
HOST     = setting("DB2_HOST", "localhost")
PORT     = setting("DB2_PORT", "50000")
USER     = setting("DB2_USER", "db2inst1")
PASSWORD = setting("DB2_PASSWORD")
# NOT user-configurable, despite reading the environment: scripts/1_ingest.sql and
# 2_search.sql hardcode MYSCHEMA.CHUNKS, and a .sql file cannot read .env. Overriding
# these would point the engine at a table the SQL never created. Deliberately absent
# from .env.example for that reason — to rename, edit the .sql scripts and these
# together. The env read is kept only so both sides can be moved in one place.
SCHEMA   = setting("DB2_SCHEMA", "myschema")
TABLE    = setting("DB2_TABLE", "chunks")
T        = f"{SCHEMA}.{TABLE}"
MODEL    = f"{SCHEMA}.{TABLE}_embed"

# Fusion knobs — tune these against eval.py, don't hand-pick.
# Defaults match .env.example and scripts/2_search.sql, so behaviour is identical
# with or without a .env. Corpus-specific: 0.3/0.7 was picked by the one-standard-
# error rule over a 5-fold-CV sweep on the shipped corpus (docs/eval-results.md).
POOL     = int(setting("HYBRID_POOL", "100"))       # candidates per leg before fusing (>= corpus = exhaustive)
W_LEX    = float(setting("HYBRID_W_LEX", "0.3"))    # weight of the keyword leg (only the ratio matters)
W_VEC    = float(setting("HYBRID_W_VEC", "0.7"))    # weight of the vector leg
VEC_GATE = float(setting("HYBRID_VEC_GATE", "0.0"))   # min top cosine to trust vectors (0 = no gating)
LEX_GATE = float(setting("HYBRID_LEX_GATE", "0.0"))   # min top BM25 score to trust keywords

# bge-small is asymmetric: passages are embedded raw (as ingested), but QUERIES
# are meant to carry a retrieval instruction. Applying it only to the query side
# markedly improves ranking. Set EMBED_QUERY_PREFIX='' to disable.
QUERY_PREFIX = setting("EMBED_QUERY_PREFIX",
                       "Represent this sentence for searching relevant passages: ")


def embed_query(query):
    """The text handed to TO_EMBEDDING for a query (adds bge's instruction)."""
    return QUERY_PREFIX + query


# Standard English function-word stoplist, applied when building the CONTAINS query.
# Db2 Text Search does NOT strip stopwords (verified: even a LANGUAGE en_US index keeps
# "the"/"with"/"and" searchable), so without this, filler OR'd into the keyword query
# matches broadly and pollutes the BM25 ranking. This is the analyzer stop-filter
# equivalent, done at query-build time — keywords() is the ONLY place CONTAINS is formed.
# Pure function words only: the bespoke domain/phrase cleaner (QU_LEXICAL) was removed.
STOPWORDS = frozenset("""
a an and are as at be been but by can could did do does for from had has have how
i if in into is it its me my no not of on or our so than that the their them then
there these they this to too was we were what when where which who whom why will
with would you your
""".split())


def keywords(query):
    """CONTAINS is implicit-AND, so OR the content words: any term can match, ranked by
    SCORE. English stopwords are dropped (see STOPWORDS) — Db2 Text Search keeps them
    searchable and OR-ing filler like "with"/"and" pollutes BM25. Falls back to all
    tokens when the query is nothing but stopwords, so CONTAINS is never empty."""
    toks = query.split()
    kept = [t for t in toks if t.lower().strip(".,!?;:'\"()[]") not in STOPWORDS]
    return " OR ".join(kept or toks) or query


def connect():
    """LOCAL mode (DB2_HOST empty/'local'): fast local connection as the instance
    owner. Otherwise a TCP connection from the .env credentials."""
    if not HOST or HOST.lower() == "local":
        return ibm_db.connect(DATABASE, "", "")
    dsn = (f"DATABASE={DATABASE};HOSTNAME={HOST};PORT={PORT};"
           f"PROTOCOL=TCPIP;UID={USER};PWD={PASSWORD};ConnectTimeout=10;")
    return ibm_db.connect(dsn, "", "")


def _rows(conn, sql, params):
    _log_sql(sql, params)
    stmt = ibm_db.prepare(conn, sql)
    for i, value in enumerate(params, start=1):
        ibm_db.bind_param(stmt, i, value)
    ibm_db.execute(stmt)
    out, row = [], ibm_db.fetch_tuple(stmt)
    while row:
        out.append((int(row[0]), float(row[1])))
        row = ibm_db.fetch_tuple(stmt)
    return out


def lexical(conn, query, limit=POOL):
    """Keyword leg → [(chunk_id, bm25_score)], best first."""
    sql = f"""
        SELECT chunk_id, SCORE(chunk_text, CAST(? AS VARCHAR(4000))) AS sc
        FROM {T} WHERE CONTAINS(chunk_text, CAST(? AS VARCHAR(4000))) = 1
        ORDER BY sc DESC FETCH FIRST {int(limit)} ROWS ONLY
    """
    kw = keywords(query)
    return _rows(conn, sql, [kw, kw])


def vector(conn, query, limit=POOL):
    """Vector leg → [(chunk_id, cosine_similarity)], best first.

    Ordering by the raw COSINE distance and fetching with APPROX lets Db2 serve
    this from the vector (ANN) index — a graph traversal instead of a full scan.
    The optimizer matches the index only when ORDER BY is on VECTOR_DISTANCE with
    the index's metric (COSINE); we still return 1 - distance as the similarity
    the fusion expects (lowest distance first == highest similarity first)."""
    sql = f"""
        WITH q (qv) AS (VALUES TO_EMBEDDING(CAST(? AS VARCHAR(4000)) USING {MODEL}))
        SELECT c.chunk_id, (1 - VECTOR_DISTANCE(c.embedding, q.qv, COSINE)) AS sim
        FROM {T} c, q
        ORDER BY VECTOR_DISTANCE(c.embedding, q.qv, COSINE)
        FETCH APPROX FIRST {int(limit)} ROWS ONLY
    """
    return _rows(conn, sql, [embed_query(query)])


def _normalized(gate):
    """SQL for a max-normalized score in (0,1] (each leg's best -> 1), or 0 when
    the leg's best score is below `gate` (gate it out as near-random).

    Max-normalization (s / max), not min-max: it keeps every candidate positive,
    so a relevant doc that happens to be a leg's *weakest* match isn't zeroed out
    and dropped from the fusion (min-max maps the lowest candidate to exactly 0)."""
    return (f"CASE WHEN MAX(s) OVER () < {gate} THEN 0 "
            f"WHEN MAX(s) OVER () <= 0 THEN 0 "
            f"ELSE s / MAX(s) OVER () END")


def hybrid(conn, query, limit=10):
    """Gated, score-normalized fusion → [(chunk_id, fused_score)], best first."""
    sql = f"""
        WITH
        q (qv) AS (VALUES TO_EMBEDDING(CAST(? AS VARCHAR(4000)) USING {MODEL})),
        lex0 AS (
            SELECT chunk_id, SCORE(chunk_text, CAST(? AS VARCHAR(4000))) AS s
            FROM {T} WHERE CONTAINS(chunk_text, CAST(? AS VARCHAR(4000))) = 1
            ORDER BY s DESC FETCH FIRST {POOL} ROWS ONLY),
        vec0 AS (
            SELECT c.chunk_id, (1 - VECTOR_DISTANCE(c.embedding, q.qv, COSINE)) AS s
            FROM {T} c, q
            ORDER BY VECTOR_DISTANCE(c.embedding, q.qv, COSINE)
            FETCH APPROX FIRST {POOL} ROWS ONLY),
        lex AS (SELECT chunk_id, {_normalized(LEX_GATE)} AS n FROM lex0),
        vec AS (SELECT chunk_id, {_normalized(VEC_GATE)} AS n FROM vec0)
        SELECT COALESCE(lex.chunk_id, vec.chunk_id) AS chunk_id,
               {W_LEX} * COALESCE(lex.n, 0) + {W_VEC} * COALESCE(vec.n, 0) AS score
        FROM lex FULL OUTER JOIN vec ON lex.chunk_id = vec.chunk_id
        ORDER BY score DESC, chunk_id ASC
        FETCH FIRST {int(limit)} ROWS ONLY
    """
    kw = keywords(query)
    return _rows(conn, sql, [embed_query(query), kw, kw])


def hybrid_split(conn, lexical_q, semantic_q, limit=10,
                 w_lex=None, w_vec=None, lex_gate=None, vec_gate=None):
    """Same gated fusion as hybrid(), but the keyword leg searches `lexical_q` and
    the vector leg embeds `semantic_q` — so a query-understanding gate can feed the
    two legs distinct queries. Behavior identical to hybrid() when both args equal.

    The fusion knobs default to the tuned globals but can be overridden per call, so
    the query-understanding router can adapt them per query (e.g. drop the lexical
    weight for a semantic paraphrase where keyword noise would demote the true hit)."""
    w_lex = W_LEX if w_lex is None else w_lex
    w_vec = W_VEC if w_vec is None else w_vec
    lex_gate = LEX_GATE if lex_gate is None else lex_gate
    vec_gate = VEC_GATE if vec_gate is None else vec_gate
    sql = f"""
        WITH
        q (qv) AS (VALUES TO_EMBEDDING(CAST(? AS VARCHAR(4000)) USING {MODEL})),
        lex0 AS (
            SELECT chunk_id, SCORE(chunk_text, CAST(? AS VARCHAR(4000))) AS s
            FROM {T} WHERE CONTAINS(chunk_text, CAST(? AS VARCHAR(4000))) = 1
            ORDER BY s DESC FETCH FIRST {POOL} ROWS ONLY),
        vec0 AS (
            SELECT c.chunk_id, (1 - VECTOR_DISTANCE(c.embedding, q.qv, COSINE)) AS s
            FROM {T} c, q
            ORDER BY VECTOR_DISTANCE(c.embedding, q.qv, COSINE)
            FETCH APPROX FIRST {POOL} ROWS ONLY),
        lex AS (SELECT chunk_id, {_normalized(lex_gate)} AS n FROM lex0),
        vec AS (SELECT chunk_id, {_normalized(vec_gate)} AS n FROM vec0)
        SELECT COALESCE(lex.chunk_id, vec.chunk_id) AS chunk_id,
               {w_lex} * COALESCE(lex.n, 0) + {w_vec} * COALESCE(vec.n, 0) AS score
        FROM lex FULL OUTER JOIN vec ON lex.chunk_id = vec.chunk_id
        ORDER BY score DESC, chunk_id ASC
        FETCH FIRST {int(limit)} ROWS ONLY
    """
    kw = keywords(lexical_q) or keywords(semantic_q)   # guard: never send an empty CONTAINS
    return _rows(conn, sql, [embed_query(semantic_q), kw, kw])


def hybrid_explain(conn, query, limit=10, lexical_q=None, semantic_q=None):
    """Like hybrid()/hybrid_split(), but also returns each leg's normalized
    contribution so the UI can show *why* a result ranked where it did. Same fusion
    SQL — no behavior change — just additional columns.

    Pass lexical_q/semantic_q to explain a split search (keyword leg on lexical_q,
    vector leg on semantic_q); both default to `query` for the single-query case.

    Returns [{chunk_id, lex_norm, vec_norm, fused}], best first. lex_norm/vec_norm
    are the max-normalized leg scores (0 if the leg was gated out or absent);
    fused = W_LEX*lex_norm + W_VEC*vec_norm (the value hybrid() orders by)."""
    lexical_q = query if lexical_q is None else lexical_q
    semantic_q = query if semantic_q is None else semantic_q
    sql = f"""
        WITH
        q (qv) AS (VALUES TO_EMBEDDING(CAST(? AS VARCHAR(4000)) USING {MODEL})),
        lex0 AS (
            SELECT chunk_id, SCORE(chunk_text, CAST(? AS VARCHAR(4000))) AS s
            FROM {T} WHERE CONTAINS(chunk_text, CAST(? AS VARCHAR(4000))) = 1
            ORDER BY s DESC FETCH FIRST {POOL} ROWS ONLY),
        vec0 AS (
            SELECT c.chunk_id, (1 - VECTOR_DISTANCE(c.embedding, q.qv, COSINE)) AS s
            FROM {T} c, q
            ORDER BY VECTOR_DISTANCE(c.embedding, q.qv, COSINE)
            FETCH APPROX FIRST {POOL} ROWS ONLY),
        lex AS (SELECT chunk_id, {_normalized(LEX_GATE)} AS n FROM lex0),
        vec AS (SELECT chunk_id, {_normalized(VEC_GATE)} AS n FROM vec0)
        SELECT COALESCE(lex.chunk_id, vec.chunk_id) AS chunk_id,
               COALESCE(lex.n, 0) AS lex_norm,
               COALESCE(vec.n, 0) AS vec_norm,
               {W_LEX} * COALESCE(lex.n, 0) + {W_VEC} * COALESCE(vec.n, 0) AS fused
        FROM lex FULL OUTER JOIN vec ON lex.chunk_id = vec.chunk_id
        ORDER BY fused DESC, chunk_id ASC
        FETCH FIRST {int(limit)} ROWS ONLY
    """
    kw = keywords(lexical_q) or keywords(semantic_q)
    params = [embed_query(semantic_q), kw, kw]
    _log_sql(sql, params)
    stmt = ibm_db.prepare(conn, sql)
    for i, value in enumerate(params, start=1):
        ibm_db.bind_param(stmt, i, value)
    ibm_db.execute(stmt)
    out, row = [], ibm_db.fetch_tuple(stmt)
    while row:
        out.append({"chunk_id": int(row[0]), "lex_norm": float(row[1]),
                    "vec_norm": float(row[2]), "fused": float(row[3])})
        row = ibm_db.fetch_tuple(stmt)
    return out


def gates(conn, query, lexical_q=None):
    """Which legs are gated out for this query (best score below threshold).
    Returns {'vector_gated': bool, 'lexical_gated': bool}. Pass lexical_q to probe
    the keyword leg with the cleaned query (what the split search actually runs)."""
    lex = lexical(conn, query if lexical_q is None else lexical_q, 1)
    vec = vector(conn, query, 1)
    return {
        "lexical_gated": (not lex) or lex[0][1] < LEX_GATE,
        "vector_gated":  (not vec) or vec[0][1] < VEC_GATE,
    }


def snippet(conn, chunk_id, width=90):
    sql = f"SELECT CAST(SUBSTR(chunk_text,1,{int(width)}) AS VARCHAR({int(width)})) AS s FROM {T} WHERE chunk_id = ?"
    _log_sql(sql, [chunk_id], level=logging.DEBUG)
    stmt = ibm_db.prepare(conn, sql)
    ibm_db.bind_param(stmt, 1, chunk_id)
    ibm_db.execute(stmt)
    row = ibm_db.fetch_tuple(stmt)
    return row[0].strip().replace("\n", " ") if row else ""


def cover(conn, chunk_id):
    """The book's cover-thumbnail path (relative to ui/static/), or '' if none.
    Stored in Db2 by 1_ingest.sql; the UI renders it beside the title."""
    sql = f"SELECT cover_url FROM {T} WHERE chunk_id = ?"
    _log_sql(sql, [chunk_id], level=logging.DEBUG)
    stmt = ibm_db.prepare(conn, sql)
    ibm_db.bind_param(stmt, 1, chunk_id)
    ibm_db.execute(stmt)
    row = ibm_db.fetch_tuple(stmt)
    return (row[0] or "").strip() if row else ""


def book_meta(conn, chunk_id):
    """Structured display fields for a result — title, author, a short description,
    and the cover path — all read from Db2's own columns. Lets the search UI render
    a proper card (bold title, author, description) instead of the raw chunk_text."""
    sql = (f"SELECT title, authors, "
           f"CAST(SUBSTR(COALESCE(description,''),1,4000) AS VARCHAR(4000)), "
           f"COALESCE(cover_url,'') FROM {T} WHERE chunk_id = ?")
    _log_sql(sql, [chunk_id], level=logging.DEBUG)
    stmt = ibm_db.prepare(conn, sql)
    ibm_db.bind_param(stmt, 1, chunk_id)
    ibm_db.execute(stmt)
    row = ibm_db.fetch_tuple(stmt)
    if not row:
        return {"title": "", "author": "", "description": "", "cover": ""}
    return {"title": (row[0] or "").strip(), "author": (row[1] or "").strip(),
            "description": (row[2] or "").strip().replace("\n", " "),
            "cover": (row[3] or "").strip()}

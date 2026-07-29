-- Hybrid search demo (for testing) — runs the three legs for one hardcoded query.
-- Run as the Db2 instance owner:  db2 -tvf scripts/2_search.sql
-- To search something else, replace the query text in all three statements: the
-- raw form (vector leg) and the 'word OR word ...' form (keyword leg).
-- Knobs are inlined to match the tuned defaults in .env / hybrid_search.core:
-- POOL 100, weights 0.3/0.7, gates 0 — matches .env.example and core.py defaults.
-- (Corpus-specific: re-tune with scripts/eval.py after changing corpus or model.)

CONNECT TO SAMPLE;

-- Lexical leg (BM25).
SELECT chunk_id, SCORE(chunk_text, 'jason OR fung OR reversing OR blood OR sugar OR disease') AS bm25,
       CAST(SUBSTR(chunk_text, 1, 70) AS VARCHAR(70)) AS snippet
FROM MYSCHEMA.CHUNKS
WHERE CONTAINS(chunk_text, 'jason OR fung OR reversing OR blood OR sugar OR disease') = 1
ORDER BY bm25 DESC FETCH FIRST 5 ROWS ONLY;

-- Vector leg (cosine similarity over the query embedding).
WITH q (qv) AS (VALUES TO_EMBEDDING('jason fung on reversing blood-sugar disease' USING MYSCHEMA.CHUNKS_EMBED))
SELECT c.chunk_id, (1 - VECTOR_DISTANCE(c.embedding, q.qv, COSINE)) AS cosine_sim,
       CAST(SUBSTR(c.chunk_text, 1, 70) AS VARCHAR(70)) AS snippet
FROM MYSCHEMA.CHUNKS c, q
ORDER BY VECTOR_DISTANCE(c.embedding, q.qv, COSINE)
FETCH APPROX FIRST 5 ROWS ONLY;

-- Hybrid leg: gate + max-normalize each leg, then weighted sum (one query).
WITH
q (qv) AS (VALUES TO_EMBEDDING('jason fung on reversing blood-sugar disease' USING MYSCHEMA.CHUNKS_EMBED)),
lex0 AS (
  SELECT chunk_id, SCORE(chunk_text, 'jason OR fung OR reversing OR blood OR sugar OR disease') AS s
  FROM MYSCHEMA.CHUNKS
  WHERE CONTAINS(chunk_text, 'jason OR fung OR reversing OR blood OR sugar OR disease') = 1
  ORDER BY s DESC FETCH FIRST 100 ROWS ONLY),
vec0 AS (
  SELECT c.chunk_id, (1 - VECTOR_DISTANCE(c.embedding, q.qv, COSINE)) AS s
  FROM MYSCHEMA.CHUNKS c, q
  ORDER BY VECTOR_DISTANCE(c.embedding, q.qv, COSINE) FETCH APPROX FIRST 100 ROWS ONLY),
lex AS (SELECT chunk_id, CASE WHEN MAX(s) OVER () < 0.0 THEN 0 ELSE s / MAX(s) OVER () END AS n FROM lex0),
vec AS (SELECT chunk_id, CASE WHEN MAX(s) OVER () < 0.0 THEN 0 ELSE s / MAX(s) OVER () END AS n FROM vec0),
fused AS (
  SELECT COALESCE(lex.chunk_id, vec.chunk_id) AS chunk_id,
         0.3 * COALESCE(lex.n, 0) + 0.7 * COALESCE(vec.n, 0) AS score
  FROM lex FULL OUTER JOIN vec ON lex.chunk_id = vec.chunk_id)
SELECT f.chunk_id, f.score,
       CAST(SUBSTR(c.chunk_text, 1, 70) AS VARCHAR(70)) AS snippet
FROM fused f JOIN MYSCHEMA.CHUNKS c ON c.chunk_id = f.chunk_id
ORDER BY f.score DESC, f.chunk_id ASC FETCH FIRST 5 ROWS ONLY;

CONNECT RESET;

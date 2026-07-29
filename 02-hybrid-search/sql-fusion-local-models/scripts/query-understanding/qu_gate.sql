-- Query-understanding gate — all additive Db2 objects in MYSCHEMA.
-- Deploy:  db2 -td@ -vf scripts/query-understanding/qu_gate.sql
--
--   QU_ROUTE(q)      -> 'lexical_heavy' | 'semantic_heavy' | 'balanced'   (deterministic, no LLM)
--   QU_LEXICAL(q)    -> extractive keyword query (strips filler+stopwords, PRESERVES rare tokens/
--                       numbers/proper nouns/quoted strings). Never touches the LLM.
--   QU_CACHE         -> memoization table keyed by the normalized query.
--   QU_UNDERSTAND(q) -> route + lexical_q + semantic_q + llm_fired, with cache + LLM-failure fallback.
--                       Calls TEXT_GENERATION(... USING MYSCHEMA.QU_GEN) only when the route warrants it.

CONNECT TO SAMPLE@

DROP PROCEDURE MYSCHEMA.QU_UNDERSTAND@
DROP FUNCTION  MYSCHEMA.QU_ROUTE@
DROP FUNCTION  MYSCHEMA.QU_LEXICAL@
DROP TABLE     MYSCHEMA.QU_CACHE@

-- ---------- deterministic router (pure SQL, sub-ms) ----------
CREATE FUNCTION MYSCHEMA.QU_ROUTE(q VARCHAR(4000))
RETURNS VARCHAR(16)
LANGUAGE SQL DETERMINISTIC NO EXTERNAL ACTION
RETURN
  SELECT CASE
    -- exact-token signals: numbers, acronyms/ALLCAPS, quoted phrases, code/$ -> keyword leg only
    WHEN hasdig = 1 OR hasacr = 1 OR hasquote = 1 OR hascode = 1 THEN 'lexical_heavy'
    -- short, content-dense queries (titles, author/narrator names) -> keyword leg only
    WHEN tokens <= 3 THEN 'lexical_heavy'
    WHEN tokens <= 5 AND stops * 10 < tokens * 3 THEN 'lexical_heavy'      -- stopword ratio < 0.30
    -- long, filler-heavy natural language -> generative semantic
    WHEN tokens >= 8 AND stops * 100 >= tokens * 34 THEN 'semantic_heavy'
    ELSE 'balanced'
  END
  FROM (
    SELECT
      REGEXP_COUNT(TRIM(q), '\s+') + 1 AS tokens,
      REGEXP_COUNT(LOWER(q),
        '\b(the|a|an|of|to|in|on|and|or|for|with|about|is|are|was|were|do|does|how|what|that|this|by|you|your|me|my|we|our|it|as|at|from|so|if|but|why|can|book|books|one|looking|find|need|want)\b') AS stops,
      CASE WHEN REGEXP_LIKE(q, '[0-9]') THEN 1 ELSE 0 END AS hasdig,
      CASE WHEN REGEXP_LIKE(q, '[A-Z]{2,}') THEN 1 ELSE 0 END AS hasacr,
      CASE WHEN q LIKE '%"%' THEN 1 ELSE 0 END AS hasquote,
      CASE WHEN REGEXP_LIKE(q, '[_(){}]|::|[A-Za-z]+_[A-Za-z]+|[$#@]') THEN 1 ELSE 0 END AS hascode
    FROM SYSIBM.SYSDUMMY1
  ) f@

-- ---------- extractive lexical query (pure SQL) ----------
CREATE FUNCTION MYSCHEMA.QU_LEXICAL(q VARCHAR(4000))
RETURNS VARCHAR(4000)
LANGUAGE SQL DETERMINISTIC NO EXTERNAL ACTION
RETURN TRIM(REGEXP_REPLACE(
  REGEXP_REPLACE(
    REGEXP_REPLACE(q,
      '\b(i am looking for|i''m looking for|looking for|can you find me|can you find|could you find|find me|show me|give me|recommend me|do you have anything|do you have|i would like|i''d like|a book about|the book about|the one about|that book about|book about|the one where|anything about|something about|anything on|something on|i want|i need|please)\b',
      '', 1, 0, 'i'),
    '\b(the|a|an|of|to|in|on|and|or|for|with|about|is|are|was|were|do|does|how|what|that|this|by|you|your|me|my|we|our|it|as|at|from|so|if|but|why|can|book|books|one|anything|something|someone|anyone|stuff|things|recommend|suggest)\b',
    '', 1, 0, 'i'),
  '\s+', ' '))@

-- ---------- memoization ----------
CREATE TABLE MYSCHEMA.QU_CACHE (
  qnorm      VARCHAR(500) NOT NULL PRIMARY KEY,
  route      VARCHAR(16),
  lexical_q  VARCHAR(4000),
  semantic_q VARCHAR(4000),
  llm_fired  SMALLINT,
  created    TIMESTAMP DEFAULT CURRENT TIMESTAMP)@

-- ---------- orchestrator: cache -> route -> conditional generation -> memoize ----------
CREATE PROCEDURE MYSCHEMA.QU_UNDERSTAND(
  IN  q       VARCHAR(4000),
  OUT o_route VARCHAR(16),
  OUT o_lex   VARCHAR(4000),
  OUT o_sem   VARCHAR(4000),
  OUT o_llm   SMALLINT)
LANGUAGE SQL
BEGIN
  DECLARE v_norm   VARCHAR(500);
  DECLARE v_found  SMALLINT DEFAULT 0;
  DECLARE v_prompt VARCHAR(4000);

  SET v_norm = LOWER(SUBSTR(TRIM(q), 1, 500));

  -- 1) cache hit -> return memoized understanding
  FOR c AS SELECT route, lexical_q, semantic_q, llm_fired FROM MYSCHEMA.QU_CACHE WHERE qnorm = v_norm DO
    SET o_route = c.route; SET o_lex = c.lexical_q; SET o_sem = c.semantic_q; SET o_llm = c.llm_fired;
    SET v_found = 1;
  END FOR;
  IF v_found = 1 THEN RETURN; END IF;

  -- 2) deterministic gate (no LLM)
  SET o_route = MYSCHEMA.QU_ROUTE(q);
  SET o_lex   = MYSCHEMA.QU_LEXICAL(q);

  -- 3) semantic query: raw for exact/short; generative otherwise
  IF o_route = 'lexical_heavy' THEN
    SET o_sem = q;
    SET o_llm = 0;
  ELSE
    SET o_llm = 1;
    BEGIN
      DECLARE CONTINUE HANDLER FOR SQLEXCEPTION SET o_sem = q;   -- LLM error -> raw (search never fails)
      SET v_prompt = 'You help search an audiobook library. Given a rough query, write a one-sentence back-cover-style description of the book the person is probably after — its topic, themes, and what it teaches — WITHOUT reusing their exact words where you can avoid it. 20-30 words. Reply as JSON with one field q. Query: ' || q;
      SET o_sem = TRIM(JSON_VALUE(TEXT_GENERATION(v_prompt USING MYSCHEMA.QU_GEN), '$.q'));
    END;
    IF o_sem IS NULL OR o_sem = '' THEN SET o_sem = q; END IF;
  END IF;

  -- 4) memoize (best-effort; never let caching fail the call)
  BEGIN
    DECLARE CONTINUE HANDLER FOR SQLEXCEPTION BEGIN END;
    INSERT INTO MYSCHEMA.QU_CACHE(qnorm, route, lexical_q, semantic_q, llm_fired)
    VALUES (v_norm, o_route, o_lex, o_sem, o_llm);
  END;
END@

CONNECT RESET@

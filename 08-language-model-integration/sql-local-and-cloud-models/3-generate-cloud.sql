-- ===========================================================================
-- 3. Text generation model, cloud: Google AI (Gemini).
--
--   db2 -tvf 3-generate-cloud.sql
--
-- The counterpart to 2-embed-cloud.sql: same provider and base URL, but
-- TYPE TEXT_GENERATION, and the function is TEXT_GENERATION(prompt USING model),
-- which returns VARCHAR instead of VECTOR.
--
-- Rerunnable: the DROP reports SQL0204N the first time. Expected.
-- ===========================================================================

-- Supply the key without editing this file (see the recipe README):
--   ALTER EXTERNAL MODEL GEN_GEMINI SET KEY 'the-real-key';

CONNECT TO SAMPLE;

DROP EXTERNAL MODEL GEN_GEMINI;

-- URL        the same base as the embedding script, ending in chat/completions.
-- ID         gemini-3.5-flash-lite -- cheapest and fastest, ample for this.
--            Avoid gemini-3.6-flash: 20 requests PER DAY on the free tier.
--            gemini-2.5-flash-lite is "no longer available to new users".
-- RETURNING  a VARCHAR width, not a vector width. The answer below runs about
--            2600 characters, so 4000 is comfortable; a longer prompt needs more.
-- There is no temperature, top_p, or max_tokens clause in this DDL -- the prompt
-- is the only control over the output.

CREATE EXTERNAL MODEL GEN_GEMINI PROVIDER OPENAI
  ID  'gemini-3.5-flash-lite'
  URL 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'
  TYPE TEXT_GENERATION RETURNING VARCHAR(4000)
  KEY 'PASTE-YOUR-GOOGLE-AI-STUDIO-API-KEY-HERE';

-- Send a prompt, print the answer. One API call.
SELECT TEXT_GENERATION(CAST('What is IBM Db2?' AS VARCHAR(200))
                       USING GEN_GEMINI) AS answer
  FROM SYSIBM.SYSDUMMY1;

CONNECT RESET;

-- ---------------------------------------------------------------------------
-- If this fails with:  SQL16402N  JSON data is not valid.
--
-- That is almost certainly free-tier quota, not a Db2 bug. Google returns a 429
-- as a JSON *array* -- [{"error": {"code": 429, ...}}] -- and Db2, expecting an
-- object, reports a parse error that never mentions quota. Confirm from a shell,
-- where the real message is readable:
--
--   curl -s https://generativelanguage.googleapis.com/v1beta/openai/chat/completions \
--     -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
--     -d '{"model":"gemini-3.5-flash-lite","messages":[{"role":"user","content":"hi"}]}'
--
-- Cleanup:  DROP EXTERNAL MODEL GEN_GEMINI;
-- To keep the key out of this file, ship the placeholder and run once:
--   ALTER EXTERNAL MODEL GEN_GEMINI SET KEY 'the-real-key';   (SET is required)
-- ---------------------------------------------------------------------------

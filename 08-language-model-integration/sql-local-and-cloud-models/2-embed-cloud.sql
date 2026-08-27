-- ===========================================================================
-- 2. Embedding model, cloud: Google AI (Gemini).
--
--   db2 -tvf 2-embed-cloud.sql
--
-- The same two moves as 1-embed-onprem.sql -- register, then TO_EMBEDDING on a
-- literal -- pointed at a hosted API instead of localhost. Only the URL, the
-- model id, the width, and the key differ.
--
-- Get a key from https://aistudio.google.com/apikey and supply it WITHOUT editing
-- this file (see the recipe README, "Supplying the API key"):
--   ALTER EXTERNAL MODEL EMBED_GEMINI SET KEY 'the-real-key';
--
-- Your text leaves the machine on every call, and calls are metered.
--
-- PROVIDER OPENAI names the OpenAI *wire format*, not the OpenAI service -- any
-- endpoint speaking it is reachable this way. HTTPS needs no keystore or
-- certificate setup; Db2's own client does the TLS handshake.
--
-- Rerunnable: the DROP reports SQL0204N the first time. Expected.
-- ===========================================================================

CONNECT TO SAMPLE;

DROP EXTERNAL MODEL EMBED_GEMINI;

-- URL        Google's OpenAI-compatible base + 'embeddings'. NOT /v1/embeddings
--            -- the version is already in the base path as /v1beta/.
-- ID         gemini-embedding-001. NOT text-embedding-004: that one is no longer
--            served here ("not found for API version v1main").
--            GET .../v1beta/openai/models lists what your key can reach.
-- RETURNING  must match the model's real width -- Db2 does not discover it.
--            gemini-embedding-001 emits 3072 floats. A wrong number here fails
--            when TO_EMBEDDING runs, not at CREATE time.
-- KEY        a real secret once filled in. Strip it before sharing this file.

CREATE EXTERNAL MODEL EMBED_GEMINI PROVIDER OPENAI
  ID  'gemini-embedding-001'
  URL 'https://generativelanguage.googleapis.com/v1beta/openai/embeddings'
  TYPE TEXT_EMBEDDING RETURNING VECTOR(3072, FLOAT32)
  KEY 'PASTE-YOUR-GOOGLE-AI-STUDIO-API-KEY-HERE';

-- Embed a literal and show the result. CREATE EXTERNAL MODEL above never
-- contacts Google, so this is the first statement that proves the key, URL, and
-- model id are all good.
SELECT VECTOR_DIMENSION_COUNT(v)             AS dims,
       SUBSTR(VECTOR_SERIALIZE(v), 1, 240)   AS vector_prefix
  FROM (VALUES TO_EMBEDDING(CAST('What is IBM Db2?' AS VARCHAR(200))
                            USING EMBED_GEMINI)) AS t(v);

-- Drop the SUBSTR above to print all 3072 numbers (~60KB on one line).

CONNECT RESET;

-- Cleanup:  DROP EXTERNAL MODEL EMBED_GEMINI;
-- To keep the key out of this file, ship the placeholder and run once:
--   ALTER EXTERNAL MODEL EMBED_GEMINI SET KEY 'the-real-key';   (SET is required)

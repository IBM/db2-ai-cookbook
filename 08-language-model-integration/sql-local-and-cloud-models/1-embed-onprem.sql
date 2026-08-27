-- ===========================================================================
-- 1. Embedding model, on-prem: a local llama.cpp server.
--
--   db2 -tvf 1-embed-onprem.sql
--
-- Register the endpoint as an external model, call TO_EMBEDDING on a literal,
-- print the vector. Nothing leaves the machine and there is no API key.
--
-- Start the server first (see the recipe README for the model download):
--   llama-server -m bge-small-en-v1.5-q8_0.gguf \
--     --embedding --pooling cls --ctx-size 512 --host 127.0.0.1 --port 8085
--
-- Rerunnable: the DROP reports SQL0204N the first time. Expected.
-- ===========================================================================

CONNECT TO SAMPLE;

DROP EXTERNAL MODEL EMBED_LOCAL;

-- PROVIDER OPENAI names the OpenAI *wire format*, not the OpenAI service. Any
-- server implementing POST /v1/embeddings qualifies, which is why a llama.cpp
-- process on localhost works with no gateway in between.
--
-- URL        the FULL endpoint path, not just the host.
-- ID         the "model" field Db2 puts in the request body. llama.cpp serves
--            whatever it was started with and ignores this, but it must be set.
-- RETURNING  must match the model's real output width -- Db2 does not discover
--            it. bge-small-en-v1.5 emits 384 floats. A wrong number here fails
--            when TO_EMBEDDING runs, not at CREATE time.
-- KEY        required by the syntax. The local server has no auth, so this is a
--            placeholder, not a secret.

CREATE EXTERNAL MODEL EMBED_LOCAL PROVIDER OPENAI
  ID  'bge-small-en-v1.5'
  URL 'http://127.0.0.1:8085/v1/embeddings'
  TYPE TEXT_EMBEDDING RETURNING VECTOR(384, FLOAT32)
  KEY 'sk-noauth';

-- CREATE EXTERNAL MODEL above never contacts the server -- it succeeds even if
-- nothing is listening. This is the first statement that proves the endpoint,
-- the model id, and the width are all good.
SELECT VECTOR_DIMENSION_COUNT(v)             AS dims,
       CAST(VECTOR_NORM(v, EUCLIDEAN) AS DECIMAL(8,6)) AS l2_norm,
       SUBSTR(VECTOR_SERIALIZE(v), 1, 60)    AS vector_prefix
  FROM (VALUES TO_EMBEDDING(CAST('What is IBM Db2?' AS VARCHAR(200))
                            USING EMBED_LOCAL)) AS t(v);

-- Drop the SUBSTR above to print all 384 numbers.

CONNECT RESET;

-- Cleanup:  DROP EXTERNAL MODEL EMBED_LOCAL;

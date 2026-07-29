-- Load data/corpus.csv (book-level corpus, one row per audiobook) into Db2 and
-- build the text + vector indexes.
-- Run from repo root as the Db2 instance owner:
--     ./scripts/preflight.sh && db2 -tvf scripts/1_ingest.sql
--
-- ALWAYS run preflight.sh first. If OpenSearch is down, SYSTS_DROP below fails,
-- which leaves the text index in place, which blocks DROP TABLE, which makes
-- CREATE TABLE fail — and the IMPORT then runs against the OLD table and rejects
-- every row as a duplicate key. The output blames duplicate keys, never the
-- stopped service. preflight.sh catches that in one line.
--
-- Prereqs: db2set DB2_VECTOR_INDEXING=YES -immediate (first run only; the
-- installer sets it), OpenSearch on :9200, and the local embedding server up:
-- llama.cpp serving bge-small-en-v1.5 on http://127.0.0.1:8085
-- (see scripts/0_start-services.sh). Drop the model/embed/vector steps for
-- lexical-only.
--
-- The table keeps book metadata (title, authors, narrators, pillar, status, …)
-- alongside the retrieval columns. Both retrievers operate ONLY on chunk_text
-- (the self-contained "{title} by {authors}. Narrated by {narrators}. {desc}"
-- field), so 2_search.sql and hybrid_search.core keep working unchanged:
--   chunk_id  = the corpus 'id' (primary key, one per book)
--   chunk_text = text-search index + TO_EMBEDDING source

CONNECT TO SAMPLE;

-- Clean slate (index before table; errors are harmless on a fresh database).
CALL SYSPROC.SYSTS_DROP('MYSCHEMA', 'CHUNKS_TEXT_IDX', 'en_US', ?);
DROP TABLE MYSCHEMA.CHUNKS;

-- Table columns are in data/corpus.csv order so IMPORT maps positionally.
-- (embedding is added AFTER the load, so it is not part of the CSV.)
CREATE TABLE MYSCHEMA.CHUNKS (
  chunk_id        INTEGER NOT NULL PRIMARY KEY,  -- corpus 'id'
  asin            VARCHAR(20),
  title           VARCHAR(300),
  subtitle        VARCHAR(400),
  authors         VARCHAR(400),
  narrators       VARCHAR(400),
  series_name     VARCHAR(200),
  series_position VARCHAR(20),
  publisher       VARCHAR(200),
  release_year    VARCHAR(10),
  language        VARCHAR(40),
  description     CLOB(1M),
  genres          VARCHAR(1000),
  pillar          VARCHAR(40),
  runtime_min     VARCHAR(10),
  status          VARCHAR(20),
  rating          VARCHAR(10),
  file_path       VARCHAR(1024),
  purchase_date   VARCHAR(40),
  chunk_text      CLOB(1M),
  cover_url       VARCHAR(200)   -- relative path to the book's cover thumbnail (ui/static/)
);

-- Rows (SKIPCOUNT skips the header; delprioritychar keeps quoted commas/newlines).
IMPORT FROM data/corpus.csv OF DEL MODIFIED BY delprioritychar SKIPCOUNT 1
  INSERT INTO MYSCHEMA.CHUNKS
    (chunk_id, asin, title, subtitle, authors, narrators, series_name,
     series_position, publisher, release_year, language, description, genres,
     pillar, runtime_min, status, rating, file_path, purchase_date, chunk_text,
     cover_url);

-- Text-search index on chunk_text (create, then populate).
CALL SYSPROC.SYSTS_CREATE('MYSCHEMA', 'CHUNKS_TEXT_IDX', 'MYSCHEMA.CHUNKS(CHUNK_TEXT)', 'SERVERID 1', 'en_US', ?);
CALL SYSPROC.SYSTS_UPDATE('MYSCHEMA', 'CHUNKS_TEXT_IDX', '', 'en_US', ?);

-- Embedding model: local llama.cpp (bge-small-en-v1.5), OpenAI-compatible endpoint.
-- PROVIDER OPENAI takes no PROJECT_ID; KEY is a dummy (the local server has no auth).
DROP EXTERNAL MODEL MYSCHEMA.CHUNKS_EMBED;
CREATE EXTERNAL MODEL MYSCHEMA.CHUNKS_EMBED PROVIDER OPENAI
  ID 'bge-small-en-v1.5'
  -- Port 8085 is FIXED here and must match EMBED_PORT in 0_start-services.sh. If you
  -- change one, change both — otherwise TO_EMBEDDING calls a dead port and fails at
  -- search time, not at setup. (0_start-services.sh warns if they diverge.)
  URL 'http://127.0.0.1:8085/v1/embeddings'
  TYPE TEXT_EMBEDDING RETURNING VECTOR(384, FLOAT32)
  KEY 'sk-noauth';

-- Embed each book's chunk_text.
-- The text-search index (above) covers the FULL chunk_text, but the embedding model
-- (bge-small-en-v1.5) has a 512-token context and ERRORS on longer input (and one
-- over-long row rolls back the whole UPDATE). So embed a truncated slice: 1500 chars
-- stays under 512 tokens for even the densest text (~3.3 chars/token). The tail of a
-- long summary is not vectorized (BM25 still indexes all of it) — an accepted limit;
-- for full coverage, chunk long summaries into passages (a larger change).
ALTER TABLE MYSCHEMA.CHUNKS ADD COLUMN embedding VECTOR(384, FLOAT32);
UPDATE MYSCHEMA.CHUNKS
   SET embedding = TO_EMBEDDING(CAST(SUBSTR(chunk_text, 1, 1500) AS VARCHAR(1500))
                               USING MYSCHEMA.CHUNKS_EMBED);

-- Vector index (last — it makes the table read-only).
CREATE VECTOR INDEX MYSCHEMA.CHUNKS_VEC_IDX ON MYSCHEMA.CHUNKS(embedding) WITH DISTANCE COSINE EXCLUDE NULL KEYS;
CALL SYSPROC.ADMIN_CMD('RUNSTATS ON TABLE MYSCHEMA.CHUNKS AND INDEXES ALL');

CONNECT RESET;

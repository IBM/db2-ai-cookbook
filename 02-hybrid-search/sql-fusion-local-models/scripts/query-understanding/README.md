# Adaptive query-understanding gate

An in-database query-understanding layer for the hybrid search pipeline. It decides —
per query, in SQL — whether spending a local LLM call is worth it, cleans the lexical
query extractively, and (only when warranted) writes a generative semantic query. Both
queries feed the existing BM25+vector fusion.

Everything runs locally: the router/cleaner are pure Db2 SQL; generation is a second
`llama-server` (Qwen2.5-3B-Instruct Q4_K_M) reached through Db2 `TEXT_GENERATION`.

## Components

| Piece | Where | What it does |
|---|---|---|
| Router | `qu_gate.sql` → `MYSCHEMA.QU_ROUTE(q)` | Deterministic, sub-ms. Returns `lexical_heavy` / `balanced` / `semantic_heavy` from token count, stopword ratio, and exact-signal flags (digits, ALLCAPS, quotes, code). |
| Lexical cleaner | `qu_gate.sql` → `MYSCHEMA.QU_LEXICAL(q)` | Extractive. Strips filler phrases + stopwords, **preserves** rare tokens, numbers, proper nouns, quoted strings. Never touches the LLM. |
| Conditional generation | `qu_gate.sql` → `MYSCHEMA.QU_UNDERSTAND(q)` | Cache → route → `TEXT_GENERATION` (HyDE-style) **only** when the route warrants it. `CONTINUE HANDLER` falls back to the raw query so search never fails because the LLM did. Memoized in `QU_CACHE`. |
| Generation model | `MYSCHEMA.QU_GEN` external model | `PROVIDER OPENAI` → `http://127.0.0.1:8086/v1/...`, temp 0, top-k 1, GBNF-constrained JSON (`qu_gen.gbnf`). Started by `start_gen_server.sh`. |
| Fusion path | `src/hybrid_search/core.py` → `hybrid_split(lexical_q, semantic_q)` | Same gated max-norm weighted fusion as `hybrid()`, but the keyword leg searches `lexical_q` and the vector leg embeds `semantic_q`. |
| Orchestration | `src/hybrid_search/understanding.py` | `smart_search()` (shipped entry point), `understand()`/`gated_search()`/`confidence_search()`/`llm_expand()`, hard Python fallback. `scripts/query-understanding/qu.py` re-exports it for the harness. |
| API | `ui/api.py` → `GET /api/smart_search` | Exposes the shipped path (results + understanding metadata). |
| Eval harness | `qu_eval.py` | Scores the arms on the golden set per `query_type`; logs route, llm_fired, added latency, MRR/Hits@1/Recall@5. |

**Key design choice — augment, don't replace.** When the LLM *does* fire, the vector leg
embeds `raw_query + ". " + expansion`, not the expansion alone. Replacing the raw query
regressed semantic MRR 0.62 → 0.48; augmenting holds it. The raw embedding is already strong
on this corpus, so the safe move is always to *add* HyDE context, never swap out the original.

## Results (golden set, 112 queries, `golden_set.draft.v1.json`)

```
arm                    | keyword MRR | semantic MRR | mixed MRR | topical R@5 | Hits@1 | LLM fired | added lat
-----------------------|-------------|--------------|-----------|-------------|--------|-----------|----------
A baseline (raw)       |    0.988    |    0.622     |   0.946   |    0.571    | 0.865  |   0/112   |    0 ms
CLEAN cleaner-only     |    0.988    |    0.656     |   0.946   |    0.615    | 0.875  |   0/112   |   23 ms   <- SHIPPED (QU_MODE=off)
GATED route-gen        |    0.988    |    0.628     |   0.932   |    0.584    | 0.865  |  69/112   |  527 ms
CRAG conf-gen          |    0.988    |    0.604     |   0.946   |    0.615    | 0.865  |   5/112   |   70 ms
```
Isolation run (cleaner alone, no LLM, vs raw baseline): semantic **+0.035**, topical **+0.044**,
keyword/mixed **+0.000**. added lat for GATED falls to ~0 warm via `QU_CACHE`.

## What the numbers say

- **The extractive cleaner is the real win — and it uses no LLM.** Applied to every query it
  lifts semantic MRR 0.622 → 0.656 and topical Recall@5 0.571 → 0.615, raises Hits@1 to the
  best of any arm (0.875), and never regresses keyword or mixed. Pure SQL, sub-ms, deterministic.
- **The router protects exact/keyword queries perfectly.** All 44 keyword queries stay at 0.988.
- **Generative expansion did not earn a place on the hot path here.** The raw bge-small
  embedding already retrieves these 97 short book descriptions well, so there is little
  headroom: GATED was neutral-to-slightly-negative on mixed, and CRAG — which fires only on the
  weak-retrieval tail — actually *hurt* semantic (0.656 → 0.604), because augmenting those
  specific low-confidence queries pulled the right hit down. More firing (GATED) ≠ better.

### Wired into the live search

The extractive cleaner is applied to the keyword leg of the live UI search and demo
(`ui/build_fixtures.py:responses_for`, shared by `/api/search`, `/api/demo`, and the
frozen fixtures): the lexical + hybrid keyword legs search the cleaned rare-word query,
the vector leg keeps the raw natural-language query. So "looking for a book on emotional
intelligence" searches `emotional intelligence` for keywords — it no longer matches junk
on common words like "book". The UI highlights the cleaned terms (`lex_query`).

### Rejected: route-adaptive fusion weights

A natural next idea is to lower the lexical weight for semantic/paraphrase queries (where
a confident-but-wrong keyword match can demote the true hit — e.g. "doing well with your
finances is more about behavior than being smart" ranks *The Total Money Makeover* over
*The Psychology of Money*). Measured on the golden set, **no route-adaptive weighting beat
the uniform `w_lex=0.1`**: dropping lexical for semantic-routed queries *lowered* semantic
MRR (0.656→0.625) and topical Recall@5 (0.615→0.602). The small uniform lexical weight
helps more queries than it hurts, so `hybrid_split` keeps per-call weight overrides
available (for a future corpus) but the shipped path uses the tuned globals.

**Recommendation (shipped): `QU_MODE=off` — router + extractive cleaner on every query, no LLM.**
It is the best config on this corpus on every metric at essentially zero cost, and it removes a
runtime dependency (the Qwen server) from the search path. The generative gates (`gated`, `crag`)
are fully built, tested, and one env flag away; they are expected to earn their keep on a larger
corpus with longer documents and vaguer, more conversational queries, where the raw-query
embedding has more to gain. **Re-run the harness below and re-read this table before enabling them.**

## Run it

```bash
# shipped path needs only the SQL gate (no LLM server for QU_MODE=off):
db2 -td@ -vf scripts/query-understanding/qu_gate.sql                # deploy router + cleaner + proc

# to evaluate / enable the generative gates, also start the model:
scripts/query-understanding/start_gen_server.sh                     # start Qwen on :8086
PYTHONPATH=src:scripts/query-understanding DB2_HOST=local \
  .venv/bin/python scripts/query-understanding/qu_eval.py           # regenerate the table
```

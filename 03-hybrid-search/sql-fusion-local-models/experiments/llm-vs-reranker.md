# Experiment: LLM as a re-ranker vs. a cross-encoder re-ranker

- **Date:** 2026-07-25
- **Corpus:** personal audiobook catalog (92 books)
- **Status:** concluded — LLM re-ranking not adopted

## Question

A popular strategy in RAG, and Agentic RAG especially, is to use an LLM to re-rank the
search results and pick the best matching one. I wanted to try this out on my own use
case: can a small, local LLM beat my existing cross-encoder re-ranker, or even the
hybrid-search baseline?

## Use case and existing setup

I run a hybrid search on my audiobook catalog. It combines results from lexical search
and vector search and fuses them with a score-based fusion algorithm. On top of that I
have a re-ranker, and a golden evaluation set of 20 queries with their known answer
chunks. The re-ranker was already doing a good job, often pushing more accurate results
above plain hybrid search. So the question was whether a small, local LLM could beat it.

## Strategies compared

All three select their #1 result from the **same top-10 hybrid candidates**, so it is a
controlled, apples-to-apples comparison:

1. **Hybrid search + fusion** — the baseline.
2. **Cross-encoder re-ranker** — re-scores and reorders the top 10 (its own ranking).
3. **Agentic LLM** — reads the top 10, reasons over them, and returns its rank list /
   best pick. The prompt was a re-ranking instruction template with a placeholder for the
   search results, plus anti-hallucination rules; the chosen ID is validated against the
   candidate set so it cannot return a result that was not in the list.

## Models (all small, quantized, running locally on CPU)

| role | model | notes |
|---|---|---|
| embedding | `bge-small-en-v1.5` | 384-dim, q8_0 |
| re-ranker | `bge-reranker-v2-m3` | cross-encoder, Q4_K_M |
| LLM | `Qwen2.5-3B-Instruct` | Q4_K_M (small, quantized — not a sophisticated LLM) |

## Method and metric

For each of the 20 queries I run hybrid search, take the top 10 results, and send them to
both the re-ranker and the LLM to produce their rankings. Then I check the **top matching
result (the number one position)**: how many times was the correct answer found at rank 1?
Hybrid search is the baseline; I check the same for the re-ranker's and the LLM's #1.

This is **top-1 accuracy (Hits@1)**: in the first hit, the correct answer was found. The
gold answer was present in the shared top-10 for **all 20 queries**, so this measures
*ranking*, not retrieval recall.

## Results

| strategy | Top-1 accuracy (Hits@1) | reproducible? |
|---|---|---|
| **Cross-encoder re-ranker** | **0.95** (19/20) | yes — identical every run |
| Hybrid fusion (baseline) | **0.90** (18/20) | yes — identical every run |
| Agentic LLM | **0.75–0.85** (15–17/20) | no — varies run to run |

## Additional observations

- The LLM score is a range because it was **not stable**:
  - **Non-deterministic even at temperature 0** — repeated identical runs gave different
    scores (e.g. 0.75 then 0.85).
  - **Prompt-sensitive** — a terse prompt scored ~0.20–0.30; a richer "reason step by
    step and do not hallucinate" prompt scored ~0.75–0.85.
- Hybrid search and the cross-encoder re-ranker were **deterministic** — the same score on
  every repeat.
- The LLM's misses clustered on **exact-title and bare-name queries**, where surface-token
  matching (lexical / cross-encoder) does well but the small model tends to pick a
  thematically similar but wrong book.

## Conclusion

For this use case, I am not going to add an LLM re-ranking leg. The LLM did not do a
better job than the baseline — it did not even beat hybrid search (0.90). The re-ranker,
on the other hand, did improve on the baseline (0.95). I did not find evidence that the
LLM helps here, so I did not add this LLM leg for refining the results from hybrid search.

## Caveats

- All models are small, quantized, and running locally on CPU; a larger or hosted LLM
  might change the outcome.
- This is my own dataset and my own evaluation set (20 held-out known-item queries).

## Open question

Has anyone compared a re-ranker against an LLM as a re-ranker on their own data? Did the
LLM ever beat the re-ranker?

## Reproducibility

**Serving.** All three models run locally via llama.cpp on CPU, behind OpenAI-compatible
endpoints. No cloud, no API keys.

**Models (GGUF):**
- Embedding: `bge-small-en-v1.5` (q8_0), CLS pooling, 512-token context.
- Re-ranker: `bge-reranker-v2-m3` (Q4_K_M, gpustack build), cross-encoder.
- LLM: `Qwen2.5-3B-Instruct` (Q4_K_M).

**Retrieval.** Hybrid = BM25 (text search) + dense (bge-small), fused by a gated,
score-normalized weighted sum; candidate pool = 100. All three strategies then select
their #1 from the **same hybrid top-10**.

**LLM re-ranking call.** The prompt is a template with a placeholder for the 10 candidates
(each rendered as `[id] title — author: ~200-char excerpt`) plus instructions to: reason
step by step, choose exactly one id from the list (never invent), ground the explanation
only in the chosen excerpt, and return `null` if none fit. Output is strict JSON
`{reasoning, best_id, explanation}`; `best_id` is validated against the candidate ids in
code, so an out-of-list pick is rejected. Decoding at **temperature 0** for
reproducibility (note: still not byte-identical run to run on this local CPU setup).

**Cross-encoder re-ranking.** The same 10 candidates are scored by the cross-encoder; its
#1 is taken.

**Evaluation.** 20 held-out known-item queries from the golden set, each with one known
answer chunk. Metric: **Hits@1** (is the strategy's #1 the gold answer?). The gold was
present in the shared top-10 for all 20 queries, so the metric isolates ranking from
retrieval recall.

## The LLM prompt and the re-ranker request (samples)

**LLM ranking prompt template.** `{query}` is the user query; `{candidates}` is the
hybrid top-10, one per line as `[id] Title — Author: <first ~200 chars of description>`.

```
You are a librarian helping a reader find the ONE audiobook that best answers their query.

Query: "{query}"

Candidates (each line = [ID] Title — Author: description excerpt):
{candidates}

Instructions:
- Think step by step: which candidates are truly about what the query asks vs. only share surface words.
- Choose the single BEST candidate. You may ONLY choose an ID from the list; never invent IDs/titles.
- Base the explanation ONLY on the chosen excerpt; no outside knowledge.
- If NONE answer, set best_id to null.

Respond ONLY JSON: {"reasoning":"...","best_id":<ID or null>,"explanation":"..."}
```

**Sample query, its hybrid top-10, and the filled prompt.** For the query
*"tiny daily choices that compound into big changes"* (gold answer: Atomic Habits, id 66),
the `{candidates}` block rendered as (excerpts trimmed here for display; the run used the
first ~200 chars):

```
[66] Atomic Habits — James Clear: The number one New York Times best seller. Over one million copies sold! Tiny Changes…
[36] Thinking, Fast and Slow — Daniel Kahneman: The guru to the gurus at last shares his knowledge with the rest of us…
[21] The Total Money Makeover — Dave Ramsey: Do you want to build a budget that actually works for you?…
[78] $100M Offers — Alex Hormozi: I took home more in a year than the CEOs of McDonald's, IKEA, Ford, Motorola, and Yahoo combined…
[39] Essentialism — Greg McKeown: Essentialism isn't about getting more done in less time. It's about getting only the right things done…
[26] One Simple Idea — Stephen Key: A new edition of the best-selling method that shows how anyone can turn their one idea into millions…
[63] Make Time — Jake Knapp; John Zeratsky: A unique and engaging listen about a proven habit framework you can apply to each day…
[91] Slow Productivity — Cal Newport: Do Fewer Things. Work at a Natural Pace. Obsess over Quality…
[18] Unstuff Your Life — Andrew J. Mellen: One of the country's most sought-after professional organizers shares his foolproof rescue plan…
[27] Goals! — Brian Tracy: The essential principles you need to know to make your goals achievable, faster than you thought…
```

That block is substituted into `{candidates}` and the whole prompt is sent to the LLM in
one call. The LLM returns, e.g., `{"reasoning": "...", "best_id": 66, "explanation": "..."}`;
`best_id` is checked to be one of the 10 ids before it is accepted.

**Re-ranker request (same candidates).** The cross-encoder receives the query plus the
same candidate documents (each up to `RERANK_DOC_CHARS = 1200` chars) at
`http://127.0.0.1:8087`:

```
POST /v1/rerank
{
  "model": "reranker",
  "query": "tiny daily choices that compound into big changes",
  "documents": [
    "Atomic Habits by James Clear. The number one New York Times best seller ... (up to 1200 chars)",
    "Thinking, Fast and Slow by Daniel Kahneman. ...",
    "The Total Money Makeover by Dave Ramsey. ...",
    "... (the same 10 candidate documents)"
  ]
}
-> { "results": [ { "index": 0, "relevance_score": 0.94 }, ... ] }
```

The results are sorted by `relevance_score` and the top document is taken as the
re-ranker's #1.

> **Note on an asymmetry:** the re-ranker sees up to ~1200 chars per candidate, while the
> LLM saw only ~200-char excerpts (10 full descriptions would not fit the small model's
> context window). So the LLM was working from less per-candidate text — a fair caveat when
> reading its lower score.

## Prompt trail (how this experiment was run)

A cleaned-up, compact timeline of the prompts that drove this experiment, each with a
summary of the outcome.

1. **Proposed the experiment.** "Add an agentic search: take the hybrid top results, build
   a context, send a rich anti-hallucination prompt to a local LLM, and have it pick the
   most helpful result. Before implementing, is this feasible, and how should I smoke-test
   it?"
   → Confirmed feasible (the local LLM callout was already in place). Proposed a staged
   smoke test — confirm the callout, fit the context, run one worked example, then evaluate
   — with the eval as the go/no-go gate.

2. **Refined the design.** "Send the top 10 instead of 20 to fit the context window. Is
   this small model actually a re-ranker? I want the evaluation first. Add a reasoning
   instruction, and have it explain its pick without hallucinating."
   → 10 candidates fit comfortably. Clarified the model is a general generative LLM, not a
   purpose-built re-ranker. Set output to JSON with reasoning + best_id + explanation, and
   validated the chosen id against the candidate list.

3. **Ran the smoke test and eval.** "Yes, run it."
   → The callout worked and accepted large inputs; the 10-candidate context fit the window;
   a worked example picked correctly with grounded reasoning. On 20 held-out known-item
   queries: re-ranker 0.95, hybrid 0.90, agentic LLM 0.75.

4. **Checked the comparison was fair.** "Is the comparison consistent? The LLM only saw the
   top 10, right?"
   → The candidate pools had differed (LLM 10, re-ranker 25, hybrid full). Re-ran with all
   three selecting from the identical top-10; the gold was in that set for all 20 queries,
   so it measures ranking, not recall. The result held.

5. **Probed the variation.** "Why did the LLM's number vary?"
   → The LLM was non-deterministic even at temperature 0 (repeat runs gave 0.75 then 0.85)
   and prompt-sensitive (a terse prompt scored ~0.25, a rich prompt ~0.80). Hybrid and the
   re-ranker were identical on every run.

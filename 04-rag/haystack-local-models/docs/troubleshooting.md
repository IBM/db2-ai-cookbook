# Troubleshooting

[← back to the recipe](../README.md)

Symptom → cause → fix. Every row here is a failure hit while building this recipe.


Symptom → cause → fix. Every row here is a failure hit while building this.

| Symptom | Cause | Fix |
|---|---|---|
| Build aborts: `UI: llama-ui-embed failed` / `missing required asset(s): loading.html` | The build fetches a prebuilt web UI that doesn't match tag b9913 | Add `-DLLAMA_BUILD_UI=OFF -DLLAMA_USE_PREBUILT_UI=OFF`; if a partial build already ran, `rm -rf ~/llama.cpp/build/tools/ui` first |
| Sanity test fails with `KeyError: 'choices'` a second after starting the server | `/health` returns **503** while the model loads, and `curl -s` treats that as success | Use `curl -sf` in the readiness loop |
| Embedding sanity prints a dim other than 384 | Wrong GGUF, or `--pooling cls` missing | Re-download the model file and pass the flag |
| `CREATE TABLE` fails on the `VECTOR` column during the first `ingest` | Db2 is older than **12.1.2**, which is where the native `VECTOR` type was introduced | `db2level` to confirm, then upgrade — there is no workaround; the type does not exist |
| `SQL1032N No start database manager command was issued` (from the `db2` CLI) or `SQL30081N … communication error` (from `ingest`/`search`) | Db2 isn't running. The CLI and the Python client report it differently — the Python client connects over TCP, so it fails at the socket | `db2start` |
| `SQL30082N … reason "24" ("USERNAME AND/OR PASSWORD INVALID")` | `AUTHENTICATION=SERVER` — Db2 checks the **OS** password | Put `db2inst1`'s OS password in `DB2_PASSWORD` |
| Db2 connect fails though the instance is up | `DB2COMM` not set to TCPIP, or `DB2_PORT` ≠ the instance's `SVCENAME` | `db2set DB2COMM=TCPIP; db2stop; db2start`, and check `db2 get dbm cfg \| grep SVCENAME` |
| `SQL1024N A database connection does not exist` | Running SQL without connecting | `db2 connect to SAMPLE` |
| **Every** insert fails `SQL0443N … JSON2BSON … JSON parsing error` | Docling's `dl_meta` contains `$ref`; BSON forbids field names starting with `$` | Keep the `SimpleMeta` extractor in `ingest.py` — it strips `dl_meta` |
| Every search prints `Nothing was retrieved` although `SELECT COUNT(*)` shows rows | A row whose embedding is all zeros. `VECTOR_DISTANCE(…, COSINE)` raises **`SQL0801N` division by zero**, which aborts the whole ranking query — the retriever swallows it and returns an empty list, so nothing says *why* | Re-run `ingest` to rebuild the table. To see the real error, run the ranking query in `db2` directly: the CLI prints `SQL0801N` where Python prints nothing |
| A metadata range filter (`>`, `>=`, `<`, `<=`) returns too few rows, with no error | Metadata comparisons are made as **strings**, so `page_number >= 2` matches pages 2–9 but not 10–15, and `<= 12` matches 1, 10, 11, 12 | Use `in` with an explicit list of values — `get_metadata_field_min_max()` gives you the bounds to build it from. See [Filtering on numbers](../README.md#filtering-on-numbers) |
| `FilterError: Operator '>=' requires a numeric value or ISO date string, got str` | Range operators are validated before the query runs and reject string values, so zero-padding a numeric field is not a workaround | Same fix: `in` with a list |
| `ModuleNotFoundError: No module named 'haystack_db2_rag'` | The package lives in `src/` | `export PYTHONPATH=src` |
| `Connection refused` on `:8081` or `:8080` | A llama.cpp server isn't running | `scripts/llama-servers.sh start`, then `status` |
| `Error code: 400 … request (N tokens) exceeds the available context size (M tokens)` | A large `--top-k` puts more chunk text in the prompt than the chat server's window holds. llama.cpp rejects the request outright — it does not truncate | Raise `--ctx-size` for the chat server in `scripts/llama-servers.sh` (it ships at 8192, which covers `--top-k 10` at this chunk size) and restart it |
| transformers warns `Token indices sequence length is longer … (519 > 512)` | A chunk exceeds the embedding window and is being silently truncated | Lower `EMBED_MAX_TOKENS` in `settings.py` (448 works for this PDF) |
| `ingest` dies in thousands of lines of `torch._inductor` traceback, ending in `fatal error: Python.h: No such file or directory` | docling 2.119+ runs its layout model through `torch.compile`, which generates C++ and compiles it — that needs the CPython headers, absent from RHEL by default | Keep the `docling==2.115.0` pin in `requirements.txt`. On a newer docling: `sudo dnf install -y python3-devel`, or run with `TORCHDYNAMO_DISABLE=1` if you have no root |
| First `ingest` run seems to hang | It's downloading Docling's ~500 MB layout models | Wait it out; subsequent runs are offline and fast |

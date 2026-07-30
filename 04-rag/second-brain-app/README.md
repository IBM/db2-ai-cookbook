# Second brain: capture what you read into Db2

> **Last checked 2026-07-30** — verified: app starts, saves a web article (82 KB of markdown),
> extracts its title, detects duplicates, browses and renders. One schema defect found and fixed.  
> Checked on: Db2 12.1.5.0 · RHEL 10 · Python 3.12.

[← RAG](../README.md) · [← Db2 AI Cookbook](../../README.md)

> Paste a URL, and the article is fetched, stripped of navigation chrome, and stored as a row in
> Db2. A small FastAPI app you keep running and keep adding to — the front half of a RAG
> pipeline, built as an application rather than a script.

![Db2](https://img.shields.io/badge/store-Db2%2012.1%2B-054ada)
![Python](https://img.shields.io/badge/Python-3.12-blue)
![Docling](https://img.shields.io/badge/extract-Docling-0f62fe)

Every other recipe in this cookbook runs once: you execute a notebook, read the output, and stop.
This one is a **running application**. It has a browser UI, it keeps a corpus that grows each time
you save something, and its state survives restarts — which is what a second brain has to do to be
worth having.

It is also deliberately incomplete. The app captures and stores; it does not yet embed, retrieve,
or answer. That is the next stage, and the point of keeping the stages separate is that you can
read the diff between them.

## The stages

Each stage is self-contained and runnable. Start at 00 and walk forward — the value is in what
changes between them.

| Stage | What it adds | Where documents go |
|---|---|---|
| [00-basic](stages/00-basic/) | `POST /save` → Docling extracts the article → one markdown file per save | `~/second-brain/*.md` |
| [01-db2](stages/01-db2/) | The same save path, but the filesystem write becomes an `INSERT`. Adds a browse page, a rendered view, duplicate detection, and title extraction | Db2 `DOCUMENTS` table |

Stage 00 touches Db2 not at all — it exists so that stage 01's change is legible. If you only want
the Db2 version, skip straight to 01.

## Quick start

```bash
cd 04-rag/second-brain-app
python3.12 -m venv .venv          # run.sh expects the venv here

./stages/01-db2/run.sh
```

`run.sh` installs that stage's requirements, applies `schema.sql`, and starts the app on
<http://127.0.0.1:8000>. It also stops any previously-running stage first, so switching between
stages is one command.

The schema is idempotent — `CREATE TABLE IF NOT EXISTS` — so saved documents persist across
restarts and across stage switches.

> **The first run downloads Docling's layout models** (several hundred MB) and takes a few minutes
> before the app answers. Later runs start in seconds.

## Expected output

Open <http://127.0.0.1:8000>, paste an article URL, and press **Save**. The page reloads with the
document listed by title. Click it to read the extracted markdown rendered back to HTML.

Saving the same URL twice does not create a second row — the app reports `Already saved as id N`
inline, because `URL` carries a `UNIQUE` constraint.

On this machine, saving the Wikipedia article on vector databases produced **82,371 bytes** of
markdown with the title `Vector database`, in under a second once the models were warm.

Two things you will notice, both by design:

- **Site-specific navigation survives.** The Wikipedia copy still begins with `## Contents`,
  `move to sidebar`, `hide`. `clean_chrome()` filters only *universal* UI labels; tuning it per
  site would make the rules brittle. Cleaning that up is a good first change to make.
- **Failed fetches are stored, not rejected.** Point it at a URL that 404s and you get a row —
  a 941-byte document titled `Page Not Found`. Nothing checks the HTTP status. In a personal
  capture tool a wrong save is cheap to delete, but it is worth knowing before you trust the
  corpus.

To confirm the row landed in Db2:

```bash
db2 connect to SAMPLE
db2 "SELECT ID, TITLE, URL, SAVED_AT, LENGTH(CONTENT) AS BYTES FROM DOCUMENTS ORDER BY ID DESC"
db2 terminate
```

## Concepts

### Docling, in three method calls

The whole extraction step is one chain; everything else in `app.py` is plumbing around it:

```python
converter.convert(url)             # fetch + parse → ConversionResult
         .document                 # structured DoclingDocument
         .export_to_markdown()     # flatten → markdown string
```

`DocumentConverter` is built **once at module load**, not per request — model initialisation is
expensive, and a web app that pays it on every save is unusable.

### Why the text is clean

Two filters run before anything is stored, and both matter more than they look:

- **`CONTENT_LABELS`** drops `PAGE_HEADER`, `PAGE_FOOTER` and `PICTURE`, so what you keep is
  article text — no figures, no `<!-- image -->` placeholders.
- **`clean_chrome()`** removes universal UI noise: `Subscribe`, `Sign in`, `Share`, copyright
  lines, bare digit counts, email-signup prompts. Platform-specific chrome is deliberately *not*
  filtered, to keep the rules general rather than tuned to one site.

Garbage stored now is garbage retrieved later, so this is the cheapest quality work in the whole
pipeline.

### A `CLOB`, not a `VECTOR` — yet

The `CONTENT` column is `CLOB(10M)`: the full article text, unchunked and unembedded. That is
the honest state of the app, and it is why this recipe needs no particular Db2 vector level.

When retrieval lands, the chunks and their embeddings become a `VECTOR` column alongside this
one — the same shape as [haystack-local-models](../haystack-local-models/), which already does
Docling → chunk → embed → `VECTOR_DISTANCE` → grounded answer. Read that recipe if you want the
finished pipeline today.

---

## Appendix

### Provenance

Ported from [IBM/second-brain-with-db2](https://github.com/IBM/second-brain-with-db2), which was
built in public one stage at a time and is being archived in favour of this copy. Apache-2.0, the
same licence as this cookbook.

### Connection and credentials

There are none to configure. `app.py` opens a local implicit connection as the instance owner:

```python
conn = ibm_db.connect("SAMPLE", "", "")
```

That works when you run as `db2inst1` against a locally catalogued `SAMPLE`. For any other setup —
a different database, a remote host, a different user — edit that one line. All SQL uses parameter
markers, so nothing is interpolated into a statement.

### Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Error: .venv not found` | `run.sh` looks for the venv at the recipe root | `cd 04-rag/second-brain-app && python3.12 -m venv .venv` |
| First save hangs for minutes | Docling is downloading its layout models | Wait it out once; later runs are fast |
| `SQLSTATE=42704` on `DOCUMENTS` | Schema never applied | `db2 -tf stages/01-db2/schema.sql` |
| `SQL1032N No start database manager` | Db2 is not running | `db2start` |
| Save returns 500 on a PDF that looks fine | The pipeline runs with `do_ocr=False`, so scanned/image-only PDFs yield no text | Use a PDF with a text layer, or enable OCR in `PdfPipelineOptions` |
| Port 8000 already in use | A previous stage is still running | `run.sh` stops it for you; otherwise `fuser -k 8000/tcp` |
| `SQL0613N ... URL... is too long` applying the schema | `UNIQUE` builds an index, and Db2 caps index key length by page size — 1024 bytes at 4K, 2048 at 8K | The shipped schema uses `VARCHAR(2000)`, which fits an 8K database. On a 4K database lower it to `VARCHAR(1000)`, or create the database with a larger page size |
| A saved document is titled `Page Not Found` | The fetch returned an error page and it was stored anyway | `DELETE FROM DOCUMENTS WHERE ID = n`, then check the URL resolves |

### Files

```
stages/00-basic/    app.py · requirements.txt · run.sh          filesystem version
stages/01-db2/      app.py · requirements.txt · run.sh          Db2 version
                    schema.sql                                  DOCUMENTS table, idempotent
```

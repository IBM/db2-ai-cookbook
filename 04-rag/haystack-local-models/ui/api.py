#!/usr/bin/env python3
"""Live backend for the RAG demo UI (`./ui/run.sh`).

A thin wrapper over the two pipelines in src/haystack_db2_rag/. It adds no retrieval or
generation logic of its own — it calls ingest_pdf() and ask(), the same functions the
CLI entry points call, and streams Haystack's own component spans to the browser so the
page can show each step as it runs.

There is no offline mode: ingesting a PDF and answering from Db2 are both live actions.
Both llama.cpp servers must be up (scripts/llama-servers.sh start) and Db2 reachable.

Single user, no authentication, loopback by default. See the note in run.sh.
"""

import json
import os
import queue
from collections import OrderedDict
import threading
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from haystack_db2_rag import settings
from haystack_db2_rag.ingest import ingest_pdf
from haystack_db2_rag.search import ask
from haystack_db2_rag.store import open_store
from haystack_db2_rag.trace import collecting, enable_step_tracing

import sample_sql
import show_code

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
UPLOADS = REPO / "data" / "uploads"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

app = FastAPI(title="Db2 + Haystack RAG Demo", docs_url="/docs")

# Install the component tracer once. Spans raised on a thread with no queue registered
# are dropped, so this is inert outside a running job.
enable_step_tracing()


# --------------------------------------------------------------------------- jobs
# Ingest takes ~50 s and a search ~10 s, and both want the same live step timeline, so
# they share one job runner rather than two transports. A job is a thread plus the queue
# its component events land in; the SSE route drains that queue.

# Bounded on purpose: a job whose SSE stream is never opened (the tab was closed between
# the POST and the stream) would otherwise sit in here forever. Evicting it only drops the
# handle — the thread already running still finishes its work.
JOBS: "OrderedDict[str, queue.Queue]" = OrderedDict()
MAX_TRACKED_JOBS = 16
DONE = object()  # sentinel: nothing further will be queued for this job


def start_job(work) -> str:
    """Run `work()` on its own thread, collecting its component events. Returns a job id.

    Each job builds its own document store, and therefore its own ibm_db connection, on
    its own thread — ibm_db handles are not safe to move between threads.
    """
    job_id = uuid.uuid4().hex
    events: queue.Queue = queue.Queue()
    JOBS[job_id] = events
    while len(JOBS) > MAX_TRACKED_JOBS:
        JOBS.popitem(last=False)

    def run():
        try:
            with collecting(events):
                result = work()
            events.put({"phase": "result", "data": result})
        except Exception as error:  # surfaced in the UI, not swallowed
            events.put({"phase": "failed", "error": f"{type(error).__name__}: {error}"})
        finally:
            events.put(DONE)

    threading.Thread(target=run, daemon=True).start()
    return job_id


@app.get("/api/jobs/{job_id}/events")
def job_events(job_id: str):
    """Server-sent events: one `step` per component as it starts and finishes, then a
    single terminal `result` or `failed`."""
    events = JOBS.get(job_id)
    if events is None:
        raise HTTPException(404, "unknown job")

    def stream():
        # finally, not just on DONE: if the browser goes away mid-stream Starlette closes
        # this generator, and the job must still be forgotten.
        try:
            while True:
                event = events.get()
                if event is DONE:
                    return
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            JOBS.pop(job_id, None)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _served_model(base_url: str) -> str | None:
    """The model id a llama.cpp server reports, or None if it is not answering."""
    try:
        with urllib.request.urlopen(f"{base_url}/models", timeout=2) as response:
            return json.load(response)["data"][0]["id"]
    except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError):
        return None


SERVER_URL = {"embedding": settings.EMBED_BASE_URL, "chat": settings.CHAT_BASE_URL}


def require_servers(*needed: str) -> None:
    """Refuse the job up front if a model server it needs is not answering.

    Worth doing rather than letting the pipeline discover it: OpenAIDocumentEmbedder does
    NOT raise on a connection error — it logs each failed batch, retries with backoff, and
    hands on documents with no embedding at all. The run then takes minutes to arrive at a
    confusing failure in the writer. Checking first turns that into one clear sentence.
    """
    down = [label for label in needed if not _served_model(SERVER_URL[label])]
    if down:
        raise HTTPException(503, f"The {' and '.join(down)} model server is not running. "
                                 f"Start it with:  scripts/llama-servers.sh start")


# ------------------------------------------------------------------------- ingest


@app.post("/api/ingest")
async def start_ingest(file: UploadFile = File(...)):
    """Upload a PDF and index it. This REPLACES the table — see recreate_table in ingest.py."""
    require_servers("embedding")
    name = Path(file.filename or "").name  # strip any directory the browser sent
    if not name.lower().endswith(".pdf"):
        raise HTTPException(400, "Only .pdf files can be ingested.")

    UPLOADS.mkdir(parents=True, exist_ok=True)
    target = UPLOADS / name
    size = 0
    with open(target, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                out.close()
                target.unlink(missing_ok=True)
                raise HTTPException(413, f"PDF is larger than {MAX_UPLOAD_BYTES // 1024 // 1024} MB.")
            out.write(chunk)
    if size == 0:
        target.unlink(missing_ok=True)
        raise HTTPException(400, "That file is empty.")

    return {"job_id": start_job(lambda: ingest_pdf(str(target))), "filename": name}


# ------------------------------------------------------------------------- search


class Question(BaseModel):
    question: str
    top_k: int = 3
    page: int | None = None
    section: str | None = None
    tables_only: bool = False


@app.post("/api/search")
def start_search(q: Question):
    """Ask a question. The filters narrow the rows in Db2 *before* the vector search."""
    if not q.question.strip():
        raise HTTPException(400, "Ask a question first.")
    require_servers("embedding", "chat")
    return {"job_id": start_job(
        lambda: ask(q.question.strip(), q.page, q.section, q.tables_only, q.top_k))}


# ------------------------------------------------------------- status / facets / code


@app.get("/api/status")
def status():
    """What the page's header strip shows: both model servers, and what is indexed."""
    embed = _served_model(settings.EMBED_BASE_URL)
    chat = _served_model(settings.CHAT_BASE_URL)
    index: dict = {"table": settings.DB2_TABLE}
    try:
        with open_store() as store:
            index["chunks"] = store.count_documents()
            index["sources"] = [s for s in store.get_metadata_field_unique_values("source") if s]
    except Exception as error:
        index["error"] = f"{type(error).__name__}: {error}"
    return {
        "embed": {"url": settings.EMBED_BASE_URL, "expected": settings.EMBED_MODEL, "served": embed},
        "chat": {"url": settings.CHAT_BASE_URL, "expected": settings.CHAT_MODEL, "served": chat},
        "index": index,
    }


@app.get("/api/facets")
def facets():
    """Values for the Search tab's filters, read straight off the stored metadata."""
    try:
        with open_store() as store:
            return {
                "sections": [s for s in store.get_metadata_field_unique_values("section") if s],
                "pages": store.get_metadata_field_min_max("page_number"),
            }
    except Exception as error:
        raise HTTPException(503, f"Db2 unreachable: {type(error).__name__}: {error}")


@app.get("/api/sample")
def sample(limit: int = 5):
    """A few real rows from the Db2 table, read with plain SQL — see ui/sample_sql.py."""
    try:
        return sample_sql.sample(limit)
    except Exception as error:
        raise HTTPException(503, f"Could not read the table: {type(error).__name__}: {error}")


@app.get("/api/code/{key}")
def code(key: str):
    """The real source behind a workflow — full file plus a snippet per component."""
    if key not in show_code.MODULES:
        raise HTTPException(404, "unknown workflow")
    return show_code.for_module(key)


class NoCacheHTML(StaticFiles):
    """StaticFiles, but HTML always revalidates. index.html carries the ?v= busters for
    the JS/CSS and nothing busts index.html itself, so a browser holding a stale copy
    pairs old markup with new scripts and renders a blank page with no console error.
    "no-cache" still permits a 304 via the ETag, so the revalidation is cheap."""

    def file_response(self, full_path, *args, **kwargs):
        response = super().file_response(full_path, *args, **kwargs)
        if str(full_path).endswith(".html"):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


# API routes above take precedence over this mount.
app.mount("/", NoCacheHTML(directory=os.path.join(HERE, "static"), html=True), name="static")

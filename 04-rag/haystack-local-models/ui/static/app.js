"use strict";

// Shared plumbing: tabs, the status strip, the step timeline widget, the SSE job runner,
// and the "Show code" cache. ingest.js and search.js drive it.

const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// Notes are our prose, not file content, so they may carry a little markup. Escaped
// first, then `code` and **bold** are re-introduced — never the other way round.
const md = (s) => esc(s)
  .replace(/`([^`]+)`/g, "<code>$1</code>")
  .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");

// The components of each pipeline, in run order. `name` is the string the pipeline was
// built with in ingest.py / search.py — the same key Haystack reports on its trace span
// and the same key ui/show_code.py cuts the snippet by, so all three line up.
//
// `note` is what appears under the code: one line per argument, then in -> out. Kept to
// a line each on purpose — it should be skimmable next to the code, not read as prose.
const STEPS = {
  ingest: [
    { name: "converter", type: "DoclingConverter", stage: "parse",
      blurb: "Docling reads the PDF's layout, then HybridChunker splits it on the document's own structure — headings and tables — up to a 448-token budget.",
      note: {
        args: [
          ["export_type=DOC_CHUNKS", "one Document per chunk, not one per file"],
          ["chunker", "splits on headings and tables, 448 tokens max"],
          ["meta_extractor", "picks which Docling fields reach Db2"],
        ],
        io: "PDF path → Documents with text and metadata, no vectors yet",
      } },
    { name: "embedder", type: "OpenAIDocumentEmbedder", stage: "embed",
      blurb: "Each chunk goes to bge-small-en-v1.5 on :8081 and comes back as 384 numbers.",
      note: {
        args: [
          ["api_base_url", "llama.cpp on :8081"],
          ["model", "bge-small-en-v1.5"],
          ["api_key", "dummy — llama.cpp ignores it, the OpenAI client demands one"],
        ],
        io: "Documents → the same Documents with `.embedding` set (384 floats each)",
      } },
    { name: "writer", type: "DocumentWriter", stage: "store",
      blurb: "One row per chunk in Db2: id, content, BSON metadata, and the VECTOR(384, FLOAT32).",
      note: {
        args: [
          ["document_store", "already knows the table, the 384 dimensions and COSINE"],
        ],
        io: "embedded Documents → a row count. The DROP and CREATE happen here.",
      } },
  ],
  search: [
    { name: "text_embedder", type: "OpenAITextEmbedder", stage: "embed",
      blurb: "The question is embedded by the same model that embedded the chunks — with the bge query prefix, which the documents do not get.",
      note: {
        args: [
          ["model", "the same one used at ingest — the invariant search rests on"],
          ["prefix", "bge's query instruction; questions only, never the chunks"],
        ],
        io: "question → one 384-float vector",
      } },
    { name: "retriever", type: "IBMDb2EmbeddingRetriever", stage: "retrieve",
      blurb: "Db2 ranks the rows by VECTOR_DISTANCE with COSINE and returns the closest top-k. Any filters were applied before this ranking.",
      note: {
        args: [
          ["document_store", "where to search"],
          ["top_k", "how many chunks to return"],
          ["filters", "not here — passed per run instead"],
        ],
        io: "query vector → Documents ranked by `VECTOR_DISTANCE(..., COSINE)`; `.score` is a distance, so lower is closer",
      } },
    { name: "prompt_builder", type: "ChatPromptBuilder", stage: "prompt",
      blurb: "The retrieved chunks are pasted into the Jinja template as the only allowed evidence.",
      note: {
        args: [
          ["template", "a list of ChatMessage, because the generator is a chat model"],
        ],
        io: "documents (from the retriever) + question → rendered messages",
      } },
    { name: "generator", type: "OpenAIChatGenerator", stage: "generate",
      blurb: "Qwen2.5-3B-Instruct on :8080 answers at temperature 0, so the same question gives the same answer.",
      note: {
        args: [
          ["api_base_url", "llama.cpp on :8080"],
          ["model", "qwen2.5-3b-instruct"],
          ["temperature: 0", "greedy decoding — same question, same answer"],
        ],
        io: "messages → replies",
      } },
  ],
};

/* ---------------------------------------------------------------- Show code ---- */

// Notes for the two blocks that are not a single component.
const BLOCK_NOTES = {
  ingest: {
    connections: { text: "Both hops carry Documents, so the socket names can be left off — " +
      "one output, one input, nothing to disambiguate. The strings must match the " +
      "`add_component()` names." },
  },
  search: {
    connections: { text: "Socket names are spelled out here (`text_embedder.embedding` → " +
      "`retriever.query_embedding`) because these components have more than one input or " +
      "output." },
    prompt: { text: "Two Jinja inputs: `documents`, looped in as the evidence, and " +
      "`question`. The first sentence is what keeps the answer grounded." },
  },
};

// Renders a `note`: either free text, or an argument list plus one in -> out line.
function noteHtml(note) {
  if (!note) return "";
  if (note.text) return `<p class="code-note">${md(note.text)}</p>`;
  const args = (note.args || [])
    .map(([name, what]) => `<li><code>${esc(name)}</code><span>${md(what)}</span></li>`)
    .join("");
  return `<div class="code-note">` +
    (args ? `<ul class="code-args">${args}</ul>` : "") +
    (note.io ? `<p class="code-io">${md(note.io)}</p>` : "") + `</div>`;
}

const codeCache = {};
function getCode(key) {
  if (!codeCache[key]) {
    codeCache[key] = fetch(`/api/code/${key}`, { cache: "no-store" })
      .then((r) => { if (!r.ok) throw new Error("could not load the source"); return r.json(); });
  }
  return codeCache[key];
}

// Fill each step's disclosure with its own add_component() call, and the page-level
// disclosure with the whole file. Fetched fresh on every page load, never bundled — edit
// the .py file, reload, and the shown code changes.
async function loadCode(key) {
  let payload;
  try { payload = await getCode(key); }
  catch (_) { return; }

  document.querySelectorAll(`#${key}-timeline .step`).forEach((card) => {
    const snippet = payload.steps[card.dataset.step];
    const body = card.querySelector(".step-code-body");
    if (snippet && body) body.innerHTML = codeBlock(snippet);
  });

  const full = document.querySelector(`.fullsrc[data-code="${key}"] .fullsrc-body`);
  if (!full) return;
  const notes = BLOCK_NOTES[key] || {};
  const wiring = payload.connections.length
    ? `<p class="code-label">How they are wired</p>${codeBlock(payload.connections.join("\n"))}` +
      noteHtml(notes.connections) : "";
  const prompt = payload.prompt
    ? `<p class="code-label">The prompt template</p>${codeBlock(payload.prompt)}` +
      noteHtml(notes.prompt) : "";
  full.innerHTML = wiring + prompt +
    `<p class="code-label">${esc(payload.file)}</p>${codeBlock(payload.full)}`;
}

/* ----------------------------------------------------------------- timeline ---- */

function renderTimeline(key) {
  const host = $(`#${key}-timeline`);
  host.innerHTML = STEPS[key].map((step, i) => `
    <article class="step stage-${step.stage}" data-step="${step.name}" data-state="pending">
      <div class="step-head">
        <span class="step-num">${i + 1}</span>
        <div class="step-title">
          <span class="step-name">${esc(step.type)}</span>
          <span class="step-key">${esc(step.name)}</span>
          <p class="step-blurb">${esc(step.blurb)}</p>
        </div>
        <span class="step-meta">
          <span class="step-detail"></span>
          <span class="step-time"></span>
        </span>
      </div>
      <details class="step-code"><summary>Show code</summary>
        <div class="step-code-body"><p class="muted">loading…</p></div>
        ${noteHtml(step.note)}
      </details>
    </article>`).join("");
  loadCode(key);
  return host;
}

function resetTimeline(key) {
  document.querySelectorAll(`#${key}-timeline .step`).forEach((card) => {
    card.dataset.state = "pending";
    card.querySelector(".step-detail").textContent = "";
    card.querySelector(".step-time").textContent = "";
  });
}

// The converter step alone runs ~35 s, so a running card counts up rather than sitting
// still — otherwise a long parse is indistinguishable from a hang.
let ticker = null;
function startTicker(card) {
  stopTicker();
  const began = performance.now();
  const time = card.querySelector(".step-time");
  ticker = setInterval(() => {
    time.textContent = `${((performance.now() - began) / 1000).toFixed(1)}s`;
  }, 100);
}
function stopTicker() {
  if (ticker) { clearInterval(ticker); ticker = null; }
}

function applyStep(key, event) {
  const card = document.querySelector(`#${key}-timeline .step[data-step="${event.name}"]`);
  if (!card) return;
  if (event.phase === "start") {
    card.dataset.state = "running";
    startTicker(card);
    return;
  }
  stopTicker();
  card.dataset.state = event.phase === "error" ? "error" : "done";
  card.querySelector(".step-time").textContent = `${event.elapsed.toFixed(2)}s`;
  card.querySelector(".step-detail").textContent = event.detail || "";
}

/* --------------------------------------------------------------- job runner ---- */

// Every job — ingest or search — reports through the same SSE stream: component events
// as they happen, then exactly one terminal result.
function runJob(jobId, onStep) {
  return new Promise((resolve, reject) => {
    const source = new EventSource(`/api/jobs/${jobId}/events`);
    let settled = false;
    const finish = (fn, value) => { settled = true; source.close(); stopTicker(); fn(value); };

    source.onmessage = (message) => {
      const event = JSON.parse(message.data);
      if (event.phase === "result") return finish(resolve, event.data);
      if (event.phase === "failed") return finish(reject, new Error(event.error));
      onStep(event);
    };
    // Fires on a normal close too, so only treat it as failure if nothing terminal came.
    source.onerror = () => {
      if (!settled) finish(reject, new Error("Lost the connection to the server."));
    };
  });
}

async function startJob(url, init) {
  const response = await fetch(url, init);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `Request failed (${response.status}).`);
  return payload;
}

function showError(key, error) {
  const box = $(`#${key}-error`);
  box.textContent = error.message;
  box.hidden = false;
}
function clearError(key) { $(`#${key}-error`).hidden = true; }

/* ------------------------------------------------------------------- status ---- */

let STATUS = null;

function serverDot(label, info) {
  const up = Boolean(info.served);
  const detail = up ? esc(info.served) : "down";
  const title = up ? `${label} model server at ${info.url}`
                   : `${label} server not answering at ${info.url} — run: scripts/llama-servers.sh start`;
  return `<span class="dot-line" title="${esc(title)}">
    <span class="dot ${up ? "dot-up" : "dot-down"}"></span>${label} ${detail}</span>`;
}

async function refreshStatus() {
  const host = $("#status");
  try {
    STATUS = await (await fetch("/api/status", { cache: "no-store" })).json();
  } catch (_) {
    host.innerHTML = `<span class="dot-line"><span class="dot dot-down"></span>backend unreachable</span>`;
    return null;
  }
  const index = STATUS.index;
  const indexText = index.error
    ? `<span class="dot-line" title="${esc(index.error)}"><span class="dot dot-down"></span>Db2 unreachable</span>`
    : `<span class="dot-line"><span class="dot dot-up"></span>${esc(index.table)} · ${index.chunks} chunks</span>`;
  host.innerHTML = serverDot("embed", STATUS.embed) + serverDot("chat", STATUS.chat) + indexText;
  updateReplaceWarning();
  return STATUS;
}

function updateReplaceWarning() {
  const target = $("#replace-state");
  if (!target || !STATUS) return;
  const index = STATUS.index;
  if (index.error) { target.textContent = "Db2 is not reachable right now."; return; }
  if (!index.chunks) { target.textContent = `${index.table} is currently empty.`; return; }
  const sources = index.sources && index.sources.length ? ` from ${index.sources.join(", ")}` : "";
  target.textContent = `${index.table} currently holds ${index.chunks} chunks${sources}.`;
}

/* --------------------------------------------------------------------- tabs ---- */

function wireTabs() {
  const tabs = document.querySelectorAll("#tabs .tab");
  tabs.forEach((tab) => tab.addEventListener("click", () => {
    tabs.forEach((other) => {
      const on = other === tab;
      other.setAttribute("aria-selected", String(on));
      $(`#page-${other.dataset.page}`).hidden = !on;
    });
  }));
}

/* --------------------------------------------------------------------- boot ---- */

async function boot() {
  wireTabs();
  renderTimeline("ingest");
  renderTimeline("search");
  wireIngest();
  wireSearch();
  await refreshStatus();
  loadFacets();
}

document.addEventListener("DOMContentLoaded", boot);

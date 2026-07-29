"use strict";

// Search tab = open-ended search: type anything, see the top 5 results from all
// three strategies side by side. Needs the live backend (./ui/run.sh --live) since
// arbitrary queries must hit Db2. The Golden-eval tab reads the frozen eval_set.json.

// mode: the single-search leg (keyword|hybrid|rerank). compare: two of those legs to
// show side by side. fu = plain (rerank=0) response; rr = reranked (rerank=1) response.
const state = { mode: "hybrid", compare: [], fu: null, rr: null };
let LIVE = false;      // /api/search reachable (live backend up)?
let EVAL = null;       // eval_set.json (featured queries + their gold answers)

const TOP = 5;         // results shown per strategy
const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const TYPE_LABEL = { keyword: "Lexical", semantic: "Semantic", mixed: "Mixed" };
const legChip = (leg) => leg === "bm25"
  ? '<span class="chip chip-bm25">Lexical</span>'
  : '<span class="chip chip-vector">Semantic</span>';

// Highlight the query's terms inside an already-escaped chunk (lexical results).
const HL_STOP = new Set(("the a an of to in on and or for with your you how what is are do it this that " +
  "by we our not into out up who i be book books looking find need want about one").split(" "));
function queryTerms(q) {
  return [...new Set(String(q || "").toLowerCase().match(/[a-z0-9]+/g) || [])]
    .filter((w) => w.length > 2 && !HL_STOP.has(w));
}
function highlight(escaped, terms) {
  if (!terms || !terms.length) return escaped;
  const re = new RegExp("(" + terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + ")", "gi");
  return escaped.replace(re, "<mark>$1</mark>");
}

/* ---------- boot ---------- */
async function boot() {
  try { LIVE = (await fetch("/api/queries", { cache: "no-store" })).ok; }
  catch (_) { LIVE = false; }
  try { EVAL = await (await fetch("eval_set.json", { cache: "no-store" })).json(); }
  catch (_) { EVAL = null; }
  renderEval();
  wire();
}

/* ---------- golden eval set page ---------- */
function renderEval() {
  const host = $("#eval-list");
  if (!host) return;
  if (!EVAL || !EVAL.queries || !EVAL.queries.length) {
    host.innerHTML = `<p class="placeholder">No eval set found —
      run <code>./ui/build_eval_set.sh</code> to generate it.</p>`;
    return;
  }
  host.innerHTML = EVAL.queries.map((q, i) => {
    const type = TYPE_LABEL[q.query_type] || q.query_type;
    const n = q.gold.length;
    const passages = q.gold.map((g) => {
      const preview = String(g.text).replace(/\s+/g, " ").trim();
      return `
      <div class="gold-passage" title="Click to expand">
        <span class="cid">#${g.chunk_id}</span>
        <div class="gp-body">
          <span class="snip">${esc(preview)}</span>
          <div class="full">${esc(g.text)}</div>
        </div>
        <span class="gp-caret" aria-hidden="true">▸</span>
      </div>`;
    }).join("");
    return `<article class="eval-card">
      <div class="eval-q">
        <span class="qnum">${i + 1}</span>
        <span class="qtext">${esc(q.query)}</span>
        <span class="type type-${q.query_type}">${type}</span>
      </div>
      ${q.note ? `<p class="eval-why">${esc(q.note)}</p>` : ""}
      <div class="eval-gold-head">Gold answer${n > 1 ? "s" : ""}
        <span>· the book${n > 1 ? "s" : ""} search should find</span></div>
      ${passages}
    </article>`;
  }).join("");
}

/* ---------- nav ---------- */
function setPage(page) {
  document.querySelectorAll("#tabs .tab").forEach((t) =>
    t.setAttribute("aria-selected", String(t.dataset.page === page)));
  // Generic: show #page-<page>, hide the rest. Force display too, so hiding works
  // even if an older/cached stylesheet lacks the [hidden] override.
  document.querySelectorAll('[id^="page-"]').forEach((sec) => {
    const on = sec.id === "page-" + page;
    sec.hidden = !on;
    sec.style.display = on ? "" : "none";
  });
}

/* ---------- controls ---------- */
const MODES = ["keyword", "hybrid", "rerank"];
const LEG = {
  keyword: { label: "Keyword", dot: "bm25" },
  hybrid:  { label: "Hybrid",  dot: "hyb" },
  rerank:  { label: "Rerank",  dot: "rr" },
};

// Reflect state in the controls: the active single-mode button is pressed unless a
// two-leg Compare is active (then none is), and the Compare checkboxes mirror state.
function refreshControls() {
  const comparing = state.compare.length === 2;
  MODES.forEach((m) => {
    $("#mode-" + m).setAttribute("aria-pressed", String(!comparing && state.mode === m));
    $("#cmp-" + m).checked = state.compare.includes(m);
  });
}

// A single-mode button: exclusive search in that leg. Clears any Compare selection.
function setMode(mode) {
  state.mode = mode;
  state.compare = [];
  refreshControls();
  run();
}

// A Compare checkbox toggled. At most two legs — checking a third drops the oldest.
// The comparison runs as soon as two are selected; dropping below two returns to the
// single-mode view.
function toggleCompare(leg, checked) {
  if (checked) {
    if (!state.compare.includes(leg)) state.compare.push(leg);
    while (state.compare.length > 2) state.compare.shift();
  } else {
    state.compare = state.compare.filter((x) => x !== leg);
  }
  refreshControls();
  if (state.compare.length === 2) run();
  else if (state.fu) render();
}

function wire() {
  $("#tabs").addEventListener("click", (e) => {
    const t = e.target.closest(".tab"); if (!t) return;
    setPage(t.dataset.page);
  });
  $("#eval-list").addEventListener("click", (e) => {
    const gp = e.target.closest(".gold-passage"); if (gp) gp.classList.toggle("open");
  });
  // Enter searches: a two-leg Compare if two are ticked, else the current single mode.
  $("#searchbox").addEventListener("keydown", (e) => { if (e.key === "Enter") run(); });
  MODES.forEach((m) => {
    $("#mode-" + m).addEventListener("click", () => setMode(m));
    $("#cmp-" + m).addEventListener("change", (e) => toggleCompare(m, e.target.checked));
  });
  $("#output").addEventListener("click", (e) => {
    const row = e.target.closest(".row"); if (row) row.classList.toggle("open");
  });
}

/* ---------- run + render ---------- */
// keyword/hybrid come from the plain (rerank=0) response; rerank from the reranked
// (rerank=1) response's hybrid leg.
function legResults(leg) {
  if (leg === "keyword") return (state.fu && state.fu.lexical.results) || [];
  if (leg === "hybrid")  return (state.fu && state.fu.hybrid.results) || [];
  if (leg === "rerank")  return (state.rr && state.rr.hybrid.results) || [];
  return [];
}

async function run() {
  const text = $("#searchbox").value.trim();
  if (!text) return;
  if (!LIVE) {
    $("#output").innerHTML = `<p class="placeholder">Open-ended search needs the live backend —
      run <code>./ui/run.sh --live</code>, then search any query here.</p>`;
    state.fu = null; return;
  }
  const legs = state.compare.length === 2 ? state.compare : [state.mode];
  const needRerank = legs.includes("rerank");
  $("#output").innerHTML = `<p class="placeholder">Searching…</p>`;
  const enc = encodeURIComponent(text);
  try {
    const fu = await fetch(`/api/search?q=${enc}&rerank=0`).then((r) => { if (!r.ok) throw 0; return r.json(); });
    let rr = null;
    if (needRerank) {
      rr = await fetch(`/api/search?q=${enc}&rerank=1`).then((r) => { if (!r.ok) throw 0; return r.json(); });
      // Reranker requested but unreachable: say so, don't pass off fusion order as reranked.
      if (rr.rerank_unavailable) {
        $("#output").innerHTML = `<p class="placeholder rerank-err">
          <b>Reranker is not available.</b> The reranker server (<code>:8087</code>) isn't
          reachable. Start it with <code>./scripts/0_start-services.sh</code> (needs the
          bge-reranker model — see the README), then try Rerank again.</p>`;
        state.fu = null; state.rr = null; return;
      }
    }
    state.fu = fu; state.rr = rr;
    render();
  } catch (_) {
    $("#output").innerHTML = `<p class="placeholder">Search failed — is the live backend running?</p>`;
    state.fu = null;
  }
}

// Compare (two legs) → two collapsed columns, side by side. Single mode → one column
// of expanded cards (cover, title, author, click-to-expand description).
function render() {
  if (!state.fu) return;
  if (state.compare.length === 2) {
    // Always render the two columns in the fixed button order (Keyword · Hybrid ·
    // Rerank), regardless of which was ticked first.
    const [a, b] = MODES.filter((m) => state.compare.includes(m));
    $("#output").innerHTML = compareView(a, b);
  } else {
    $("#output").innerHTML = singleView(state.mode);
    markClamped($("#output"));
  }
}

// A description longer than its 3-line clamp gets a "Show more" affordance; measured
// after layout. Clicking the card (#output handler toggles .open) un-clamps it.
function markClamped(root) {
  root.querySelectorAll(".row").forEach((row) => {
    const d = row.querySelector(".rdesc");
    if (d && d.scrollHeight - d.clientHeight > 2) row.classList.add("clamped");
  });
}

// The book's cover thumbnail (path from Db2). Neutral placeholder when missing/broken.
function coverImg(r) {
  return r && r.cover
    ? `<img class="cover" src="${esc(r.cover)}" alt="" loading="lazy"
         onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'cover cover-missing'}))">`
    : `<span class="cover cover-missing" aria-hidden="true"></span>`;
}

// Expanded card (single mode): cover, title, author, and the description shown clamped
// (click the card to reveal it in full).
function resultCard(r, hl) {
  const title = r.title || r.snippet || "";
  const desc = r.description || r.text || "";
  return `<div class="row">
    ${coverImg(r)}
    <div class="rbody">
      <div class="rline"><span class="rank">${r.rank}</span><span class="rtitle">${highlight(esc(title), hl)}</span></div>
      ${r.author ? `<div class="rby">by ${esc(r.author)}</div>` : ""}
      ${desc ? `<div class="rdesc">${highlight(esc(desc), hl)}</div><span class="rmore" aria-hidden="true"></span>` : ""}
    </div>
  </div>`;
}

// Collapsed card (compare columns): cover, title, author — no description.
function compactCard(r, hl) {
  const title = r.title || r.snippet || "";
  return `<div class="row row-compact">
    ${coverImg(r)}
    <div class="rbody">
      <div class="rline"><span class="rank">${r.rank}</span><span class="rtitle">${highlight(esc(title), hl)}</span></div>
      ${r.author ? `<div class="rby">by ${esc(r.author)}</div>` : ""}
    </div>
  </div>`;
}

// One leg, expanded, single column.
function singleView(leg) {
  const meta = LEG[leg];
  const terms = queryTerms(state.fu.query);
  const results = legResults(leg).slice(0, TOP);
  if (!results.length) return `<p class="placeholder">No results.</p>`;
  return `<h3 class="results-h"><span class="dot ${meta.dot}"></span>Top ${results.length} · ${meta.label}</h3>
    <div class="rows">${results.map((r) => resultCard(r, terms)).join("")}</div>`;
}

// Two legs, collapsed, side by side.
function compareView(a, b) {
  const terms = queryTerms(state.fu.query);
  const col = (leg) => {
    const meta = LEG[leg];
    const rows = legResults(leg).slice(0, TOP).map((r) => compactCard(r, terms)).join("")
      || `<p class="placeholder">No results.</p>`;
    return `<div class="cmp-col">
      <h3 class="results-h"><span class="dot ${meta.dot}"></span>${meta.label}</h3>
      <div class="rows">${rows}</div></div>`;
  };
  return `<div class="cmp-grid">${col(a)}${col(b)}</div>`;
}

boot();

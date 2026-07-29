"use strict";
/* Demo view — mixed-audience "does search find my book?" page. Thin renderer:
   verdicts + book labels are precomputed in demo_fixtures.json by ui/demo_view.py
   (offline) or /api/demo (live). No verdict logic here — just presentation.

   demo_fixtures.json:
     view_models       : { id -> view_model }  (curated "r*" + golden-pool "g*")
     pool_by_type      : { keyword|semantic|mixed -> [golden ids] }  (Shuffle draws here)
     representative    : [curated ids, ordered]                      (shown on load / by the button)
*/

const D = {
  fx: null,            // demo_fixtures.json
  live: false,         // /api/demo reachable?
  tech: false,         // Simple/Technical toggle
  current: null,       // current view_model
  seen: new Map(),     // id -> view_model, session coverage
  order: [],           // ids currently shown as chips
};
const dq = (s) => document.querySelector(s);
const desc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const STRATS = ["lexical", "vector", "hybrid"];
const SLABEL = { lexical: "Lexical", vector: "Semantic", hybrid: "Hybrid" };
const SCORE_LABEL = { bm25: "lexical", cosine: "semantic", fused: "fused" };
const SDOT = { lexical: "bm25", vector: "vec", hybrid: "hyb" };
const VERDICT = {
  found:   { icon: "✓", label: "Found it" },
  wrong:   { icon: "✗", label: "Wrong book" },
  nothing: { icon: "∅", label: "Nothing found" },
};

async function demoBoot() {
  try { D.fx = await (await fetch("demo_fixtures.json", { cache: "no-store" })).json(); }
  catch (_) { D.fx = null; }
  try { D.live = (await fetch("/api/demo_deck", { cache: "no-store" })).ok; }
  catch (_) { D.live = false; }
  D.order = ((D.fx && D.fx.representative) || []).slice();   // start on the curated set
  renderChips();
  renderScoreboard();
  demoWire();
}

/* ---------- data access ---------- */
function vmById(id) { return D.fx && D.fx.view_models[id]; }
function allVMs() { return D.fx ? Object.values(D.fx.view_models) : []; }
function displayVMs() { return D.order.map(vmById).filter(Boolean); }
// query_type "keyword" is shown as "lexical" for consistent leg naming
function SLABEL_TYPE(t) { return ({ keyword: "lexical", semantic: "semantic", mixed: "mixed" })[t] || t; }

function sampleK(arr, k) {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a.slice(0, k);
}

/* ---------- session / deck controls ---------- */
function resetSession() {
  D.seen.clear();
  D.current = null;
  dq("#demo-scenario").innerHTML = "";
  dq("#demo-panels").innerHTML =
    `<p class="placeholder">Tap an example query on the left to see all three strategies at once.</p>`;
  document.querySelectorAll(".dchip").forEach((x) => x.classList.remove("active"));
  renderScoreboard();
}

// Shuffle: draw a NEW set of golden eval queries (3 per type) from the pool.
function shuffleDeck() {
  const pt = (D.fx && D.fx.pool_by_type) || {};
  let ids = [];
  ["keyword", "semantic", "mixed"].forEach((t) => { ids = ids.concat(sampleK(pt[t] || [], 3)); });
  ids = sampleK(ids, ids.length);          // interleave the types
  if (ids.length) D.order = ids;
  renderChips();
  resetSession();                          // a fresh draw starts a fresh scoreboard
}

// Representative set: restore the curated set and show its coverage (scoreboard only).
function loadRepresentative() {
  D.order = ((D.fx && D.fx.representative) || []).slice();
  renderChips();
  document.querySelectorAll(".dchip").forEach((x) => x.classList.remove("active"));
  D.current = null;
  dq("#demo-scenario").innerHTML = "";
  dq("#demo-panels").innerHTML =
    `<p class="placeholder">Coverage across the representative set is below.</p>`;
  D.seen = new Map(D.order.map((id) => [id, vmById(id)]).filter(([, vm]) => vm));
  renderScoreboard();
}

function renderChips() {
  const host = dq("#demo-chips");
  if (!host) return;
  host.innerHTML = displayVMs().map((vm) => `
    <button class="dchip type-${desc(vm.query_type)}" data-id="${desc(vm.id)}"
            role="button" aria-label="Example query: ${desc(vm.query)}">
      <span class="dchip-q">${desc(vm.query)}</span>
      <span class="dchip-t">${desc(SLABEL_TYPE(vm.query_type))}</span>
    </button>`).join("");
}

/* ---------- run + render ---------- */
function showVM(vm) {
  D.current = vm;
  D.seen.set(vm.id, vm);
  renderQuery(vm);
  renderScoreboard();
}

async function demoSearch(text) {
  if (!text) return;
  let vm = allVMs().find((v) => v.query === text);
  if (!vm && D.live) {
    try {
      const r = await fetch("/api/demo?q=" + encodeURIComponent(text));
      if (r.ok) vm = await r.json();
    } catch (_) { /* fall through */ }
  }
  if (!vm) {
    dq("#demo-scenario").textContent = "";
    dq("#demo-panels").innerHTML =
      `<p class="placeholder">That query isn't in the frozen demo set. Tap an example on the left,
       or run <code>./ui/run.sh --live</code> for ad-hoc search.</p>`;
    return;
  }
  showVM(vm);
}

function renderQuery(vm) {
  dq("#demo-scenario").innerHTML = vm.scenario ? `<b>Scenario:</b> ${desc(vm.scenario)}` : "";
  dq("#demo-panels").innerHTML = STRATS.map((s) => panelHtml(s, vm.strategies[s])).join("");
}

function panelHtml(strat, st) {
  const v = VERDICT[st.verdict] || VERDICT.nothing;
  let body;
  if (st.verdict === "nothing") {
    body = `<p class="dnote">No results — nothing in the index matched those words.</p>`;
  } else {
    const b = st.shown || {};
    const wrongTag = st.verdict === "wrong"
      ? `<span class="dwrong-tag">not what you meant</span>` : "";
    body = `<div class="dbook">
        ${coverImg(b)}
        <div class="dbook-meta">
          <span class="dtitle">${desc(b.title)}</span>
          ${b.author ? `<span class="dauthor">by ${desc(b.author)}</span>` : ""}
          ${wrongTag}
        </div>
      </div>`;
  }
  return `<div class="dpanel dpanel-${st.verdict}">
    <div class="dphead">
      <span class="dstrat"><span class="dot ${SDOT[strat]}"></span>${SLABEL[strat]}</span>
      <span class="dverdict dv-${st.verdict}"><span class="dv-icon" aria-hidden="true">${v.icon}</span>${v.label}</span>
    </div>
    ${body}
    ${D.tech ? techHtml(strat, st) : ""}
  </div>`;
}

function techHtml(strat, st) {
  const parts = [];
  const gr = st.gold_rank;
  parts.push(`gold rank: <b>${gr == null ? "—" : "#" + gr}</b> (of top ${st.k}); gold ${(st.gold_ids || []).map((c) => "#" + c).join(" ")}`);
  const b = st.shown;
  if (b) {
    const sc = b.score == null ? "—" : b.score;
    const st_ = SCORE_LABEL[b.score_type] || b.score_type || "";
    parts.push(`shown: #${b.chunk_id} @ rank ${b.rank} · ${st_} <b>${sc}</b>${b.is_gold ? " · ★gold" : ""}`);
    if (strat === "hybrid" && b.found_by && b.found_by.length) {
      parts.push(`provenance: ${b.found_by.map((x) => ({ bm25: "lexical", vector: "semantic" })[x] || x).join(" + ")}`);
    }
  }
  if (strat === "hybrid" && st.fusion_note) parts.push(desc(st.fusion_note));
  return `<div class="dtech">${parts.map((p) => `<span>${p}</span>`).join("")}</div>`;
}

function renderScoreboard() {
  const host = dq("#demo-scoreboard");
  if (!host) return;
  const vms = [...D.seen.values()];
  const n = vms.length;
  if (!n) { host.innerHTML = `<p class="dsb-empty">Tap an example to build the coverage picture.</p>`; return; }
  const found = { lexical: 0, vector: 0, hybrid: 0 };
  const mrr = { lexical: 0, vector: 0, hybrid: 0 };
  const hit1 = { lexical: 0, vector: 0, hybrid: 0 };
  let ki = 0;
  vms.forEach((vm) => {
    const isKi = (vm.query_class || "known_item") === "known_item";
    if (isKi) ki++;
    STRATS.forEach((s) => {
      const st = vm.strategies[s];
      if (st.verdict === "found") {
        found[s]++;
        if (isKi && st.gold_rank) { mrr[s] += 1 / st.gold_rank; if (st.gold_rank === 1) hit1[s]++; }
      }
    });
  });
  // headline: found / not-found per strategy (coverage only; no rank-superiority claims)
  const cards = STRATS.map((s) => `
    <div class="dsb-card dsb-${s}">
      <span class="dsb-name"><span class="dot ${SDOT[s]}"></span>${SLABEL[s]}</span>
      <span class="dsb-num">found the book in <b>${found[s]} of ${n}</b></span>
      <span class="dsb-blank">${n - found[s] ? "missed " + (n - found[s]) : "no misses"}</span>
    </div>`).join("");
  // queries × methods matrix (the compact/narrow view)
  const matrix = `<table class="dsb-matrix"><caption class="sr-only">Coverage matrix: queries by method</caption>
    <thead><tr><th scope="col">query</th>${STRATS.map((s) => `<th scope="col">${SLABEL[s]}</th>`).join("")}</tr></thead>
    <tbody>${vms.map((vm) => `<tr><th scope="row">${desc(vm.query.slice(0, 34))}</th>${
      STRATS.map((s) => { const vd = vm.strategies[s].verdict; const v = VERDICT[vd];
        return `<td class="mx-${vd}"><span aria-hidden="true">${v.icon}</span><span class="sr-only">${v.label}</span></td>`; }).join("")
    }</tr>`).join("")}</tbody></table>`;
  const tech = D.tech
    ? `<p class="dsb-tech">Technical · known-item MRR: ${STRATS.map((s) => `${SLABEL[s]} ${(mrr[s] / (ki || 1)).toFixed(2)}`).join(" · ")}
       · Hits@1: ${STRATS.map((s) => `${SLABEL[s]} ${(hit1[s] / (ki || 1)).toFixed(2)}`).join(" · ")}</p>`
    : "";
  host.innerHTML = `<div class="dsb-title">Coverage this session · ${n} quer${n === 1 ? "y" : "ies"}</div>
    <div class="dsb-cards">${cards}</div>${matrix}${tech}`;
}

function demoWire() {
  dq("#demo-chips").addEventListener("click", (e) => {
    const c = e.target.closest(".dchip"); if (!c) return;
    const vm = vmById(c.dataset.id); if (!vm) return;
    document.querySelectorAll(".dchip").forEach((x) => x.classList.toggle("active", x === c));
    dq("#demo-search").value = vm.query;
    showVM(vm);
  });
  dq("#demo-search").addEventListener("keydown", (e) => { if (e.key === "Enter") demoSearch(e.target.value.trim()); });
  dq("#demo-run").addEventListener("click", () => demoSearch(dq("#demo-search").value.trim()));
  dq("#demo-shuffle").addEventListener("click", shuffleDeck);
  dq("#demo-representative").addEventListener("click", loadRepresentative);
  dq("#demo-tech").addEventListener("change", (e) => {
    D.tech = e.target.checked;
    if (D.current) renderQuery(D.current);
    renderScoreboard();
  });
}

demoBoot();

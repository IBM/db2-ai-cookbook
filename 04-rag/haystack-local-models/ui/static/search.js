"use strict";

// Search tab: ask a question, watch the four components run, then read the answer and
// the chunks it was grounded in.

function wireSearch() {
  $("#search-run").addEventListener("click", search);
  $("#question").addEventListener("keydown", (event) => {
    if (event.key === "Enter") search();
  });
}

// The section dropdown is the stored metadata, not a hard-coded list — so it follows
// whatever document was ingested last.
async function loadFacets() {
  const select = $("#f-section");
  let facets;
  try { facets = await (await fetch("/api/facets", { cache: "no-store" })).json(); }
  catch (_) { return; }
  if (!facets.sections) return;
  const current = select.value;
  select.innerHTML = '<option value="">any</option>' +
    facets.sections.map((s) => `<option value="${esc(s)}">${esc(s)}</option>`).join("");
  select.value = current;
}

function chunkCard(doc, rank) {
  const tableChip = doc.has_table ? '<span class="chip chip-table">table</span>' : "";
  const pages = doc.page_end && doc.page_end !== doc.page_number
    ? `p.${doc.page_number}–${doc.page_end}` : `p.${doc.page_number}`;
  return `
    <article class="chunk">
      <div class="chunk-head">
        <span class="rank">${rank}</span>
        <span class="score" title="cosine distance, lower is closer">${doc.score.toFixed(3)}</span>
        <span class="chunk-where">${esc(pages)} · ${esc(doc.headings || doc.section || "—")}</span>
        ${tableChip}
      </div>
      <p class="chunk-text">${esc(doc.excerpt)}</p>
    </article>`;
}

async function search() {
  const question = $("#question").value.trim();
  if (!question) return;

  const button = $("#search-run");
  button.disabled = true;
  button.textContent = "Asking…";
  clearError("search");
  resetTimeline("search");
  $("#answer-card").hidden = true;
  $("#chunks").hidden = true;

  const pageValue = $("#f-page").value;
  const body = {
    question,
    top_k: Number($("#f-topk").value) || 3,
    page: pageValue === "" ? null : Number(pageValue),
    section: $("#f-section").value || null,
    tables_only: $("#f-tables").checked,
  };

  try {
    const { job_id } = await startJob("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const result = await runJob(job_id, (event) => applyStep("search", event));

    $("#answer-text").textContent = result.answer;
    $("#answer-card").hidden = false;

    const docs = result.documents;
    $("#chunks-count").textContent = docs.length === 1 ? "1 chunk" : `${docs.length} chunks`;
    $("#chunks-list").innerHTML = docs.length
      ? docs.map((doc, i) => chunkCard(doc, i + 1)).join("")
      : `<p class="placeholder">Nothing was retrieved. Either the table is empty (ingest a PDF
         first) or the filters excluded every chunk.</p>`;
    $("#chunks").hidden = false;
  } catch (error) {
    showError("search", error);
  } finally {
    button.disabled = false;
    button.textContent = "Ask";
  }
}

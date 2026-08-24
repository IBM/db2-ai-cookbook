"use strict";

// Ingestion tab: pick a PDF, POST it, then watch the three components run.

let chosenFile = null;

function wireIngest() {
  const input = $("#pdf");
  const drop = $("#drop");
  const button = $("#ingest-run");

  const choose = (file) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      showError("ingest", new Error("Only .pdf files can be ingested."));
      return;
    }
    clearError("ingest");
    chosenFile = file;
    $("#drop-main").textContent = file.name;
    drop.classList.add("has-file");
    button.disabled = false;
  };

  input.addEventListener("change", () => choose(input.files[0]));

  ["dragenter", "dragover"].forEach((type) =>
    drop.addEventListener(type, (event) => {
      event.preventDefault();
      drop.classList.add("dragging");
    }));
  ["dragleave", "drop"].forEach((type) =>
    drop.addEventListener(type, (event) => {
      event.preventDefault();
      drop.classList.remove("dragging");
    }));
  drop.addEventListener("drop", (event) => choose(event.dataTransfer.files[0]));

  button.addEventListener("click", ingest);
}

async function ingest() {
  if (!chosenFile) return;
  const button = $("#ingest-run");
  button.disabled = true;
  button.textContent = "Ingesting…";
  clearError("ingest");
  resetTimeline("ingest");
  $("#ingest-result").hidden = true;
  $("#sample-card").hidden = true;

  const form = new FormData();
  form.append("file", chosenFile);

  try {
    const { job_id } = await startJob("/api/ingest", { method: "POST", body: form });
    const result = await runJob(job_id, (event) => applyStep("ingest", event));

    $("#ingest-result-head").textContent =
      `Stored ${result.documents_written} chunks in ${result.table}`;
    $("#ingest-result-sub").textContent =
      `${chosenFile.name} is now the indexed document. Switch to the Search tab to ask it something.`;
    $("#ingest-result").hidden = false;
    await showSample();
  } catch (error) {
    showError("ingest", error);
  } finally {
    button.disabled = false;
    button.textContent = "Ingest";
    await refreshStatus();
    loadFacets();
  }
}

// The one place this UI leaves the Python API: a plain SELECT against the table the
// ingest just wrote, so you can see the chunks really are ordinary Db2 rows.
async function showSample() {
  let data;
  try {
    const response = await fetch("/api/sample?limit=5", { cache: "no-store" });
    if (!response.ok) return;
    data = await response.json();
  } catch (_) { return; }

  $("#sample-total").textContent =
    `Showing ${data.rows.length} of ${data.total} rows in ${data.table}.`;
  $("#sample-sql").innerHTML = sqlBlock(data.sql);
  $("#sample-note").innerHTML = noteHtml({
    args: [
      ["JSON_VALUE", "reads the BSON in META — Docling's metadata stays queryable in SQL"],
      ["VECTOR_SERIALIZE", "renders EMBEDDING, a native `VECTOR(384, FLOAT32)`, not a blob"],
      ["ID", "the chunk's content hash — same PDF in, same rows out"],
    ],
  });

  $("#sample-rows").innerHTML =
    `<thead><tr>${data.columns.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead>` +
    `<tbody>${data.rows.map((row) => `<tr>${row.map((cell, i) =>
      `<td class="col-${esc(data.columns[i].toLowerCase())}">${esc(cell)}</td>`).join("")}</tr>`).join("")}</tbody>`;
  $("#sample-card").hidden = false;
}

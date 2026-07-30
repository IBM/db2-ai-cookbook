import re
from html import escape

import ibm_db
import marko
import uvicorn
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc.labels import DocItemLabel
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

converter = DocumentConverter(format_options={
    InputFormat.PDF: PdfFormatOption(pipeline_options=PdfPipelineOptions(do_ocr=False))
})
conn = ibm_db.connect("SAMPLE", "", "")
app = FastAPI()

CONTENT_LABELS = set(DocItemLabel) - {DocItemLabel.PAGE_HEADER, DocItemLabel.PAGE_FOOTER, DocItemLabel.PICTURE}

CHROME = {"subscribe", "sign in", "sign up", "log in", "log out", "sign out",
          "share", "comment", "comments", "reply", "save", "like", "bookmark",
          "follow", "following", "continue", "more"}


def clean_chrome(md: str) -> str:
    keep = []
    for line in md.splitlines():
        s, low = line.strip(), line.strip().lower()
        if (low in CHROME or s.isdigit() or s.startswith("©")
                or s.endswith("'s avatar") or "your email" in low):
            continue
        keep.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(keep))


class SaveRequest(BaseModel):
    url: str


STYLE = "<style>body{max-width:780px;margin:2em auto;font-family:system-ui,sans-serif;line-height:1.6;padding:0 1em}pre{background:#f5f5f5;padding:1em;overflow-x:auto;border-radius:4px}</style>"

INDEX_PAGE = STYLE + """<!doctype html>
<title>My Second Brain</title>
<h1>My Second Brain</h1>
<input id="u" size="60" placeholder="https://...">
<button onclick="save()">Save</button>
<p id="s"></p>
<h2>Saved documents</h2>
<ul>__ITEMS__</ul>
<script>
async function save() {
  const url = document.getElementById('u').value;
  const s = document.getElementById('s');
  s.textContent = 'Saving...';
  const r = await fetch('/save', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({url})
  });
  const j = await r.json();
  if (!r.ok) s.textContent = 'Error: ' + JSON.stringify(j);
  else if (j.duplicate) s.textContent = 'Already saved as id ' + j.id;
  else location.reload();
}
</script>
"""


@app.get("/", response_class=HTMLResponse)
def index():
    stmt = ibm_db.exec_immediate(conn, "SELECT ID, COALESCE(TITLE, URL), SAVED_AT FROM DOCUMENTS ORDER BY ID DESC")
    items = ""
    while (row := ibm_db.fetch_tuple(stmt)):
        items += f'<li><a href="/documents/{row[0]}">{escape(row[1])}</a> <small>({row[2]})</small></li>'
    return INDEX_PAGE.replace("__ITEMS__", items or "<li><em>nothing saved yet</em></li>")


@app.post("/save")
def save(req: SaveRequest):
    check = ibm_db.prepare(conn, "SELECT ID FROM DOCUMENTS WHERE URL = ?")
    ibm_db.execute(check, (req.url,))
    existing = ibm_db.fetch_tuple(check)
    if existing:
        return {"id": int(existing[0]), "duplicate": True}
    doc = converter.convert(req.url).document
    title = next((t.text for t in reversed(doc.texts) if t.label == DocItemLabel.TITLE), None)
    md = clean_chrome(doc.export_to_markdown(labels=CONTENT_LABELS))
    stmt = ibm_db.prepare(conn, "INSERT INTO DOCUMENTS (URL, TITLE, CONTENT) VALUES (?, ?, ?)")
    ibm_db.execute(stmt, (req.url, title, md))
    row = ibm_db.fetch_tuple(ibm_db.exec_immediate(conn, "VALUES IDENTITY_VAL_LOCAL()"))
    return {"id": int(row[0]), "duplicate": False}


@app.get("/documents/{doc_id}", response_class=HTMLResponse)
def view_document(doc_id: int):
    stmt = ibm_db.prepare(conn, "SELECT URL, CONTENT FROM DOCUMENTS WHERE ID = ?")
    ibm_db.execute(stmt, (doc_id,))
    url, content = ibm_db.fetch_tuple(stmt)
    return f'{STYLE}<p><a href="/">&larr; home</a></p><p>Source: <a href="{escape(url)}">{escape(url)}</a></p>{marko.convert(content)}'


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)

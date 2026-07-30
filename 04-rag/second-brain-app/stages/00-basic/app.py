from datetime import datetime
from pathlib import Path

import uvicorn
from docling.document_converter import DocumentConverter
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

VAULT_DIR = Path.home() / "second-brain"
VAULT_DIR.mkdir(exist_ok=True)

converter = DocumentConverter()
app = FastAPI()


class SaveRequest(BaseModel):
    url: str


PAGE = """<!doctype html>
<title>second-brain-with-db2</title>
<h1>second-brain-with-db2</h1>
<input id="u" size="60" placeholder="https://...">
<button onclick="save()">Save</button>
<p id="s"></p>
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
  s.textContent = r.ok ? 'Saved: ' + j.file : 'Error: ' + JSON.stringify(j);
}
</script>
"""


@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE


@app.post("/save")
def save(req: SaveRequest):
    markdown = converter.convert(req.url).document.export_to_markdown()
    filename = datetime.now().strftime("%Y-%m-%d_%H%M%S") + ".md"
    path = VAULT_DIR / filename
    path.write_text(f"Source: {req.url}\n\n{markdown}", encoding="utf-8")
    return {"file": str(path)}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)

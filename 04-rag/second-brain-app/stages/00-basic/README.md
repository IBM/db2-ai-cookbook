# Stage 0: Basic save endpoint

The minimum viable second-brain-with-db2: one form, one POST endpoint, one markdown file per save.

```mermaid
flowchart LR
    URL[📎 URL] --> Save["FastAPI<br/>POST /save"]
    Save --> Docling[docling<br/>extract]
    Docling --> File[📄 ~/second-brain/<br/>YYYY-MM-DD_HHMMSS.md]
```

## What's in this stage

- `POST /save` accepts `{"url": "..."}`, calls `DocumentConverter().convert(url).document.export_to_markdown()`, and writes the result to `~/second-brain/YYYY-MM-DD_HHMMSS.md` with a `Source: <url>` line prepended.
- `GET /` serves a plain HTML page with one input, one button, and a status line. No JS framework, no build step.
- `DocumentConverter` is instantiated once at module load — model init is expensive, so reuse it across requests.

## Key concept

How docling fits in, in three method calls:

```python
converter.convert(url)             # fetch + parse → ConversionResult
         .document                 # structured DoclingDocument
         .export_to_markdown()     # flatten → markdown string
```

Everything else in `app.py` is plumbing around that one line.

## Run

From the project root (with `.venv` created):

```bash
./stages/00-basic/run.sh
```

Or from this directory: `./run.sh`. The script activates the shared venv, installs this stage's requirements, and launches the app.

Open http://127.0.0.1:8000.

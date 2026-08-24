"""Convert a PDF with Docling, embed the chunks, and store them in Db2.

    PYTHONPATH=src .venv/bin/python -m haystack_db2_rag.ingest data/M-Lean_Article.pdf

The pipeline is three components:  converter -> embedder -> writer

Importing this module is free: the pipeline is built inside build_pipeline(), so the
web UI (ui/api.py) can call ingest_pdf() without a CLI run happening on import.
"""

import sys

from docling.chunking import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from haystack import Pipeline
from haystack.components.embedders import OpenAIDocumentEmbedder
from haystack.components.writers import DocumentWriter
from haystack.utils import Secret
from haystack_integrations.components.converters.docling import (
    BaseMetaExtractor,
    DoclingConverter,
    ExportType,
)

from . import settings
from .store import open_store


class SimpleMeta(BaseMetaExtractor):
    """Keep a small, flat, filterable subset of what Docling knows about each chunk.

    Docling's full metadata contains "$ref" keys, and Db2 stores metadata as BSON,
    which forbids field names starting with "$". So we keep a small flat subset —
    every field here is one you can filter on (see metadata.py).
    """

    def extract_chunk_meta(self, chunk):
        doc_items = getattr(chunk.meta, "doc_items", [])
        pages = {prov.page_no for item in doc_items for prov in getattr(item, "prov", [])}
        page_start = min(pages) if pages else 0
        headings = getattr(chunk.meta, "headings", None) or []
        origin = getattr(chunk.meta, "origin", None)
        return {
            "source": getattr(origin, "filename", "") if origin else "",
            # Filter this one with == or `in` — a list, not a range. See "Filtering on
            # numbers" in the README for why > and >= mislead.
            "page_number": page_start,
            "page_start": page_start,
            # 11 of this PDF's 70 chunks straddle a page break, so the end page is its own field.
            "page_end": max(pages) if pages else 0,
            "section": headings[0] if headings else "",
            "headings": " > ".join(headings),
            "has_table": any(str(getattr(item, "label", "")) == "table" for item in doc_items),
        }

    def extract_dl_doc_meta(self, dl_doc):
        return {}


def build_pipeline(store) -> Pipeline:
    """The three-component indexing pipeline:  converter -> embedder -> writer."""
    # HybridChunker splits on the document's own structure (headings, tables) and packs
    # each chunk up to a token budget, measured with the embedding model's tokenizer.
    # Built here, not at import: from_pretrained() reads the tokenizer off disk.
    chunker = HybridChunker(
        tokenizer=HuggingFaceTokenizer.from_pretrained(
            settings.EMBED_TOKENIZER, max_tokens=settings.EMBED_MAX_TOKENS
        )
    )

    pipeline = Pipeline()
    pipeline.add_component(
        "converter",
        DoclingConverter(
            export_type=ExportType.DOC_CHUNKS, chunker=chunker, meta_extractor=SimpleMeta()
        ),
    )
    pipeline.add_component(
        "embedder",
        OpenAIDocumentEmbedder(
            api_key=Secret.from_token(settings.API_KEY),
            model=settings.EMBED_MODEL,
            api_base_url=settings.EMBED_BASE_URL,
        ),
    )
    pipeline.add_component("writer", DocumentWriter(document_store=store))

    pipeline.connect("converter", "embedder")
    pipeline.connect("embedder", "writer")
    return pipeline


def ingest_pdf(pdf: str, recreate_table: bool = True) -> dict:
    """Run the pipeline over one PDF and report what was stored.

    recreate_table=True gives a clean table every run, so this is repeatable. The drop
    happens when the writer first connects, not here — a PDF that fails to convert
    therefore leaves the previous index untouched.
    """
    with open_store(recreate_table=recreate_table) as store:
        result = build_pipeline(store).run({"converter": {"sources": [pdf]}})
        return {
            "documents_written": result["writer"]["documents_written"],
            "table": settings.DB2_TABLE,
            "source": pdf,
        }


if __name__ == "__main__":
    pdf = sys.argv[1] if len(sys.argv) > 1 else "data/M-Lean_Article.pdf"
    print(f"Converting {pdf} (the first run downloads Docling's layout models)...")
    written = ingest_pdf(pdf)["documents_written"]
    print(f"Stored {written} chunks in {settings.DB2_TABLE}.")

"""Convert a PDF with Docling, embed the chunks, and store them in Db2.

    PYTHONPATH=src .venv/bin/python -m haystack_db2_rag.ingest data/M-Lean_Article.pdf

The pipeline is three components:  converter -> embedder -> writer
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
from .store import document_store

pdf = sys.argv[1] if len(sys.argv) > 1 else "data/M-Lean_Article.pdf"


class SimpleMeta(BaseMetaExtractor):
    """Keep one page number and the section headings for each chunk.

    Docling's full metadata contains "$ref" keys, and Db2 stores metadata as BSON,
    which forbids field names starting with "$". So we keep a small flat subset.
    """

    def extract_chunk_meta(self, chunk):
        pages = {
            prov.page_no
            for item in getattr(chunk.meta, "doc_items", [])
            for prov in getattr(item, "prov", [])
        }
        return {
            "page_number": min(pages) if pages else 0,
            "headings": " > ".join(getattr(chunk.meta, "headings", None) or []),
        }

    def extract_dl_doc_meta(self, dl_doc):
        return {}

# HybridChunker splits on the document's own structure (headings, tables) and packs
# each chunk up to a token budget, measured with the embedding model's tokenizer.
chunker = HybridChunker(
    tokenizer=HuggingFaceTokenizer.from_pretrained(
        settings.EMBED_TOKENIZER, max_tokens=settings.EMBED_MAX_TOKENS
    )
)

# recreate_table=True gives a clean table every run, so this script is repeatable.
store = document_store(recreate_table=True)

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

print(f"Converting {pdf} (the first run downloads Docling's layout models)...")
result = pipeline.run({"converter": {"sources": [pdf]}})

print(f"Stored {result['writer']['documents_written']} chunks in {settings.DB2_TABLE}.")

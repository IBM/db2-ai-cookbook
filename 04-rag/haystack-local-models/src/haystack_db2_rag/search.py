"""Answer a question using the documents stored in Db2.

    PYTHONPATH=src .venv/bin/python -m haystack_db2_rag.search "what is M-Lean?"

The flags filter on metadata in Db2 *before* the vector search, so the similarity
ranking only ever sees the rows that already match:

    ... .search "what are the results?" --page 4
    ... .search "what is in Table 1?" --tables-only
    ... .search "what are the phases?" --section "5. Proposed framework design" --top-k 5

Run metadata.py to see which values those fields take. The pipeline is four components:
    text_embedder -> retriever -> prompt_builder -> generator

Importing this module is free: the pipeline is built inside build_pipeline(), so the
web UI (ui/api.py) can call ask() without a CLI run happening on import.
"""

import argparse

from haystack import Pipeline
from haystack.components.builders import ChatPromptBuilder
from haystack.components.embedders import OpenAITextEmbedder
from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.dataclasses import ChatMessage
from haystack.utils import Secret
from haystack_integrations.components.retrievers.ibm_db import IBMDb2EmbeddingRetriever

from . import settings
from .chunks import body
from .store import open_store

PROMPT = """Answer the question using only the excerpts below. If they do not contain
the answer, say that the document does not cover it — do not use any other knowledge.

{% for doc in documents %}
{{ doc.content }}
{% endfor %}

Question: {{ question }}
Answer:"""


def build_filters(page=None, section=None, tables_only=False):
    """Turn the CLI flags (or the UI's form controls) into a retriever filter.

    Each flag is one condition; several flags are ANDed. This is the same dict shape the
    store takes in metadata.py — a retriever filter and a metadata query are one language.
    """
    conditions = []
    if page is not None:
        conditions.append({"field": "meta.page_number", "operator": "==", "value": page})
    if section:
        conditions.append({"field": "meta.section", "operator": "==", "value": section})
    if tables_only:
        conditions.append({"field": "meta.has_table", "operator": "==", "value": True})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"operator": "AND", "conditions": conditions}


def build_pipeline(store, top_k: int = 3) -> Pipeline:
    """The four-component answering pipeline:
    text_embedder -> retriever -> prompt_builder -> generator."""
    pipeline = Pipeline()
    pipeline.add_component(
        "text_embedder",
        OpenAITextEmbedder(
            api_key=Secret.from_token(settings.API_KEY),
            model=settings.EMBED_MODEL,
            api_base_url=settings.EMBED_BASE_URL,
            # bge models want this prefix on the question, but not on the documents.
            prefix="Represent this sentence for searching relevant passages: ",
        ),
    )
    pipeline.add_component(
        "retriever", IBMDb2EmbeddingRetriever(document_store=store, top_k=top_k)
    )
    pipeline.add_component(
        "prompt_builder", ChatPromptBuilder(template=[ChatMessage.from_user(PROMPT)])
    )
    pipeline.add_component(
        "generator",
        OpenAIChatGenerator(
            api_key=Secret.from_token(settings.API_KEY),
            model=settings.CHAT_MODEL,
            api_base_url=settings.CHAT_BASE_URL,
            # temperature 0 = greedy decoding: the same question gives the same answer,
            # and the "only use the excerpts" instruction is followed consistently.
            generation_kwargs={"temperature": 0},
        ),
    )

    pipeline.connect("text_embedder.embedding", "retriever.query_embedding")
    pipeline.connect("retriever.documents", "prompt_builder.documents")
    pipeline.connect("prompt_builder.prompt", "generator.messages")
    return pipeline


def ask(question, page=None, section=None, tables_only=False, top_k=3) -> dict:
    """Answer one question, and report the chunks the answer was grounded in."""
    filters = build_filters(page, section, tables_only)
    with open_store() as store:
        result = build_pipeline(store, top_k).run(
            {
                "text_embedder": {"text": question},
                "retriever": {"filters": filters} if filters else {},
                "prompt_builder": {"question": question},
            },
            include_outputs_from={"retriever"},
        )
    return {
        "question": question,
        "answer": result["generator"]["replies"][0].text,
        "documents": [
            {
                # COSINE distance, so lower is closer.
                "score": doc.score,
                "content": doc.content,
                "excerpt": " ".join(body(doc).split()),
                "page_number": doc.meta["page_number"],
                "page_end": doc.meta["page_end"],
                "section": doc.meta["section"],
                "headings": doc.meta["headings"],
                "has_table": doc.meta["has_table"],
                "source": doc.meta["source"],
            }
            for doc in result["retriever"]["documents"]
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question", nargs="?", default="What is M-Lean?")
    parser.add_argument("--page", type=int, help="only chunks that start on this page")
    parser.add_argument("--section", help="only chunks under this section heading")
    parser.add_argument("--tables-only", action="store_true", help="only chunks containing a table")
    parser.add_argument("--top-k", type=int, default=3, help="how many chunks to retrieve (default 3)")
    args = parser.parse_args()

    result = ask(args.question, args.page, args.section, args.tables_only, args.top_k)

    if not result["documents"]:
        print("\nNothing was retrieved. Either the table is empty (run ingest) or the search "
              "is failing — see Troubleshooting in the README.")

    print(f"\nQ: {result['question']}")
    print(f"\nA: {result['answer']}\n")
    print("Retrieved:")
    for doc in result["documents"]:
        print(f"  [{doc['score']:.3f}] p.{doc['page_number']} {doc['headings']}: {doc['excerpt'][:60]}...")


if __name__ == "__main__":
    main()

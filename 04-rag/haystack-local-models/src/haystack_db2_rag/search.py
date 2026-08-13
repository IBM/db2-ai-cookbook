"""Answer a question using the documents stored in Db2.

    PYTHONPATH=src .venv/bin/python -m haystack_db2_rag.search "what is M-Lean?"

The flags filter on metadata in Db2 *before* the vector search, so the similarity
ranking only ever sees the rows that already match:

    ... .search "what are the results?" --page 4
    ... .search "what is in Table 1?" --tables-only
    ... .search "what are the phases?" --section "5. Proposed framework design" --top-k 5

Run metadata.py to see which values those fields take. The pipeline is four components:
    text_embedder -> retriever -> prompt_builder -> generator
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
from .store import document_store

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("question", nargs="?", default="What is M-Lean?")
parser.add_argument("--page", type=int, help="only chunks that start on this page")
parser.add_argument("--section", help="only chunks under this section heading")
parser.add_argument("--tables-only", action="store_true", help="only chunks containing a table")
parser.add_argument("--top-k", type=int, default=3, help="how many chunks to retrieve (default 3)")
args = parser.parse_args()

question = args.question

# Each flag is one condition; several flags are ANDed. This is the same dict shape the
# store takes in metadata.py — a retriever filter and a metadata query are one language.
conditions = []
if args.page is not None:
    conditions.append({"field": "meta.page_number", "operator": "==", "value": args.page})
if args.section:
    conditions.append({"field": "meta.section", "operator": "==", "value": args.section})
if args.tables_only:
    conditions.append({"field": "meta.has_table", "operator": "==", "value": True})

if not conditions:
    filters = None
elif len(conditions) == 1:
    filters = conditions[0]
else:
    filters = {"operator": "AND", "conditions": conditions}

PROMPT = """Answer the question using only the excerpts below. If they do not contain
the answer, say that the document does not cover it — do not use any other knowledge.

{% for doc in documents %}
{{ doc.content }}
{% endfor %}

Question: {{ question }}
Answer:"""

store = document_store()

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
    "retriever", IBMDb2EmbeddingRetriever(document_store=store, top_k=args.top_k)
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

result = pipeline.run(
    {
        "text_embedder": {"text": question},
        "retriever": {"filters": filters} if filters else {},
        "prompt_builder": {"question": question},
    },
    include_outputs_from={"retriever"},
)

documents = result["retriever"]["documents"]
if not documents:
    print("\nNothing was retrieved. Either the table is empty (run ingest) or the search "
          "is failing — see Troubleshooting in the README.")

print(f"\nQ: {question}")
print(f"\nA: {result['generator']['replies'][0].text}\n")
print("Retrieved:")
for doc in documents:
    # Docling prepends the headings to each chunk's text, so the preview starts past them.
    excerpt = " ".join(doc.content.replace(doc.meta["headings"], "", 1).split())
    print(f"  [{doc.score:.3f}] p.{doc.meta['page_number']} {doc.meta['headings']}: {excerpt[:60]}...")

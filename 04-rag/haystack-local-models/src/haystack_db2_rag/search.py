"""Answer a question using the documents stored in Db2.

    PYTHONPATH=src .venv/bin/python -m haystack_db2_rag.search "what is M-Lean?"

Add a page number to filter on metadata before the search:

    PYTHONPATH=src .venv/bin/python -m haystack_db2_rag.search "what are the results?" 4

The pipeline is four components:
    text_embedder -> retriever -> prompt_builder -> generator
"""

import sys

from haystack import Pipeline
from haystack.components.builders import ChatPromptBuilder
from haystack.components.embedders import OpenAITextEmbedder
from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.dataclasses import ChatMessage
from haystack.utils import Secret
from haystack_integrations.components.retrievers.ibm_db import IBMDb2EmbeddingRetriever

from . import settings
from .store import document_store

question = sys.argv[1] if len(sys.argv) > 1 else "What is M-Lean?"
filters = (
    {"field": "meta.page_number", "operator": "==", "value": int(sys.argv[2])}
    if len(sys.argv) > 2
    else None
)

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
pipeline.add_component("retriever", IBMDb2EmbeddingRetriever(document_store=store, top_k=3))
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
    print(f"  [{doc.score:.3f}] p.{doc.meta['page_number']} {doc.meta['headings']}: {doc.content[:60]}...")

"""Query the Db2 table by metadata alone — no embeddings, no models, no question.

    PYTHONPATH=src .venv/bin/python -m haystack_db2_rag.metadata

search.py answers questions by vector distance. This module shows the other half of the
same table: the structural metadata Docling extracted, stored as BSON in the META column
and queried with ordinary SQL predicates. Neither llama.cpp server needs to be running.

The filters are plain dicts, the same ones the retriever accepts, so anything shown here
can be handed to search.py to narrow a vector search (see --section and --tables-only).
"""

from .chunks import body
from .store import document_store

store = document_store()


def preview(doc):
    """The chunk's first line of actual text, for a one-line-per-hit listing."""
    return body(doc).splitlines()[0]


def show(label, documents):
    """Print a filter's hit count, and where each matched chunk sits in the document."""
    print(f"\n{label} — {len(documents)} chunks")
    for doc in documents[:4]:
        print(f"  p.{doc.meta['page_start']:<3} {doc.meta['section'][:34]:34s} {preview(doc)[:44]}")
    if len(documents) > 4:
        print(f"  ... and {len(documents) - 4} more")


print(f"{store.count_documents()} chunks in {store.table_name}\n")

# 1. What is there to filter on? Types are inferred from the stored BSON.
print("Metadata fields:")
for field, info in sorted(store.get_metadata_fields_info().items()):
    print(f"  {field:16s} {info['type']}")

# 2. The values each field takes — this is what a faceted search UI would show.
sections = [s for s in store.get_metadata_field_unique_values("section") if s]
print(f"\n{len(sections)} sections, from '{sections[0]}' to '{sections[-1]}':")
for section in sections[:8]:
    print(f"  {section}")
print(f"  ... and {len(sections) - 8} more")

print("\nPages:", store.get_metadata_field_min_max("page_number"))
print("Source documents:", store.get_metadata_field_unique_values("source"))

# 3. A structured query with no vector involved: every chunk that contains a table.
#    Docling knew which elements were tables; that survived into the metadata.
show(
    "has_table == True",
    store.filter_documents({"field": "meta.has_table", "operator": "==", "value": True}),
)

# 4. Counting without fetching the rows — the work stays in Db2.
in_methods = {"field": "meta.section", "operator": "==", "value": "5. Proposed framework design"}
print(f"\nChunks in '5. Proposed framework design': {store.count_documents_by_filter(in_methods)}")

# 5. A compound filter: AND / OR / NOT take a list of conditions.
show(
    "section == '5. Proposed framework design' AND has_table == True",
    store.filter_documents(
        {
            "operator": "AND",
            "conditions": [
                in_methods,
                {"field": "meta.has_table", "operator": "==", "value": True},
            ],
        }
    ),
)

# 6. A page range. Use `in` with an explicit list: metadata comparisons run as strings, so
#    >= 10 also matches "2".."9" — see "Filtering on numbers" in the README.
show(
    "page_number in [10..15]",
    store.filter_documents(
        {"field": "meta.page_number", "operator": "in", "value": [10, 11, 12, 13, 14, 15]}
    ),
)

print("\nThe same filter dicts narrow a vector search:")
print('  .venv/bin/python -m haystack_db2_rag.search "What is in Table 1?" --tables-only')

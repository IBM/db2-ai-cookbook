#!/usr/bin/env python3
"""Rebuild the `chunk_text` column of data/corpus.csv from the structured fields.

chunk_text is the single text representation both retrieval legs use — the Db2 Text
Search (BM25) index and TO_EMBEDDING (the vector). It is:

    "{title} by {authors}. Narrated by {narrators}. {description}"

(whitespace collapsed). Keeping it derived — rather than a hand-maintained column —
means the search corpus stays in sync with title/authors/narrators/description.
Run this after fetch_descriptions.py (which fills `description` with the full
summary), then re-run scripts/1_ingest.sql to re-index and re-embed.

Run:  python scripts/build_chunk_text.py
"""
import csv
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(REPO, "data", "corpus.csv")


def chunk_text(row):
    parts = [f"{row['title']} by {row['authors']}."]
    if row.get("narrators", "").strip():
        parts.append(f"Narrated by {row['narrators']}.")
    parts.append(row.get("description", "").strip())
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def main():
    rows = list(csv.DictReader(open(CORPUS, newline="")))
    fields = list(rows[0].keys())
    changed = 0
    lens = []
    for r in rows:
        new = chunk_text(r)
        if new != r.get("chunk_text", ""):
            changed += 1
        r["chunk_text"] = new
        lens.append(len(new))
    with open(CORPUS, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(rows)

    lens.sort()
    over512 = sum(1 for L in lens if L / 4 > 512)   # ~4 chars/token vs bge-small's 512-token ctx
    print(f"chunk_text rebuilt for {len(rows)} books ({changed} changed)")
    print(f"  length chars: min={lens[0]} median={lens[len(lens)//2]} max={lens[-1]}")
    print(f"  ~{over512} books exceed bge-small's 512-token context (embedding truncates the tail)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

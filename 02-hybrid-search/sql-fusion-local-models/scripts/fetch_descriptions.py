#!/usr/bin/env python3
"""Replace each book's short blurb with its FULL description, for display.

The corpus shipped Audnexus's short `description` field (~200 chars, truncated with
"..."). Audnexus also has a `summary` field with the full text (~1500-2100 chars),
just HTML-formatted. This fetches the summary, strips the HTML to clean text, and
updates the `description` column in data/corpus.csv AND Db2.

IMPORTANT: it does NOT touch `chunk_text` (the text-search + embedding source), so
retrieval and eval are unchanged — only what the UI displays gets richer.

Idempotent-ish: skips a book whose description already looks full (> MINLEN chars).

Run:  DB2_HOST=local PYTHONPATH=src python scripts/fetch_descriptions.py
"""
import csv
import html
import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from hybrid_search import core as h
import ibm_db

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(REPO, "data", "corpus.csv")
REGION = os.environ.get("AUDNEX_REGION", "ca")
MINLEN = 350          # a description already longer than this is treated as "full"
MAXLEN = 4000         # cap (matches core.book_meta's SUBSTR)
UA = {"User-Agent": "db2-hybrid-search/1.0"}


def clean(htmltext):
    """HTML summary -> readable plain text."""
    t = re.sub(r"<\s*(br|/p|/li)\s*/?>", " ", htmltext, flags=re.I)  # breaks -> space
    t = re.sub(r"<[^>]+>", "", t)                                    # drop remaining tags
    t = html.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:MAXLEN]


def audnex_summary(asin):
    try:
        req = urllib.request.Request(f"https://api.audnex.us/books/{asin}?region={REGION}", headers=UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            return (json.load(r).get("summary") or "").strip()
    except Exception:
        return ""


def main():
    rows = list(csv.DictReader(open(CORPUS, newline="")))
    fields = list(rows[0].keys())
    conn = h.connect()

    updated, skipped, missing = 0, 0, []
    for r in rows:
        if len(r.get("description", "")) > MINLEN:
            skipped += 1
            continue
        summ = audnex_summary(r["asin"].strip()) if r["asin"].strip() else ""
        full = clean(summ) if summ else ""
        if not full or len(full) <= len(r.get("description", "")):
            missing.append((r["id"], r["title"][:34]))
            continue
        r["description"] = full
        st = ibm_db.prepare(conn, "UPDATE MYSCHEMA.CHUNKS SET description = ? WHERE chunk_id = ?")
        ibm_db.bind_param(st, 1, full)
        ibm_db.bind_param(st, 2, int(r["id"]))
        ibm_db.execute(st)
        updated += 1
        print(f"  id{r['id']:>3} {len(full):>4} chars  {r['title'][:44]}")
        time.sleep(0.05)
    ibm_db.commit(conn)

    with open(CORPUS, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(rows)

    print(f"\ndescriptions: {updated} updated, {skipped} already full, {len(missing)} unavailable")
    for i, t in missing:
        print(f"  no summary: id{i} {t}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
build_eval_set.py — freeze the gold passages for the FEATURED eval queries into
eval_set.json, so the "Golden eval set" page in the UI can show, for each demo
question, the exact Db2-docs passage(s) that search is expected to return —
fully offline, no Db2 needed at view time.

Run it via ui/build_eval_set.sh (as the Db2 instance owner, local connection).
Reads queries.json and writes eval_set.json, both in this script's directory.
"""

import json
import os
import ibm_db
from hybrid_search import core as h


def chunk_text(conn, cid):
    """Full chunk text for one chunk_id (CAST to VARCHAR so ibm_db hands back a
    plain string rather than a CLOB locator; chunks are well under 8000 chars)."""
    sql = f"SELECT CAST(SUBSTR(chunk_text, 1, 8000) AS VARCHAR(8000)) FROM {h.T} WHERE chunk_id = ?"
    stmt = ibm_db.prepare(conn, sql)
    ibm_db.bind_param(stmt, 1, cid)
    ibm_db.execute(stmt)
    row = ibm_db.fetch_tuple(stmt)
    return (row[0] if row else "") or ""


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "queries.json")) as f:
        deck = json.load(f)
    featured = [q for q in deck if q.get("featured")]

    conn = h.connect()
    out = []
    for q in featured:
        gold = [{"chunk_id": cid, "text": chunk_text(conn, cid)}
                for cid in q["gold_chunk_ids"]]
        out.append({"id": q["id"], "query": q["query"],
                    "query_type": q["query_type"],
                    "note": q.get("note", ""), "gold": gold})
    ibm_db.close(conn)

    with open(os.path.join(here, "eval_set.json"), "w") as f:
        json.dump({"queries": out}, f, indent=2)
    print(f"wrote eval_set.json — {len(out)} featured queries, "
          f"{sum(len(q['gold']) for q in out)} gold passages")


if __name__ == "__main__":
    main()

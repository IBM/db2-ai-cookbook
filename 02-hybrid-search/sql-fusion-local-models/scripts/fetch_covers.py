#!/usr/bin/env python3
"""Fetch a cover thumbnail for every book in data/corpus.csv.

For each ASIN: ask Audnexus (region ca) for the cover image URL, download a small
~160px thumbnail (Amazon media URLs take a ._SX160_ size modifier, ~7 KB vs ~190 KB
full-size) into ui/static/covers/<asin>.jpg, and record a relative path in a new
`cover_url` column of data/corpus.csv (so 1_ingest.sql stores it in Db2).

Idempotent: skips a cover that's already downloaded. Stdlib only, no pip deps.

Run:  python scripts/fetch_covers.py
"""
import csv
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
CORPUS = os.path.join(REPO, "data", "corpus.csv")
COVER_DIR = os.path.join(REPO, "ui", "static", "covers")
REGION = os.environ.get("AUDNEX_REGION", "ca")
UA = {"User-Agent": "db2-hybrid-search/1.0 (cover fetch)"}


def audnex_image(asin):
    """The cover image URL Audnexus has for this ASIN, or None."""
    url = f"https://api.audnex.us/books/{asin}?region={REGION}"
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r).get("image") or None
    except Exception:
        return None


def thumb_url(img):
    """Amazon media URLs accept a size modifier: X.jpg -> X._SX160_.jpg (small)."""
    return img[:-4] + "._SX160_.jpg" if img.lower().endswith(".jpg") else img


def download(url, dest):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    if len(data) < 500:                      # too small to be a real cover
        raise ValueError("suspiciously small image")
    with open(dest, "wb") as f:
        f.write(data)
    return len(data)


def main():
    os.makedirs(COVER_DIR, exist_ok=True)
    rows = list(csv.DictReader(open(CORPUS, newline="")))
    fields = list(rows[0].keys())
    if "cover_url" not in fields:
        fields.append("cover_url")            # new column, appended after chunk_text

    have, fetched, missing = 0, 0, []
    for r in rows:
        asin = r["asin"].strip()
        rel = f"covers/{asin}.jpg"
        dest = os.path.join(REPO, "ui", "static", rel)
        if asin and os.path.exists(dest):     # idempotent: already downloaded
            r["cover_url"] = rel; have += 1; continue
        img = audnex_image(asin) if asin else None
        if not img:
            r["cover_url"] = ""; missing.append((r["id"], asin, r["title"][:32])); continue
        try:
            kb = download(thumb_url(img), dest) // 1024
            r["cover_url"] = rel; fetched += 1
            print(f"  id{r['id']:>3} {asin:13} {kb:>3} KB  {r['title'][:40]}")
        except Exception as e:
            r["cover_url"] = ""; missing.append((r["id"], asin, f"{r['title'][:24]} ({e})"))
        time.sleep(0.05)                      # be polite to Audnexus

    with open(CORPUS, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(rows)

    print(f"\ncovers: {have} already present, {fetched} fetched, {len(missing)} missing "
          f"({have + fetched}/{len(rows)} total)")
    if missing:
        print("MISSING (cover_url left empty — the UI will show a placeholder):")
        for i, a, t in missing:
            print(f"  id{i} {a} {t}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

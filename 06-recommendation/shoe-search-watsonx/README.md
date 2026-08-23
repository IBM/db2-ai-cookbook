# Finding a similar product in another store's inventory

> **Last checked 2026-08-16** — verified against `SAMPLE`: the 500 pre-computed vectors import
> into a `VECTOR(1024,FLOAT32)` column with 0 rejects, the cross-store `VECTOR_DISTANCE` query
> returns ranked matches, and a live watsonx.ai embedding call comes back at 1024 dimensions.
> The cells were exercised individually rather than as one top-to-bottom run.  
> Checked on: Db2 12.1.5.0 · RHEL 10 · Python 3.12.

[← Recommendation](../README.md) · [← Db2 AI Cookbook](../../README.md)

> You found the running shoe you want at the Ottawa store. Is there anything close to it in
> Toronto? Embed each shoe as a row, store the vectors in Db2, and let `VECTOR_DISTANCE` answer —
> with the store location as an ordinary SQL filter.

![Db2](https://img.shields.io/badge/store-Db2%2012.1.2%2B%20VECTOR-054ada)
![watsonx.ai](https://img.shields.io/badge/embeddings-watsonx.ai%20cloud-0f62fe)
![Python](https://img.shields.io/badge/Python-3.12-blue)

This is item-to-item recommendation, and the shape of the query is what makes it interesting: the
*similarity* comes from the vector, and the *availability* comes from a `WHERE` clause on the
inventory columns. One statement, one system.

## Quick start

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then fill in the Db2 and watsonx.ai values
```

Then open `2-shoe-search.ipynb` and select `.venv/bin/python` as the kernel — in VS Code, through
the kernel picker. To use JupyterLab instead, `pip install jupyterlab` first; it is not in
`requirements.txt`, which pins only what the notebook itself imports.

`shoes-vectors.csv` ships with the recipe, so the search notebook runs without spending
watsonx.ai calls. Run `1-shoes-data-gen.ipynb` only if you want to regenerate the catalogue and
its embeddings from scratch.

## Expected output

The notebook tells one story end to end:

1. **Search Ottawa** for a men's size 12 running shoe → a shortlist, ranked
2. **Pick one** — the chosen shoe is in stock in Ottawa
3. **Search Toronto** for shoes similar to it → the nearest matches available at that location
4. **Compare** the Toronto candidates against the original side by side

Then *Looking under the hood* re-runs the same steps showing the mechanics: the table before it
had a `VECTOR` column, the `ALTER` that adds one, which shoe attributes were concatenated into
the text that got embedded, and the `VECTOR_DISTANCE` query that does the matching.

## Concepts

### The row becomes a sentence

A shoe is a set of columns — brand, type, material, colour, weather resistance, arch support,
size, price, store. The notebook joins **five** of them into one labelled string and embeds that,
which is what makes two shoes "similar":

```
TYPE: Running [SEP] MATERIAL: Knit [SEP] COLOR: Black [SEP] WEATHER_RESISTANCE: Waterproof [SEP] ARCH_SUPPORT: Flat
                              │
                              └──▶  watsonx.ai embedding  ──▶  VECTOR(1024,FLOAT32) column
```

Choosing which attributes go into that string *is* the recommendation logic, and the omissions
carry as much weight as the inclusions. `BRAND` is left out, so a Loopic can come back as the
nearest match to a Zentrax — similarity is about the shoe, not the label. `SIZE` and `CITY` are
left out because they are hard filters, not similarity dimensions; they belong in the `WHERE`
clause.

### Similarity and availability are different questions

```sql
… VECTOR_DISTANCE(<chosen shoe's vector>, EMBEDDING, EUCLIDEAN) AS DISTANCE
FROM SQ_SHOES
WHERE CITY = 'Toronto' AND SIZE = 12 AND CLASS = 'Men'
ORDER BY DISTANCE
```

"Like this one" is a vector operation. "In Toronto, size 12, in stock" is a relational one. Db2
evaluates both in the same statement — the part that would otherwise need a vector store, an
application join, and a second round trip.

### The data is synthetic

`1-shoes-data-gen.ipynb` builds the catalogue with [Faker](https://faker.readthedocs.io/) —
brands, models and inventory are invented, and no real product data or retailer imagery is
included.

- `shoes.csv` — the shoe catalogue with its store inventory (500 shoes)
- `shoes-vectors.csv` — one 1024-dimension embedding per shoe, pre-computed
- `utils.py` — helpers the search notebook imports

> **Product photos are not included.** The notebook calls
> `utils.display_sku_images(...)`, which looks for `images/<SKU>.jpeg`. Without that folder the
> grid renders "Image not found" placeholders and everything else works normally. To see
> pictures, drop your own `<SKU>.jpeg` files into `images/`.

---

## Appendix

### Credentials

`.env` holds two sets of values: the Db2 connection details and your watsonx.ai API key and
project ID. It is gitignored, and `.env.example` shows the shape.

Db2 is reached through the `%sql` magic provided by
[`db2.ipynb`](https://github.com/IBM/db2-jupyter), which the notebook downloads on first run. That
magic's `CONNECT CREDENTIALS` path builds a TCP/IP connection string and **has no local-catalog
branch** — so it needs `database`, `hostname`, `port`, `uid` and `pwd` even when Db2 is on the same
machine and you are the instance owner. Those five keys are lowercase in `.env`, because
`dotenv_values()` passes them through verbatim.

> **One thing to watch.** The magic caches these credentials to `db2connect.pickle` next to the
> notebook, password in plaintext. The cookbook's root `.gitignore` covers `*.pickle` for exactly
> that reason — an ignore rule naming only `.env` lets the copy through.

### Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `%sql` is not defined | `db2.ipynb` did not download | Fetch it from [IBM/db2-jupyter](https://github.com/IBM/db2-jupyter) into this folder |
| `ModuleNotFoundError: nbformat` on `%run db2.ipynb` | IPython cannot run a notebook without it | `pip install -r requirements.txt` — it is pinned there |
| `Connect requires a HOST, PORT, and DATABASE name` | `.env` has the watsonx keys but not the five lowercase Db2 ones | Add them; see *Credentials* above |
| `SQL1013N ... could not be found` from a `! db2` cell | The notebook's hardcoded database name is not cataloged here | `db2 list db directory`, then edit the `connect to` in those cells |
| `WATSONX_APIKEY` errors | `.env` missing or not loaded | `cp .env.example .env`, fill it in, restart the kernel |
| `ModuleNotFoundError: utils` | Kernel started outside this folder | Open the notebook from the recipe directory |
| Every result has the same distance | The chosen shoe's vector was compared against itself, or the embeddings never loaded | Check the table has as many rows as `shoes.csv` and that the vectors are non-zero |
| `CREATE TABLE` fails on the `VECTOR` column | Db2 is older than 12.1.2 | `db2level` to confirm; there is no workaround |

### Files

```
2-shoe-search.ipynb      the recipe — search, pick, cross-store match, then the mechanics
1-shoes-data-gen.ipynb   regenerate the synthetic catalogue and its embeddings
utils.py                 helpers imported by the search notebook
shoes.csv                the shoe catalogue and inventory
shoes-vectors.csv        pre-computed embeddings, one per shoe
requirements.txt         pinned
.env.example             Db2 and watsonx.ai credentials template
```

# A storefront where "similar products" is a SQL query

> **Last checked 2026-08-16** — verified from a clean database: with both tables dropped,
> `./setup.sh` loads them (500 + 24 rows, 0 rejected) and completes in one run, `./run.sh` brings
> both services up, and `/api/products/ZEN-5999/recommendations` returns 8 walking shoes across
> five brands for a walking shoe.  
> Checked on: Db2 12.1.5.0 · RHEL 10 · Python 3.12 · Node 22.

[← Recommendation](../README.md) · [← Db2 AI Cookbook](../../README.md)

> Click a shoe, and a "similar products" row appears underneath it. That row is a single
> `VECTOR_DISTANCE` query against Db2 — no vector store, no model call, no service in between.

![Db2](https://img.shields.io/badge/store-Db2%2012.1.2%2B%20VECTOR-054ada)
![Flask](https://img.shields.io/badge/backend-Flask%20%2B%20ibm__db-000000)
![React](https://img.shields.io/badge/frontend-React%2019%20%2B%20Vite-61dafb)

[shoe-search-watsonx](../shoe-search-watsonx/) shows the same idea in a notebook. This recipe puts
a browser in front of it, which changes what you can see: the recommendation has to come back
inside a page render, from a real HTTP request, against the same 500 rows. `shoes-vectors.csv` here
is byte-identical to the notebook's — the data is the same, only the front end is new.

## Quick start

Db2 12.1.2+ must already be running with a `SAMPLE` database. Everything else:

```bash
sudo dnf install -y python3.12 nodejs      # RHEL 10 ships Node 22; on RHEL 9 see SETUP.md §2.3
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then, from this directory:

```bash
./setup.sh                   # creates backend/.env from the template, then stops
$EDITOR backend/.env         # fill in DB_PASSWORD
./setup.sh                   # loads the tables, builds both environments
./run.sh                     # starts both services, prints the URL
```

Open the URL `run.sh` prints. Only **port 5173** needs to be reachable — Vite proxies the API, so
there is no second port to forward or open.

`./setup.sh` is idempotent: it loads `S1.SQ_SHOES`/`S1.SHOE_COLOR_SIZES` from the CSVs, builds the
backend venv, and runs `npm install`, skipping whatever is already in place. `--force-db` reloads
the data. `./run.sh --status` shows what is running and `./run.sh --stop` stops both; logs land in
`/tmp/recnodejs-{backend,frontend}.log`.

Doing it by hand instead, or starting from a bare VM with no Db2? [SETUP.md](SETUP.md) has the
long form.

## Expected output

A product grid. Click any shoe and its detail page shows price, colours and sizes, then a
**similar products** carousel — that carousel is the vector search. The UI also exposes the SQL
behind it, so you can read the query that produced the row you are looking at.

From the command line, the same thing:

```bash
curl -s http://localhost:5000/api/products/ZEN-5999/recommendations
```

`ZEN-5999` is *Zentrax X Walking*. All eight results come back as walking shoes — from Loopic,
RunXpress, StrideOne and FootFlex, not just Zentrax. Brand was never part of the embedded text, so
it does not pull the results together; the shoe's character does.

## Concepts

### Two layers, and only one of them runs per request

The embeddings were computed once, offline, and loaded into Db2 as a column. Nothing in the
running app talks to watsonx.ai — there is no API key in `backend/.env`, and no model is loaded.

```
INGESTION (once, offline)          PER REQUEST (every click)
shoe attributes → embedding   │    SKU → VECTOR_DISTANCE over S1.SQ_SHOES → 8 rows
→ shoes-vectors.csv → Db2     │    one SQL statement, no model call
```

That split is what makes the recommendation cheap enough to sit in a page render. The expensive,
slow, GPU-shaped work happened before the app ever started.

### The similarity is a subquery

The whole recommendation engine is this, in [backend/app/routes/products.py](backend/app/routes/products.py):

```sql
SELECT sku, PRODUCT_NAME, BRAND, PRICE, RATING, COLOR,
       vector_distance(
           (SELECT embedding FROM s1.sq_shoes WHERE sku = ?),
           embedding,
           euclidean) AS distance
FROM s1.sq_shoes
WHERE sku <> ?
ORDER BY distance ASC
FETCH FIRST 8 ROWS ONLY
```

The chosen shoe's vector is fetched inline by its primary key, compared against every other row,
and the result is ordered by distance. `WHERE sku <> ?` is doing real work — without it the shoe
always recommends itself first at distance 0.

### One origin, one port

The components call the API with relative paths — `axios.get("/api/products")` — and Vite proxies
`/api` through to Flask ([vite.config.ts](frontend/vite.config.ts)):

```
browser ──HTTP:5173──> Vite ──proxy /api──> Flask ──ibm_db:50000──> Db2 SAMPLE
                        └── serves the React app
```

The backend host appears nowhere in the frontend source, so the browser only ever talks to the
origin that served the page. **5173 is the only port to forward or open**, and the app behaves
identically from the server, from another machine, or through a tunnel.

This is worth doing deliberately. The obvious alternative — calling `http://<host>:5000` directly
from React — bakes a host into the bundle that has to be reachable *from the browser* rather than
from the server. That mismatch is the classic way a demo like this fails: the page loads fine and
the product grid is simply empty, because the fetch failed and the component rendered an empty
list.

### The data

- `shoes-vectors.csv` — 500 shoes, each with a 1024-dimension embedding
- `shoe_color_sizes.csv` — 24 colour/size variants, so a product page has something to render
- `dbsetup.sql` — creates `S1.SQ_SHOES` and `S1.SHOE_COLOR_SIZES` and imports both

Synthetic throughout: the brands, models and inventory are invented, and the shoe photographs in
`frontend/src/assets/` are stand-ins mapped by colour, not real product imagery.

---

## Appendix

### Setting up on a fresh VM

[SETUP.md](SETUP.md) is a from-scratch recreation guide — Db2, Python, `uv` and Node prerequisites,
data load, and the API host step — written for a machine with nothing installed. Start there if
the prerequisites above are not already in place.

### Reaching the app

Nothing to configure — the Vite proxy means any address that reaches port 5173 works:

| How you browse the app | Open |
|---|---|
| Browser on the server itself | `http://localhost:5173/` |
| Browser on another machine | `http://<server-ip>:5173/` — from `hostname -I` |
| VS Code / SSH port-forward | forward **5173 only**, then `http://localhost:5173/` |

If the backend runs on a non-default port, set `BACKEND_PORT` for both the run scripts and Vite —
[vite.config.ts](frontend/vite.config.ts) reads it when building the proxy target:

```bash
BACKEND_PORT=5001 ./run.sh
```

### Credentials

`backend/.env` holds the five `DB_*` values and nothing else — this recipe needs no watsonx.ai key,
because it never generates an embedding. It is gitignored; `.env.example` shows the shape.

### Endpoints

| Endpoint | Returns |
|---|---|
| `GET /api/products` | First 3 shoes with colour/size variants |
| `GET /api/products/<sku>` | A single product |
| `GET /api/products/<sku>/recommendations` | Top 8 nearest by `VECTOR_DISTANCE(..., euclidean)` |
| `GET /api/query/vector-search` | The SQL text above, for display in the UI |

### Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Page loads, no products, failed XHR in the console | Backend not running, or Vite started before the proxy config was in place | `./run.sh --status`; then `./run.sh --stop && ./run.sh` so Vite reloads `vite.config.ts` |
| Only 5173 forwarded and it still works | Expected — the proxy means the browser never contacts port 5000 | Nothing to do |
| `{"error": "DB connection failed"}` | Wrong credentials or port in `backend/.env` | Check `DB_PORT` against `db2 get dbm cfg \| grep -i svcename`; the real error prints on backend stdout |
| `SQL0204N` on the `DROP TABLE` lines | Tables do not exist yet | Expected on first run — `db2 -tvf` continues |
| `IMPORT` cannot find the file | `db2 -tvf` run from the wrong directory | `cd` to this folder first; the paths in `dbsetup.sql` are relative |
| `SQL0104N` on `VECTOR(1024, FLOAT32)` | Db2 older than 12.1.2 | `db2level` to confirm; there is no workaround |
| `npm install` peer-dependency errors | `react-material-ui-carousel` against React 19 | `npm install --force` |
| `db2: command not found` inside a script | `db2profile` not sourced | `export DB2_PROFILE=/path/to/db2profile` before running |
| `unbound variable` sourcing `db2profile` | `db2profile` references AIX-only vars under `set -u`, and *unsets* the empty ones as it goes — so binding them once only protects the first `source` | The scripts route every source through `source_db2profile()`, which re-binds first; do the same if scripting by hand |

### Files

```
setup.sh                 set up DB + backend + frontend, start nothing
run.sh                   start what is not running, print the URL
setup_and_run.sh         one-shot; also holds the shared helper functions
dbsetup.sql              create both tables and import the CSVs
shoes-vectors.csv        500 shoes with 1024-dim embeddings
shoe_color_sizes.csv     colour/size variants
backend/                 Flask + ibm_db, port 5000
                         requirements.txt  pinned
                         .env.example      Db2 connection template
                         app/routes/products.py  the four endpoints, incl. the vector query
frontend/                React 19 + TypeScript + Vite + MUI, port 5173
                         vite.config.ts    the /api proxy to Flask
SETUP.md                 from-scratch guide for a fresh VM
```

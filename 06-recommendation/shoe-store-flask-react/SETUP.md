# Setting up `shoe-store-flask-react` on a new VM

This is a complete, from-scratch recreation guide for this demo on a **fresh Linux VM**. It assumes nothing is installed except a base OS and a shell.

If you are Claude Code reading this on the target VM: work through the sections in order. Every step has a verification command — run it before moving on.

---

## 0. What this project is

A shoe-product recommendation demo backed by **Db2 vector search**.

| Piece | Stack | Port |
|---|---|---|
| `backend/` | Python 3.12 + Flask + `ibm_db` | 5000 |
| `frontend/` | React 19 + TypeScript + Vite + MUI | 5173 |
| Data | Db2 `SAMPLE` database, schema `S1` | 50000 |

Recommendations come from `VECTOR_DISTANCE(...)` over a `VECTOR(1024, FLOAT32)` embedding column in `S1.SQ_SHOES` — so the Db2 build on the new VM **must** support the `VECTOR` datatype.

### Data flow

```
browser  ──HTTP:5173──>  Vite dev server  ──proxy /api──>  Flask  ──ibm_db:50000──>  Db2 SAMPLE
                          serves the React app                                        S1.SQ_SHOES (500 rows, 1024-dim vectors)
                                                                                      S1.SHOE_COLOR_SIZES (24 rows)
```

The React components call the API with **relative paths**, and Vite proxies `/api` to Flask. The backend host is therefore absent from the frontend source, and **5173 is the only port that has to be reachable from the browser**.

---

## 1. Reference environment

The setup below was verified on this configuration. Newer patch levels are fine; the constraints that actually matter are called out.

| Component | Verified version | Constraint |
|---|---|---|
| OS | RHEL 9.6 (Plow), x86_64 · also RHEL 10.0 | Any RHEL 9.x / 10.x or compatible; other distros need the equivalent packages |
| Db2 | 12.1.5.0 | **Must support the `VECTOR` datatype** (Db2 12.1.2+) |
| Db2 instance | `db2inst1`, SVCENAME `50000` | Any instance/port — record it for `.env` |
| Python | 3.12.13 | 3.12.x — `ibm_db` wheels are built per minor version |
| uv | 0.7.19 · also 0.12.0 | Any recent version (or substitute plain `venv` + `pip`) |
| Node.js | v20.20.1 · also v22.23.1 | 20.x or 22.x LTS (18.x also works) |
| npm | 10.8.2 · also 10.9.8 | Ships with Node |

---

## 2. Prerequisites — install on the new VM

### 2.1 Db2 with vector support

Db2 must already be installed with an instance running and a `SAMPLE` database. If the VM has no Db2, install Db2 12.1.2 or later first (server install is out of scope here — use the standard IBM installer), then:

```bash
source /home/db2inst1/sqllib/db2profile
db2start
db2sampl                     # creates the SAMPLE database, if it doesn't exist
```

Verify version and vector support:

```bash
source /home/db2inst1/sqllib/db2profile
db2level | grep "Informational tokens"        # expect DB2 v12.1.x, x >= 2
db2 connect to sample
db2 "CREATE TABLE VECCHECK (V VECTOR(4, FLOAT32))" && db2 "DROP TABLE VECCHECK"
```

If `CREATE TABLE ... VECTOR(...)` fails with SQL0104N, the Db2 level is too old — everything downstream will fail, so stop and upgrade.

Note the instance's port for later:

```bash
db2 get dbm cfg | grep -i svcename            # e.g. 50000
```

### 2.2 Python 3.12 and uv

```bash
sudo dnf install -y python3.12
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env      # or restart the shell so `uv` is on PATH
```

Verify:

```bash
python3.12 --version    # Python 3.12.x
uv --version
```

No separate Db2 client driver install is needed — the `ibm_db` wheel bundles its own `clidriver`.

### 2.3 Node.js

On RHEL 10 the distro package is new enough — no third-party repo needed:

```bash
sudo dnf install -y nodejs        # RHEL 10 AppStream ships Node 22
```

On RHEL 9, AppStream's Node is older, so use NodeSource:

```bash
curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
sudo dnf install -y nodejs
```

Verify:

```bash
node -v    # v20.x or v22.x
npm -v     # 10.x
```

---

## 3. Get the project

Clone the cookbook and change into this recipe:

```bash
git clone <cookbook-repo-url>
cd db2-ai-cookbook/06-recommendation/shoe-store-flask-react
```

Confirm the payload is intact — the two CSVs are the data source and must be present:

```bash
ls -la shoes-vectors.csv shoe_color_sizes.csv dbsetup.sql
wc -l shoes-vectors.csv          # 501 (header + 500 rows)
wc -l shoe_color_sizes.csv       # 24  (header + 24 rows; last line has no trailing newline)
```

The repo deliberately **excludes** `node_modules/`, `backend/.venv/`, `__pycache__/`, and `backend/.env`. All four are recreated by the steps below — `.env` is excluded because it holds a database password.

---

## 4. Load the data into Db2

`dbsetup.sql` creates the two tables and imports both CSVs. The `IMPORT` statements use **relative paths**, so you must run it from the project directory.

```bash
cd <cookbook>/06-recommendation/shoe-store-flask-react
source /home/db2inst1/sqllib/db2profile
db2 -tvf dbsetup.sql
```

What it does:

1. `CONNECT TO sample`
2. `DROP TABLE S1.SQ_SHOES` / `S1.SHOE_COLOR_SIZES` — **on a fresh database these two DROPs fail with SQL0204N (name not found). That is expected and harmless**; `db2 -tvf` continues to the next statement.
3. `CREATE TABLE S1.SQ_SHOES (... EMBEDDING VECTOR(1024, FLOAT32))` and `S1.SHOE_COLOR_SIZES`
4. `IMPORT` both CSVs

The `S1` schema is created implicitly by the `CREATE TABLE`. That requires `IMPLICIT_SCHEMA` authority on the database — `db2inst1` has it by default. If you run as another user and get SQL0551N, either grant it or pre-create the schema with `db2 "CREATE SCHEMA S1"`.

Verify — both counts must be non-zero, and the vector query must return rows:

```bash
db2 connect to sample
db2 "select count(*) from s1.sq_shoes"             # 500
db2 "select count(*) from s1.shoe_color_sizes"     # 24
db2 "select sku, vector_distance(embedding, (select embedding from s1.sq_shoes fetch first 1 row only), euclidean) as d from s1.sq_shoes order by d fetch first 3 rows only"
```

If the row counts are 0 but no error appeared, check the import summary lines in the `db2 -tvf` output for rejected rows — usually a CSV that got mangled in transit (line endings, truncation).

---

## 5. Backend (Flask, port 5000)

```bash
cd <cookbook>/06-recommendation/shoe-store-flask-react/backend
uv venv --python "$(which python3.12)"
source .venv/bin/activate
uv pip install -r requirements.txt
```

Dependencies (`requirements.txt`): `flask`, `python-dotenv`, `ibm_db`, `flask-cors`.

### Environment file

`backend/.env` is **not** in the export. Create it from the template and fill in the credentials for the Db2 instance on *this* VM:

```bash
cp .env.example .env
```

Then edit `.env` so it reads:

```
DB_NAME=SAMPLE
DB_HOST=localhost
DB_PORT=50000
DB_USER=db2inst1
DB_PASSWORD=<the db2inst1 password on this VM>
```

All five keys are read by [backend/config.py](backend/config.py) and assembled into an `ibm_db` DSN in [backend/app/db.py](backend/app/db.py). `DB_PORT` must match the `SVCENAME` you noted in step 2.1.

### Start it

```bash
cd <cookbook>/06-recommendation/shoe-store-flask-react/backend
source .venv/bin/activate
python run.py
```

Flask binds `0.0.0.0:5000` with `debug=True` ([backend/run.py](backend/run.py)).

Verify from another shell:

```bash
curl -s http://localhost:5000/api/products | head -c 300
```

Expect JSON with a `products` array of 3 items. If you get `{"error": "DB connection failed"}`, the credentials or port in `.env` are wrong — the underlying `ibm_db` error is printed on the backend's stdout.

---

## 6. Frontend (Vite, port 5173)

```bash
cd <cookbook>/06-recommendation/shoe-store-flask-react/frontend
npm install
```

If npm aborts on peer-dependency conflicts (React 19 against some of the carousel packages), use:

```bash
npm install --force
```

Start the dev server bound to all interfaces so it is reachable from outside the VM:

```bash
npm run dev -- --host
```

Vite prints a `Local:` URL and one `Network:` URL per interface.

---

## 7. Open the app

Nothing to configure. The React components call the API with relative paths and Vite proxies
`/api` to Flask ([frontend/vite.config.ts](frontend/vite.config.ts)), so the backend host is not
baked into the frontend source. Any address that reaches port 5173 works:

| How you access the app | Open |
|---|---|
| Browser on the VM itself | `http://localhost:5173/` |
| Browser on another machine, same network | `http://<vm-ip>:5173/` — from `hostname -I` |
| SSH / VS Code port-forward | forward **5173 only**, then `http://localhost:5173/` |

Port 5000 never needs to be forwarded or opened — the browser does not contact it. Flask still
binds `0.0.0.0:5000`, so you can curl it directly on the VM for debugging.

If you move the backend off port 5000, set `BACKEND_PORT` for both the run scripts and Vite; the
proxy target reads it:

```bash
BACKEND_PORT=5001 ./run.sh
```

### Firewall

If browsing from another machine and the page will not load at all:

```bash
sudo firewall-cmd --add-port=5173/tcp --permanent
sudo firewall-cmd --reload
```

---

## 8. Verify end to end

```bash
# backend reachable
curl -s http://localhost:5000/api/products | head -c 200

# recommendations (vector search) — use a SKU from the products response
curl -s http://localhost:5000/api/products/ZEN-5999/recommendations | head -c 300

# frontend serving
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:5173/
```

Then open the app in a browser using the URL from the table in section 7. A working app shows a product list; clicking a product shows its details plus a "similar products" row — that row is the vector-search result and is the real proof the whole chain works.

### API endpoints

| Endpoint | Returns |
|---|---|
| `GET /api/products` | First 3 shoes with color/size variants |
| `GET /api/products/<sku>` | A single product |
| `GET /api/products/<sku>/recommendations` | Top 8 nearest products via `VECTOR_DISTANCE(..., euclidean)` |
| `GET /api/query/vector-search` | The SQL text used for recommendations (shown in the UI) |

---

## 9. Helper scripts

The export includes three idempotent scripts that automate sections 4–6 once the prerequisites in section 2 are installed. They re-check what is already in place and skip it.

| Script | Use |
|---|---|
| `./setup.sh` | Set up DB + backend + frontend, start nothing. `--force-db` reloads the data. |
| `./run.sh` | Start whatever is not running, print the URL. `--status` / `--stop`. |
| `./setup_and_run.sh` | One-shot setup + start. `--skip-db` skips the SQL load. |

```bash
./setup.sh          # first run stops after copying .env.example → .env so you can add the password
$EDITOR backend/.env
./setup.sh          # finishes venv, deps, npm install, DB load
./run.sh            # starts both services, prints the URL to open
```

Logs: `/tmp/recnodejs-{backend,frontend}.log`. PID files: `/tmp/recnodejs-{backend,frontend}.pid`.

Overridable via environment: `BACKEND_PORT` (5000), `FRONTEND_PORT` (5173), `DB2_PROFILE` (`/home/db2inst1/sqllib/db2profile`), `LOG_DIR` (`/tmp`).

**Paths to check on a new VM:** the scripts default `DB2_PROFILE` to `/home/db2inst1/sqllib/db2profile`. If the instance owner or home directory differs, export `DB2_PROFILE=/path/to/db2profile` before running them.

`run.sh`'s `print_urls` lists every address that reaches the frontend. All of them work — the proxy means there is no second host to keep in step.

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `SQL0104N` on `VECTOR(1024, FLOAT32)` | Db2 too old | Need 12.1.2+ (§2.1) |
| `SQL0204N` on the `DROP TABLE` lines | Tables don't exist yet | Expected on first run — ignore |
| `IMPORT` finds no file | Ran `db2 -tvf` from the wrong directory | `cd` to the project root first (§4) |
| `{"error": "DB connection failed"}` | Wrong credentials/port in `backend/.env` | Check `.env` against `db2 get dbm cfg | grep SVCENAME`; the real error prints on backend stdout |
| `ibm_db` import error | venv built with the wrong Python | Recreate with `uv venv --python $(which python3.12)` |
| `db2: command not found` in a script | `db2profile` not sourced | `source /home/db2inst1/sqllib/db2profile`, or set `DB2_PROFILE` |
| Page loads, no products, browser console shows failed XHR | Backend down, or Vite started before `vite.config.ts` was in place | `./run.sh --status`; restart with `./run.sh --stop && ./run.sh` |
| Page won't load from another machine | Vite not bound to `0.0.0.0`, or firewall | `npm run dev -- --host`; open port 5173 |
| `npm install` peer-dependency errors | React 19 vs. older carousel packages | `npm install --force` |
| `unbound variable` when sourcing `db2profile` under `set -u` | `db2profile` references AIX-only vars | The scripts pre-bind them; if scripting by hand, pre-set `LIBPATH`, `SHLIB_PATH`, `LD_LIBRARY_PATH_32`, `LD_LIBRARY_PATH_64` to empty |

---

## 11. What is intentionally not in the export

| Excluded | Recreate with |
|---|---|
| `backend/.venv/` | §5 — `uv venv` + `uv pip install -r requirements.txt` |
| `frontend/node_modules/` | §6 — `npm install` |
| `backend/.env` | §5 — `cp .env.example .env`, then fill in the password |
| `__pycache__/`, `.DS_Store` | Nothing — build/OS noise |

Everything else, including both CSV data files (≈7 MB), is in the repo. There are no other external downloads at runtime.

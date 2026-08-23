# Teaching Db2 what a customer is worth

> **Last checked 2026-08-17** — verified end to end: IDAX enabled on Db2 12.1.5, 60,252 rows
> loaded, the model trains in under a second, and predictions and error metrics come back from
> Db2 on every run. Two full train → predict → measure cycles produced identical results.  
> Checked on: Db2 12.1.5.0 · RHEL 10 · Python 3.12 · Node not required.

[← In-database ML](../README.md) · [← Db2 AI Cookbook](../../README.md)

> You know what 48,202 of your customers spent. Another 12,050 have not bought yet. Train a
> regression model **inside Db2** — one `CALL`, no export — and it tells you what those 12,050 are
> likely to be worth.

![Db2](https://img.shields.io/badge/store-Db2%2012.1%20%2B%20IDAX-054ada)
![SQL](https://img.shields.io/badge/training-one%20SQL%20statement-lightgrey)
![Python](https://img.shields.io/badge/Python-3.12-blue)

Every other module in this cookbook turns data into **vectors**. This one does not. It is the same
argument — the computation goes to the data, not the data to the computation — made against a
different opponent: instead of a standalone vector store, the thing you are avoiding is exporting a
table to scikit-learn and waiting a quarter for a model to come back.

## Quick start

Db2 12.1 with the IDAX stored procedures enabled, and a 16K-page-size database.
Neither is the default — see [Enabling IDAX](#enabling-idax) first, it takes about two minutes.

```bash
db2 -tvf dbsetup.sql          # create GOSALES, load 60,252 customers
db2 -tvf lab.sql              # the whole pipeline in SQL: split → impute → train → score → measure
```

That is the entire recipe. To see it as a story instead of a transcript, there is a small web app:

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill in DB_PASSWORD
./run.sh                      # http://localhost:5050/
```

`./run.sh --status` and `./run.sh --stop` manage it. Arrow keys move between screens.

## Expected output

`lab.sql` prints the model as a table of coefficients — what each customer attribute is worth,
in dollars:

```
(Intercept)      -                   61.7380
GENDER           M                   41.2090
MARITAL_STATUS   Married             34.0194
PROFESSION       Executive           31.4704
...
PROFESSION       Retired            -11.6709
PROFESSION       Student            -18.7435
AGE              -                    0.0496
```

Then its accuracy on 12,050 customers held back from training:

```
MAE       10.35        typical prediction is off by about $10
MAPE       8.16 %      roughly 92% accurate
```

A married male executive aged 40 scores **$170.42**; a single female student aged 20 scores
**$80.33**. That 2.1× spread, computed before either has bought anything, is the entire business
case.

The app tells the same story in four screens — the two groups of customers, the one statement that
learns from the first group, what it learned, and finally the held-back customers revealed with
predicted against actual. Each screen has a **Show the SQL** panel.

## Concepts

### Learn from the ones you know; predict the ones you don't

That sentence is all of supervised learning. `IDAX.SPLIT_DATA` divides the catalogue 80/20; the
model sees the 48,202 and never the 12,050. At the end you compare its guesses on the held-back
group against what they really spent — which is only meaningful *because* it never saw them.

```
48,202 customers with a known spend  ──train──▶  model  ──score──▶  12,050 unknowns
```

### The training is one statement

```sql
CALL IDAX.LINEAR_REGRESSION('model=GOSALES_LINREG, intable=GOSALES_TRAIN,
     id=ID, target=PURCHASE_AMOUNT, intercept=true');
```

No Python, no framework, no GPU, no data leaving the database. It returns in under a second on
48,202 rows. The model is then a first-class object in the catalogue —
`IDAX.LIST_MODELS` lists it, `IDAX.DROP_MODEL` removes it, and its coefficients are a table you
can query.

### `incolumn` does not select features — the input table does

This is the trap in this module. `IDAX.LINEAR_REGRESSION` accepts an `incolumn` parameter, and
**ignores it**: it trains on every column of `intable`. Verified here — a model trained with
`incolumn=AGE` came back with coefficients for `PRODUCT_LINE`, `IS_TENT` and everything else.

The reliable way to choose features is to build an input table containing only the columns you
want, which is what `lab.sql` does and what IBM's own reference notebook does.

### Which columns you leave out is a business decision

`GOSALES` carries `PRODUCT_LINE` and `IS_TENT` alongside the customer attributes. Including them
lowers error from $10.35 to $7.46 — and they are still excluded, deliberately.

They describe the *purchase*, not the *customer*. At the moment you are deciding whom to target,
you cannot know which product line someone will buy. A model that needs that input answers a
question you cannot ask. $7.46 is the better answer to *"they just bought a tent, what did they
spend?"*; $10.35 is the correct answer to *"is this person worth reaching?"*

### Missing data is part of the pipeline, not a prerequisite

2,592 customers have no gender recorded and 2,351 have no age. `IDAX.IMPUTE_DATA` fills them in
place — the mean for a number, a chosen value for a category — as ordinary steps in the same SQL
script. Nothing is dropped and nothing is cleaned outside the database.

### The data

`gosales-data.csv` is IBM's long-standing **GoSales** sample: 60,252 synthetic customers of a
fictional outdoor-equipment retailer, with gender, age, marital status, profession and what they
spent ($65–$185). No real person or real transaction is involved.

---

## Appendix

### Enabling IDAX

The analytic stored procedures ship with Db2 but are **not** installed into a database by default,
and there is no DDL for them anywhere in the install tree — `SYSINSTALLOBJECTS` creates them.
Following [IBM's prerequisites](https://www.ibm.com/docs/en/db2/12.1.x?topic=content-in-database-machine-learning):

```bash
db2set DB2_ENABLE_ML_PROCEDURES=YES
db2stop force && db2start                    # the registry variable needs a restart

# 16K page size is required — a 4K database fails later, in ways that do not point here
db2 "CREATE DB DB2AI USING CODESET UTF-8 TERRITORY US PAGESIZE 16384"

db2 connect to DB2AI
db2 "CREATE TABLESPACE IDAX_TBSP"
db2 "CALL SYSINSTALLOBJECTS('IDAX', 'C', 'IDAX_TBSP', NULL)"
db2 "GRANT USE OF TABLESPACE IDAX_TBSP TO PUBLIC"
```

Confirm before going further — this should report 737:

```sql
SELECT COUNT(*) FROM SYSCAT.ROUTINES WHERE ROUTINEMODULENAME='IDAX';
```

The 16K database also auto-creates `IDAX_USERTEMPSPACE`, which the procedures need.

### Credentials

`.env` holds the five `DB_*` values and nothing else — this recipe needs no API key, because it
never calls a hosted model. It is gitignored; `.env.example` shows the shape.

### Presenting this

The app is built as a five-minute talk. Open with the one-liner —

> *Marketing teams sit on customer data they can't act on. Db2 trains a model right where the data
> already lives — one statement, nothing exported. So you know who's worth reaching before you spend.*

— then let the four screens carry it. Screen 2 is where you open the SQL panel; screen 3 is where
you let someone in the room pick a customer. Keep $7.46 in reserve for *"can it do better?"*

### Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `SQL0440N ... IDAX.LIST_MODELS not found` | Procedures not installed, or the registry variable set without an instance restart | [Enabling IDAX](#enabling-idax) |
| IDAX calls fail on a database that otherwise looks fine | Database not created at 16K page size | Recreate it; page size cannot be altered |
| Model has coefficients for columns you never listed | `incolumn` is ignored — it trains on every column of `intable` | Control features via the input table's columns |
| `SQL1024N` partway through a shell script | Each `db2` invocation is its own process; a `$( )` subshell loses the CLP connection | Keep connect and query in the same subshell |
| Rerunning the lab gives different numbers | `IMPUTE_DATA` mutates the train and test tables | `lab.sql` drops and rebuilds — run it whole, not in pieces |
| `SQL0204N` on the DROP lines | Tables do not exist yet | Expected on a first run; `db2 -tvf` continues |
| `SQL0438N` from `IDAX.DROP_MODEL` | No model to drop yet | Expected on a first run. `db2 -tvf` exits 4 because of it — judge the run by the row counts and metrics, not the exit code |

### Files

```
lab.sql                the recipe — the whole pipeline in SQL, runnable on its own
dbsetup.sql            create GOSALES and load the CSV
gosales-data.csv       60,252 synthetic customers
app.py                 Flask API; the SQL dict is executed and displayed from one place
templates/index.html   the four-screen walkthrough — one file, no build step
run.sh                 start / stop / status for the app
requirements.txt       pinned
.env.example           Db2 connection template
```

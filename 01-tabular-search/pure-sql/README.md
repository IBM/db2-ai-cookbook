# Tabular similarity search in pure SQL

[← Tabular search](../README.md) · [← Db2 AI Cookbook](../../README.md)

> Find the rows most similar to a given row, using a native Db2 `VECTOR` column and a `WHERE`
> clause in the same statement. No Python, no framework, no application code — seven `.sql` files
> and `db2`.

![Db2](https://img.shields.io/badge/store-Db2%2012.1.2%2B%20VECTOR-054ada)
![No Python](https://img.shields.io/badge/runtime-SQL%20only-lightgrey)
![Status](https://img.shields.io/badge/purpose-learning%20%2F%20reference-success)

The table is `PATIENTS`: 20 rows of ordinary clinical columns — age, gender, cholesterol, blood
pressure, smoking status — plus one 768-dimension embedding per patient that encodes the whole
record. The question is *"who is most like patient 2, among people aged 35–40?"*

## Quick start

Db2 12.1's `SAMPLE` database already ships `PATIENTS` **with its embeddings**, so there is usually
nothing to set up. Confirm, then run the payoff query:

```bash
db2 connect to SAMPLE
db2 "SELECT COUNT(*) AS ROWS, COUNT(EMBEDDING) AS WITH_EMBEDDING FROM PATIENTS"
db2 -tvf 7-vector_distance.sql
```

If the count returns **20 and 20**, you are ready. If `PATIENTS` is missing — or you want to build
it on another database — see [Building the table yourself](#building-the-table-yourself) in the
appendix.

## Expected output

```
NAME                AGE  GENDER  CHOLESTEROL  BLOOD_PRESSURE  SMOKING      DISTANCE
------------------  ---  ------  -----------  --------------  -----------  --------
Cristian Santos      37  Male            195             114  Non-smoker     0.0618
Holly Wood           37  Male            160             109  Non-smoker     0.0802
Angie Henderson      38  Female          152              81  Non-smoker     0.1065
```

That ranking is worth a second look. Patient 2 — the reference — is **Noah Rhodes, Male,
cholesterol 193, BP 114, non-smoker**. Cristian Santos at **195 / 114, Male, non-smoker** is
almost the same patient clinically, and the vector places him closest. Angie Henderson differs in
gender and carries much lower numbers, and lands furthest away. The embedding encodes the record,
and the distance reflects it.

## Concepts

### One query does both jobs

```sql
SELECT NAME, AGE, GENDER, CHOLESTEROL_LEVEL, BLOOD_PRESSURE, SMOKING_STATUS,
       VECTOR_DISTANCE((SELECT EMBEDDING FROM PATIENTS WHERE PATIENT_ID = 2),
                       EMBEDDING, EUCLIDEAN) AS DISTANCE
FROM PATIENTS
WHERE PATIENT_ID <> 2
  AND AGE BETWEEN 35 AND 40
ORDER BY DISTANCE ASC
FETCH FIRST 3 ROWS ONLY;
```

1. The subquery fetches **patient 2's** embedding as the reference point.
2. `VECTOR_DISTANCE` scores every candidate against it — smaller is closer.
3. `WHERE` applies ordinary relational predicates on ordinary columns.
4. `ORDER BY DISTANCE` ranks what survives.

A dedicated vector database returns nearest neighbours and nothing else. Answering *"similar to
this one, but only aged 35–40"* with a separate vector store means searching vectors, taking the
IDs back to the database, joining and filtering there — two systems and glue code in between.
Db2 keeps the vector in the same row as the data, so the optimizer sees the whole question at
once.

This is also similarity over **structured rows**, not document chunks: each embedding stands for
an entire patient record rather than a paragraph of text, which is what separates this recipe
from the [RAG module](../../04-rag/).

### The seven files, in reading order

| File | Demonstrates | You should see |
| --- | --- | --- |
| `1-sample_patients.sql` | The plain relational data | 5 rows — Allison Hill, Noah Rhodes, Angie Henderson, Daniel Wagner, Cristian Santos |
| `2-vector_column_describe.sql` | `DESCRIBE TABLE` | 8 columns; `EMBEDDING` is `VECTOR(FLOAT32)`, length `768` |
| `3-vector_constructor.sql` | `VECTOR('[…]', 768, FLOAT32)` | Rewrites patient 20's embedding from a text literal. It writes the value the row already holds, so it is safe to re-run |
| `4-vector_serialize.sql` | `VECTOR_SERIALIZE` | Patient 2's vector as text: `[-0.0808365867,0.0543872342,…]` |
| `5-vector_dimension_count.sql` | `VECTOR_DIMENSION_COUNT` | `768` for each of the first 5 patients |
| `6-patient_2.sql` | The reference row | Noah Rhodes — 43, Male, cholesterol 193, BP 114, non-smoker |
| `7-vector_distance.sql` | `VECTOR_DISTANCE` + a `WHERE` clause | The output above |

### The data

```
PATIENTS
  PATIENT_ID         INTEGER              1 … 20
  NAME               VARCHAR(30)
  AGE                INTEGER              20 … 76
  GENDER             VARCHAR(6)
  CHOLESTEROL_LEVEL  INTEGER
  BLOOD_PRESSURE     INTEGER
  SMOKING_STATUS     VARCHAR(10)          Smoker | Non-smoker
  EMBEDDING          VECTOR(768, FLOAT32)
```

**The patient records are synthetic.** Names, ages, cholesterol levels and blood pressures were
generated with [Faker](https://faker.readthedocs.io/) — they describe no real person, and nothing
here is clinical data.

The embeddings in `patients-vectors.csv` are **pre-computed** and ship with the recipe. Producing
them is out of scope here; this recipe is about what Db2 can do once you have vectors. For
generating embeddings, see [multimodal embedding](../../02-multimodal-embedding/).

---

## Appendix

### The age filter is doing more than it appears

Exactly three patients fall between 35 and 40, so `FETCH FIRST 3` returns all of them — the
ranking is real, but no candidate is ever *rejected*. Widen the band to watch selection happen:

```sql
AND AGE BETWEEN 30 AND 50      -- 6 candidates instead of 3
```

```
Abigail Shaffer      44  194  107  Non-smoker   0.0603
Cristian Santos      37  195  114  Non-smoker   0.0618
Michele Williams     47  156  104  Non-smoker   0.0714
```

Abigail Shaffer (44, cholesterol 194, BP 107) now edges out Cristian Santos, and three of the six
candidates are dropped on distance alone.

### Building the table yourself

Only needed if `PATIENTS` is missing, or you want it on a database other than `SAMPLE`.

```bash
./dbsetup.sh <database>      # create PATIENTS, import the 20 rows
./loadvectors.sh <database>  # ALTER in the VECTOR column, load one embedding per patient
```

**You should see** `20` rows read and inserted by the `IMPORT`, then 20 successful `UPDATE`
statements.

> ⚠️ **Running `dbsetup.sh SAMPLE` destroys the `PATIENTS` table that ships with the sample
> database**, embeddings and all — it opens with `DROP TABLE PATIENTS`. It is replaced by a table
> built from `patients-data.csv`, which has no vector column until `loadvectors.sh` adds it.
> Recovering the original means recreating the sample database. On any other database there is
> nothing to drop, and the `DROP` simply reports that the table was not found.

### Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `SQL0204N  PATIENTS is an undefined name` | The table does not exist on this database | Build it — see above — or connect to `SAMPLE` |
| Queries run but return nothing you expect | The seven `.sql` files hardcode `CONNECT TO SAMPLE`, while the shell scripts take a database name | If you built the table elsewhere, edit that line in each file |
| `SQL0601N  … EMBEDDING … already exists` | `loadvectors.sh` runs `ALTER TABLE … ADD COLUMN`, but `patients_ddl.sql` already declares `EMBEDDING` | Use one path or the other, not both |
| `CREATE TABLE` fails on the `VECTOR` column | Db2 is older than 12.1.2, where the type was introduced | `db2level` to confirm; there is no workaround |
| Distances look inverted | These are **distances**, not similarity scores | Lower is closer — `ORDER BY DISTANCE ASC` |

`VECTOR_DISTANCE` also accepts `COSINE` and `MANHATTAN`. Which is correct depends on the embedding
model that produced the vectors — check what yours was trained for before changing `EUCLIDEAN`.

### Files

```
1-…7-*.sql              the demo, in reading order
dbsetup.sh              create PATIENTS and import the 20 rows
loadvectors.sh          add the VECTOR column, load one embedding per patient
patients-data.csv       the 20 synthetic patient records
patients-vectors.csv    pre-computed 768-dim vector per PATIENT_ID
patients_ddl.sql        db2look output — the table including EMBEDDING
```

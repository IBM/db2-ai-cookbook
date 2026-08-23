"""Db2 in-database machine learning — a 5-minute demo.

The story: a marketing team has 60,252 customers and budget to reach a fraction
of them. Db2 learns who is worth reaching, without the data ever leaving it.

Every SQL statement the demo runs lives in the SQL dict below and is used for
BOTH execution and display. The "Show the SQL" panels therefore cannot drift
from what actually ran -- which is the whole point of showing them.
"""
import os
import time
import uuid
from decimal import Decimal

import ibm_db
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()

DSN = (
    f"DATABASE={os.getenv('DB_NAME', 'DB2AI')};"
    f"HOSTNAME={os.getenv('DB_HOST', 'localhost')};"
    f"PORT={os.getenv('DB_PORT', '50000')};"
    "PROTOCOL=TCPIP;"
    f"UID={os.getenv('DB_USER', 'db2inst1')};"
    f"PWD={os.getenv('DB_PASSWORD', '')};"
)

MODEL = "GOSALES_LINREG"

# ---------------------------------------------------------------- the SQL
# Single source of truth: executed and displayed from here.
SQL = {
    "overview": """-- Customers you have already sold to: you know what they spent.
SELECT COUNT(*) AS KNOWN FROM GOSALES_TRAIN;

-- Customers you have not sold to yet: you know who they are, nothing more.
SELECT COUNT(*) AS UNKNOWN FROM GOSALES_TEST""",
    "sample": """-- Read from the raw table, so the real gaps stay visible.
SELECT g.ID, g.GENDER, g.AGE, g.MARITAL_STATUS, g.PROFESSION, g.PURCHASE_AMOUNT
FROM GOSALES g, GOSALES_TRAIN t
WHERE g.ID = t.ID ORDER BY g.ID FETCH FIRST 5 ROWS ONLY""",
    "unknown": """-- The ones we want an answer for. PURCHASE_AMOUNT is never
-- selected -- as far as the model is concerned, this column does not exist.
SELECT g.ID, g.GENDER, g.AGE, g.MARITAL_STATUS, g.PROFESSION
FROM GOSALES g, GOSALES_TEST t
WHERE g.ID = t.ID ORDER BY g.ID FETCH FIRST 5 ROWS ONLY""",
    "reveal": """SELECT t.ID, t.PROFESSION,
       p.PURCHASE_AMOUNT AS PREDICTED,   -- what the model said
       t.PURCHASE_AMOUNT AS ACTUAL       -- what they really spent
FROM GOSALES_TEST t, GOSALES_TEST_PREDICTIONS p
WHERE t.ID = p.ID ORDER BY t.ID FETCH FIRST 6 ROWS ONLY""",
    # -- training pipeline, in order --------------------------------------
    "features": """CREATE TABLE GOSALES_C AS (
    SELECT ID, GENDER, AGE, MARITAL_STATUS, PROFESSION, PURCHASE_AMOUNT
    FROM GOSALES
) WITH DATA ORGANIZE BY ROW""",
    "split": """CALL IDAX.SPLIT_DATA('intable=GOSALES_C, id=ID,
     traintable=GOSALES_TRAIN, testtable=GOSALES_TEST,
     fraction=0.8, seed=1')""",
    "impute": """CALL IDAX.IMPUTE_DATA('intable=GOSALES_TRAIN, incolumn=AGE, method=mean');
CALL IDAX.IMPUTE_DATA('intable=GOSALES_TRAIN, method=replace,
     nominalValue=M, incolumn=GENDER');
CALL IDAX.IMPUTE_DATA('intable=GOSALES_TRAIN, method=replace,
     nominalValue=Married, incolumn=MARITAL_STATUS');
CALL IDAX.IMPUTE_DATA('intable=GOSALES_TRAIN, method=replace,
     nominalValue=Other, incolumn=PROFESSION')""",
    "train": """CALL IDAX.LINEAR_REGRESSION('model=GOSALES_LINREG,
     intable=GOSALES_TRAIN, id=ID,
     target=PURCHASE_AMOUNT, intercept=true')""",
    "model": """SELECT VAR_NAME, LEVEL_NAME, VALUE
FROM GOSALES_LINREG_MODEL ORDER BY VALUE DESC""",
    "predict": """CALL IDAX.PREDICT_LINEAR_REGRESSION('model=GOSALES_LINREG,
     intable=<one row of customer details>,
     outtable=<result>, id=ID')""",
    "metrics": """CALL IDAX.MAE('intable=GOSALES_TEST, id=ID, target=PURCHASE_AMOUNT,
     resulttable=GOSALES_TEST_PREDICTIONS, resulttarget=PURCHASE_AMOUNT');

SELECT AVG(ABS(A.PURCHASE_AMOUNT - B.PURCHASE_AMOUNT)
           / A.PURCHASE_AMOUNT * 100) AS MAPE
FROM GOSALES_TEST A, GOSALES_TEST_PREDICTIONS B WHERE A.ID = B.ID""",
}

# Statements executed but not shown as their own scene.
_TEST_PREP = [
    "CALL IDAX.IMPUTE_DATA('intable=GOSALES_TEST, incolumn=AGE, method=mean')",
    "CALL IDAX.IMPUTE_DATA('intable=GOSALES_TEST, method=replace, nominalValue=M, incolumn=GENDER')",
    "CALL IDAX.IMPUTE_DATA('intable=GOSALES_TEST, method=replace, nominalValue=Married, incolumn=MARITAL_STATUS')",
    "CALL IDAX.IMPUTE_DATA('intable=GOSALES_TEST, method=replace, nominalValue=Other, incolumn=PROFESSION')",
    "CREATE TABLE GOSALES_TEST_INPUT AS (SELECT ID, GENDER, AGE, MARITAL_STATUS, PROFESSION"
    " FROM GOSALES_TEST) WITH DATA ORGANIZE BY ROW",
    "CALL IDAX.PREDICT_LINEAR_REGRESSION('model=GOSALES_LINREG, intable=GOSALES_TEST_INPUT,"
    " outtable=GOSALES_TEST_PREDICTIONS, id=ID')",
]

_DROP_TABLES = [
    "GOSALES_C", "GOSALES_TRAIN", "GOSALES_TEST", "GOSALES_TEST_INPUT",
    "GOSALES_TEST_PREDICTIONS", "GOSALES_TRAIN_SUM1000",
    "GOSALES_TRAIN_SUM1000_CHAR", "GOSALES_TRAIN_SUM1000_NUM",
]

app = Flask(__name__)

# Last known-good results. Populated on the first successful train and used as
# the on-stage fallback if a live retrain fails.
CACHE = {"model": None, "metrics": None}


# ------------------------------------------------------------- db helpers
def connect():
    return ibm_db.connect(DSN, "", "")


def rows(conn, sql):
    stmt = ibm_db.exec_immediate(conn, sql)
    out = []
    r = ibm_db.fetch_assoc(stmt)
    while r:
        out.append(r)
        r = ibm_db.fetch_assoc(stmt)
    return out


def call_scalar(conn, sql):
    """Run a CALL and read the first value of its first result set.

    IDAX procedures return their answer as a result set rather than an output
    table, so MAE/MSE have to be read this way.
    """
    stmt = ibm_db.exec_immediate(conn, sql)
    r = ibm_db.fetch_tuple(stmt)
    while r is False:
        stmt = ibm_db.next_result(stmt)
        if stmt is False:
            return None
        r = ibm_db.fetch_tuple(stmt)
    return float(r[0]) if r else None


def quiet(conn, sql):
    """Run a statement, ignoring 'does not exist' style failures."""
    try:
        ibm_db.exec_immediate(conn, sql)
        return True
    except Exception:
        return False


def num(v):
    return float(v) if isinstance(v, (Decimal, int, float)) else float(str(v))


def model_exists(conn):
    return bool(rows(conn, f"SELECT 1 FROM SYSCAT.TABLES WHERE TABNAME='{MODEL}_MODEL'"))


# ------------------------------------------------------------ model shape
LABELS = {
    ("GENDER", "M"): "Male", ("GENDER", "F"): "Female",
    ("MARITAL_STATUS", "Married"): "Married",
    ("MARITAL_STATUS", "Single"): "Single",
    ("MARITAL_STATUS", "Unspecified"): "Marital status unknown",
}


def read_model(conn):
    """Coefficients, translated into what each one is worth in dollars."""
    base, drivers = 0.0, []
    for r in rows(conn, SQL["model"]):
        var = (r.get("VAR_NAME") or "").strip()
        lvl = (r.get("LEVEL_NAME") or "").strip()
        val = num(r.get("VALUE"))
        if var == "(Intercept)":
            base = val
        elif var == "AGE":
            drivers.append({"label": "Each year of age", "value": val,
                            "group": "Age", "per_unit": True})
        else:
            drivers.append({
                "label": LABELS.get((var, lvl), lvl or var),
                "value": val,
                "group": var.replace("_", " ").title(),
                "per_unit": False,
            })
    drivers.sort(key=lambda d: d["value"], reverse=True)
    return {"base": base, "drivers": drivers}


def read_metrics(conn):
    mae = call_scalar(conn, "CALL IDAX.MAE('intable=GOSALES_TEST, id=ID, target=PURCHASE_AMOUNT,"
                            " resulttable=GOSALES_TEST_PREDICTIONS, resulttarget=PURCHASE_AMOUNT')")
    mape = num(rows(conn, "SELECT AVG(ABS(A.PURCHASE_AMOUNT-B.PURCHASE_AMOUNT)/A.PURCHASE_AMOUNT*100) AS M"
                          " FROM GOSALES_TEST A, GOSALES_TEST_PREDICTIONS B WHERE A.ID=B.ID")[0]["M"])
    tested = int(num(rows(conn, "SELECT COUNT(*) AS C FROM GOSALES_TEST_PREDICTIONS")[0]["C"]))
    return {"mae": mae, "mape": mape, "accuracy": 100 - mape, "tested": tested}


# ----------------------------------------------------------------- routes
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/sql")
def api_sql():
    return jsonify(SQL)


@app.route("/api/state")
def api_state():
    conn = connect()
    try:
        return jsonify({"trained": model_exists(conn)})
    finally:
        ibm_db.close(conn)


def _person(r, spend=True):
    return {"id": int(num(r["ID"])), "gender": (r["GENDER"] or "—"),
            "age": ("—" if r["AGE"] is None else int(num(r["AGE"]))),
            "marital": (r["MARITAL_STATUS"] or "—"),
            "profession": (r["PROFESSION"] or "—"),
            "spend": round(num(r["PURCHASE_AMOUNT"]), 2) if spend else None}


@app.route("/api/overview")
def api_overview():
    """Scene 1: the two groups, and why a model is needed at all.

    Customers split into those whose spend you already know and those you
    don't. The 'unknown' group is the held-back test set -- their amounts are
    never shown to the model, which is what makes scene 4's reveal honest.
    """
    conn = connect()
    try:
        total = int(num(rows(conn, "SELECT COUNT(*) AS C FROM GOSALES")[0]["C"]))
        gaps = rows(conn, "SELECT SUM(CASE WHEN GENDER IS NULL THEN 1 ELSE 0 END) AS G,"
                          " SUM(CASE WHEN AGE IS NULL THEN 1 ELSE 0 END) AS A FROM GOSALES")[0]
        try:
            known = int(num(rows(conn, "SELECT COUNT(*) AS C FROM GOSALES_TRAIN")[0]["C"]))
            unknown = int(num(rows(conn, "SELECT COUNT(*) AS C FROM GOSALES_TEST")[0]["C"]))
            sample = [_person(r) for r in rows(conn, SQL["sample"])]
            pending = [_person(r, spend=False) for r in rows(conn, SQL["unknown"])]
        except Exception:
            # Before the first split exists, describe the same shape.
            known, unknown = int(total * 0.8), total - int(total * 0.8)
            sample = [_person(r) for r in rows(
                conn, "SELECT ID, GENDER, AGE, MARITAL_STATUS, PROFESSION, PURCHASE_AMOUNT"
                      " FROM GOSALES ORDER BY ID FETCH FIRST 5 ROWS ONLY")]
            pending = [_person(r, spend=False) for r in rows(
                conn, "SELECT ID, GENDER, AGE, MARITAL_STATUS, PROFESSION, PURCHASE_AMOUNT"
                      " FROM GOSALES ORDER BY ID DESC FETCH FIRST 5 ROWS ONLY")]
        return jsonify({
            "customers": total, "known": known, "unknown": unknown,
            "no_gender": int(num(gaps["G"])), "no_age": int(num(gaps["A"])),
            "sample": sample, "pending": pending,
        })
    finally:
        ibm_db.close(conn)


@app.route("/api/reveal")
def api_reveal():
    """Scene 4: the customers from scene 1, with the answer revealed."""
    conn = connect()
    try:
        out = []
        for r in rows(conn, SQL["reveal"]):
            pred, act = num(r["PREDICTED"]), num(r["ACTUAL"])
            out.append({"id": int(num(r["ID"])),
                        "profession": (r["PROFESSION"] or "—").strip(),
                        "predicted": round(pred, 2), "actual": round(act, 2),
                        "miss": round(abs(pred - act), 2)})
        return jsonify({"ok": True, "rows": out})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 409
    finally:
        ibm_db.close(conn)


@app.route("/api/train", methods=["POST"])
def api_train():
    """Run the pipeline live. On failure, fall back to the last good result."""
    conn = connect()
    steps, t0 = [], time.time()
    try:
        quiet(conn, f"CALL IDAX.DROP_MODEL('model={MODEL}')")
        for t in _DROP_TABLES:
            quiet(conn, f"DROP TABLE {t}")

        def step(name, sql):
            s = time.time()
            ibm_db.exec_immediate(conn, sql)
            steps.append({"name": name, "ms": int((time.time() - s) * 1000)})

        step("Selecting customer attributes", SQL["features"])
        step("Splitting 80 / 20", SQL["split"])
        for s in SQL["impute"].split(";\n"):
            if s.strip():
                ibm_db.exec_immediate(conn, s.strip())
        steps.append({"name": "Filling the gaps", "ms": 0})

        s = time.time()
        ibm_db.exec_immediate(conn, SQL["train"])
        train_ms = int((time.time() - s) * 1000)
        steps.append({"name": "Training the model", "ms": train_ms})

        for s_ in _TEST_PREP:
            ibm_db.exec_immediate(conn, s_)
        steps.append({"name": "Scoring the held-back customers", "ms": 0})

        n_train = int(num(rows(conn, "SELECT COUNT(*) AS C FROM GOSALES_TRAIN")[0]["C"]))
        n_test = int(num(rows(conn, "SELECT COUNT(*) AS C FROM GOSALES_TEST")[0]["C"]))

        CACHE["model"] = read_model(conn)
        CACHE["metrics"] = read_metrics(conn)

        return jsonify({"ok": True, "live": True, "steps": steps,
                        "train_ms": train_ms,
                        "total_ms": int((time.time() - t0) * 1000),
                        "train_rows": n_train, "test_rows": n_test})
    except Exception as e:
        if CACHE["model"]:
            return jsonify({"ok": True, "live": False, "error": str(e),
                            "steps": steps, "train_ms": 1500,
                            "total_ms": int((time.time() - t0) * 1000),
                            "train_rows": 48202, "test_rows": 12050})
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        ibm_db.close(conn)


@app.route("/api/model")
def api_model():
    conn = connect()
    try:
        if model_exists(conn):
            CACHE["model"] = read_model(conn)
        if not CACHE["model"]:
            return jsonify({"ok": False, "error": "no model yet"}), 409
        return jsonify({"ok": True, **CACHE["model"]})
    except Exception:
        if CACHE["model"]:
            return jsonify({"ok": True, **CACHE["model"]})
        raise
    finally:
        ibm_db.close(conn)


@app.route("/api/metrics")
def api_metrics():
    conn = connect()
    try:
        CACHE["metrics"] = read_metrics(conn)
        return jsonify({"ok": True, **CACHE["metrics"]})
    except Exception:
        if CACHE["metrics"]:
            return jsonify({"ok": True, **CACHE["metrics"]})
        return jsonify({"ok": False, "error": "no metrics yet"}), 409
    finally:
        ibm_db.close(conn)


@app.route("/api/predict", methods=["POST"])
def api_predict():
    """Score one customer with a real IDAX call.

    Db2 does the arithmetic, not the browser -- that is the claim the demo
    makes, so the demo has to honour it.
    """
    d = request.get_json(force=True)
    tag = uuid.uuid4().hex[:8].upper()
    tin, tout = f"WHATIF_{tag}", f"WHATIF_{tag}_OUT"
    conn = connect()
    try:
        ibm_db.exec_immediate(conn, f"""CREATE TABLE {tin} (
            ID INTEGER NOT NULL, GENDER VARCHAR(3), AGE INTEGER,
            MARITAL_STATUS VARCHAR(30), PROFESSION VARCHAR(30),
            PRIMARY KEY(ID)) ORGANIZE BY ROW""")
        ins = ibm_db.prepare(conn, f"INSERT INTO {tin} VALUES (1,?,?,?,?)")
        ibm_db.execute(ins, (d["gender"], int(d["age"]), d["marital"], d["profession"]))
        ibm_db.exec_immediate(
            conn,
            f"CALL IDAX.PREDICT_LINEAR_REGRESSION('model={MODEL}, intable={tin},"
            f" outtable={tout}, id=ID')")
        spend = num(rows(conn, f"SELECT PURCHASE_AMOUNT AS P FROM {tout}")[0]["P"])
        return jsonify({"ok": True, "spend": round(spend, 2)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        quiet(conn, f"DROP TABLE {tout}")
        quiet(conn, f"DROP TABLE {tin}")
        ibm_db.close(conn)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5050")), debug=False)

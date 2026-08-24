"""A look at the actual Db2 rows the ingestion produced — in SQL, not through Haystack.

Everything else in this UI goes through the Python API. This one panel deliberately does
not: after an ingest it runs a plain SELECT so you can see that the chunks are ordinary
Db2 rows, that META really is queryable BSON, and that EMBEDDING really is a native
VECTOR rather than a blob. The README makes the same point from the `db2` CLI under
"Verify the vectors in Db2"; this is that check, run for you.

The SQL below is what the panel shows and what it runs — there is only one copy.
"""

import ibm_db

from haystack_db2_rag import settings

# JSON_VALUE reads the BSON in META, so the metadata Docling extracted is queryable with
# ordinary SQL. VECTOR_SERIALIZE renders the native VECTOR as text so it can be looked at.
SAMPLE_SQL = """SELECT SUBSTR(ID, 1, 10)                                       AS ID,
       JSON_VALUE(META, '$.page_number' RETURNING INTEGER)     AS PAGE,
       JSON_VALUE(META, '$.has_table' RETURNING VARCHAR(5))    AS HAS_TABLE,
       JSON_VALUE(META, '$.section'  RETURNING VARCHAR(200))   AS SECTION,
       SUBSTR(CONTENT, 1, 90)                                  AS CONTENT,
       SUBSTR(VECTOR_SERIALIZE(EMBEDDING), 1, 40) || '...'      AS EMBEDDING
FROM {table}
ORDER BY PAGE, ID
FETCH FIRST {limit} ROWS ONLY"""

COUNT_SQL = "SELECT COUNT(*) FROM {table}"


def _dsn() -> str:
    return (f"DATABASE={settings.DB2_DATABASE};HOSTNAME={settings.DB2_HOSTNAME};"
            f"PORT={settings.DB2_PORT};PROTOCOL=TCPIP;"
            f"UID={settings.DB2_USERNAME};PWD={settings.DB2_PASSWORD};")


def sample(limit: int = 5) -> dict:
    """Run the SELECT and return the rows plus the exact SQL that produced them."""
    limit = max(1, min(int(limit), 20))          # the only value interpolated below
    sql = SAMPLE_SQL.format(table=settings.DB2_TABLE, limit=limit)

    conn = ibm_db.connect(_dsn(), "", "")
    try:
        stmt = ibm_db.exec_immediate(conn, COUNT_SQL.format(table=settings.DB2_TABLE))
        total = ibm_db.fetch_tuple(stmt)[0]

        stmt = ibm_db.exec_immediate(conn, sql)
        columns = [ibm_db.field_name(stmt, i) for i in range(ibm_db.num_fields(stmt))]
        rows = []
        record = ibm_db.fetch_tuple(stmt)
        while record:
            # Chunks contain newlines; collapse them so the row fits one line on screen.
            # Display only — the query above is exactly what ran.
            rows.append([" ".join(str(value).split()) for value in record])
            record = ibm_db.fetch_tuple(stmt)
    finally:
        ibm_db.close(conn)

    return {"sql": sql, "columns": columns, "rows": rows, "total": total,
            "table": settings.DB2_TABLE}

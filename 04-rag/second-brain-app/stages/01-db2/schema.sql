CREATE TABLE IF NOT EXISTS DOCUMENTS (
    ID        INTEGER       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- 2000, not 2048: UNIQUE builds an index, and Db2's maximum index key
    -- length is page-size dependent (1024 bytes at 4K, 2048 at 8K). At the 8K
    -- page size db2sampl uses, VARCHAR(2048) plus key overhead overshoots and
    -- CREATE TABLE fails with SQL0613N.
    URL       VARCHAR(2000) NOT NULL UNIQUE,
    TITLE     VARCHAR(512),
    SAVED_AT  TIMESTAMP     NOT NULL DEFAULT CURRENT TIMESTAMP,
    CONTENT   CLOB(10M)     NOT NULL
);

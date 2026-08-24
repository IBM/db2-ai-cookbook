-- In-database linear regression on Db2, end to end.
--
-- Business question: which customers are worth the most, before they buy?
--
-- FEATURE CHOICE. GOSALES ships two columns that describe the *purchase* --
-- PRODUCT_LINE and IS_TENT -- alongside the ones describing the *customer*.
-- We train on customer attributes only. You cannot know which product line
-- someone will buy at the moment you are deciding who to target, so feeding
-- those in would leak the answer into the question.
--
-- This also works around a real behaviour: IDAX.LINEAR_REGRESSION trains on
-- every column of `intable` regardless of what `incolumn` says. Verified here --
-- a model trained with `incolumn=AGE` produced coefficients for PRODUCT_LINE
-- and IS_TENT too. The reliable way to choose features is to control the
-- columns of the input table, which is what IBM's own reference notebook does.

CONNECT TO DB2AI;

-- ---------------------------------------------------------------- reset
-- On a fresh database these two kinds of failure are expected and harmless:
--   SQL0438N from DROP_MODEL  -- no such model yet
--   SQL0204N from DROP TABLE  -- no such table yet
-- `db2 -tvf` reports a non-zero exit for them but continues to the next
-- statement, which is what we want. Judge the run by the row counts and
-- metrics at the end, not by the exit code.
CALL IDAX.DROP_MODEL('model=GOSALES_LINREG');

DROP TABLE IF EXISTS GOSALES_C;
DROP TABLE IF EXISTS GOSALES_TRAIN;
DROP TABLE IF EXISTS GOSALES_TEST;
DROP TABLE IF EXISTS GOSALES_TEST_INPUT;
DROP TABLE IF EXISTS GOSALES_TEST_PREDICTIONS;
DROP TABLE IF EXISTS GOSALES_TRAIN_SUM1000;
DROP TABLE IF EXISTS GOSALES_TRAIN_SUM1000_CHAR;
DROP TABLE IF EXISTS GOSALES_TRAIN_SUM1000_NUM;

-- ------------------------------------------------- 1. customer attributes
CREATE TABLE GOSALES_C AS (
    SELECT ID, GENDER, AGE, MARITAL_STATUS, PROFESSION, PURCHASE_AMOUNT
    FROM GOSALES
) WITH DATA ORGANIZE BY ROW;

-- --------------------------------------------------------- 2. train/test
CALL IDAX.SPLIT_DATA('intable=GOSALES_C, id=ID, traintable=GOSALES_TRAIN, testtable=GOSALES_TEST, fraction=0.8, seed=1');

SELECT COUNT(*) AS TRAIN_ROWS FROM GOSALES_TRAIN;
SELECT COUNT(*) AS TEST_ROWS  FROM GOSALES_TEST;

-- ------------------------------------------------- 3. what the data holds
CALL IDAX.SUMMARY1000('intable=GOSALES_TRAIN, outtable=GOSALES_TRAIN_SUM1000, incolumn=GENDER;AGE;MARITAL_STATUS;PROFESSION');

SELECT COLUMNNAME, COUNTT, DEC(AVERAGE,8,2) AS MEAN, MISSING FROM GOSALES_TRAIN_SUM1000_NUM;
SELECT COLNAME, DISTINCTVALUES, MOSTFREQUENTVALUE, MISSING FROM GOSALES_TRAIN_SUM1000_CHAR;

-- ---------------------------------------------------- 4. fill the gaps
CALL IDAX.IMPUTE_DATA('intable=GOSALES_TRAIN, incolumn=AGE, method=mean');
CALL IDAX.IMPUTE_DATA('intable=GOSALES_TRAIN, method=replace, nominalValue=M, incolumn=GENDER');
CALL IDAX.IMPUTE_DATA('intable=GOSALES_TRAIN, method=replace, nominalValue=Married, incolumn=MARITAL_STATUS');
CALL IDAX.IMPUTE_DATA('intable=GOSALES_TRAIN, method=replace, nominalValue=Other, incolumn=PROFESSION');

-- ------------------------------------------------------------- 5. train
CALL IDAX.LINEAR_REGRESSION('model=GOSALES_LINREG, intable=GOSALES_TRAIN, id=ID, target=PURCHASE_AMOUNT, intercept=true');

CALL IDAX.LIST_MODELS('format=short, all=true');

SELECT SUBSTR(VAR_NAME,1,16) AS VARIABLE, SUBSTR(COALESCE(LEVEL_NAME,'-'),1,14) AS LEVEL,
       DEC(VALUE,10,4) AS DOLLARS
FROM GOSALES_LINREG_MODEL ORDER BY VALUE DESC;

-- ----------------------------------------------------------- 6. predict
-- The test set gets the same treatment as the training set.
CALL IDAX.IMPUTE_DATA('intable=GOSALES_TEST, incolumn=AGE, method=mean');
CALL IDAX.IMPUTE_DATA('intable=GOSALES_TEST, method=replace, nominalValue=M, incolumn=GENDER');
CALL IDAX.IMPUTE_DATA('intable=GOSALES_TEST, method=replace, nominalValue=Married, incolumn=MARITAL_STATUS');
CALL IDAX.IMPUTE_DATA('intable=GOSALES_TEST, method=replace, nominalValue=Other, incolumn=PROFESSION');

-- Predictors only -- the model must not see the answer it is being asked for.
CREATE TABLE GOSALES_TEST_INPUT AS (
    SELECT ID, GENDER, AGE, MARITAL_STATUS, PROFESSION FROM GOSALES_TEST
) WITH DATA ORGANIZE BY ROW;

CALL IDAX.PREDICT_LINEAR_REGRESSION('model=GOSALES_LINREG, intable=GOSALES_TEST_INPUT, outtable=GOSALES_TEST_PREDICTIONS, id=ID');

SELECT * FROM GOSALES_TEST_PREDICTIONS FETCH FIRST 5 ROWS ONLY;

-- --------------------------------------------------------- 7. how good?
CALL IDAX.MSE('intable=GOSALES_TEST, id=ID, target=PURCHASE_AMOUNT, resulttable=GOSALES_TEST_PREDICTIONS, resulttarget=PURCHASE_AMOUNT');
CALL IDAX.MAE('intable=GOSALES_TEST, id=ID, target=PURCHASE_AMOUNT, resulttable=GOSALES_TEST_PREDICTIONS, resulttarget=PURCHASE_AMOUNT');

SELECT DEC(AVG(ABS(A.PURCHASE_AMOUNT - B.PURCHASE_AMOUNT) / A.PURCHASE_AMOUNT * 100),6,2) AS MAPE_PCT
FROM GOSALES_TEST A, GOSALES_TEST_PREDICTIONS B WHERE A.ID = B.ID;

CONNECT RESET;

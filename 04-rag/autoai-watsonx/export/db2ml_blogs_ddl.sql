-- This CLP file was created using DB2LOOK Version "12.1" 
-- Timestamp: Tue 04 Mar 2025 03:39:46 PM PST
-- Database Name: SAMPLE         
-- Database Manager Version: DB2/LINUXX8664 Version 12.1.2.0
-- Database Codepage: 1208
-- Database Collating Sequence is: IDENTITY
-- Alternate collating sequence(alt_collate): null
-- varchar2 compatibility(varchar2_compat): OFF


CONNECT TO SAMPLE;

------------------------------------------------
-- DDL Statements for Table "SHAIKHQ "."DB2ML_BLOGS"
------------------------------------------------
 

CREATE TABLE "MLBLOGS_ANSWERS"  (
		  "CHUNK" VARCHAR(1024 OCTETS) , 
		  "EMBEDDING" VECTOR(1024,FLOAT32) )












COMMIT WORK;

CONNECT RESET;

TERMINATE;


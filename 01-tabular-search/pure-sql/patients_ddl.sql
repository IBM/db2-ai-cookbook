-- This CLP file was created using DB2LOOK Version "12.1" 
-- Timestamp: Tue 04 Mar 2025 01:43:17 PM PST
-- Database Name: SAMPLE         
-- Database Manager Version: DB2/LINUXX8664 Version 12.1.2.0
-- Database Codepage: 1208
-- Database Collating Sequence is: IDENTITY
-- Alternate collating sequence(alt_collate): null
-- varchar2 compatibility(varchar2_compat): OFF


CONNECT TO SAMPLE;

------------------------------------------------
-- DDL Statements for Table "SHAIKHQ "."PATIENTS"
------------------------------------------------
 

CREATE TABLE "PATIENTS"  (
		  "PATIENT_ID" INTEGER , 
		  "NAME" VARCHAR(30 OCTETS) , 
		  "AGE" INTEGER , 
		  "GENDER" VARCHAR(6 OCTETS) , 
		  "CHOLESTEROL_LEVEL" INTEGER , 
		  "BLOOD_PRESSURE" INTEGER , 
		  "SMOKING_STATUS" VARCHAR(10 OCTETS) , 
		  "EMBEDDING" VECTOR(768,FLOAT32) )












COMMIT WORK;

CONNECT RESET;

TERMINATE;


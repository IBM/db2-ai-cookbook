#!/bin/bash

# Check if an argument is provided
if [ -z "$1" ]; then
  echo "Usage: $0 <database_name>"
  exit 1
fi

# Assign the first argument to a variable
DB_NAME=$1

# Connect to the specified database
db2 "CONNECT TO $DB_NAME"

db2 "DROP TABLE PATIENTS"


db2 "CREATE TABLE PATIENTS (
    PATIENT_ID INT,
    NAME VARCHAR(30),
    AGE INT,
    GENDER VARCHAR(6),
    CHOLESTEROL_LEVEL INT,
    BLOOD_PRESSURE INT,
    SMOKING_STATUS VARCHAR(10))"

db2 "IMPORT FROM 'patients-data.csv' OF DEL skipcount 1 INSERT INTO 
PATIENTS(PATIENT_ID, NAME, AGE, GENDER, CHOLESTEROL_LEVEL, BLOOD_PRESSURE, SMOKING_STATUS)"

db2 "CONNECT RESET"
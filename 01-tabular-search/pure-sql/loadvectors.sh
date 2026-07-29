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

db2 "ALTER TABLE PATIENTS ADD COLUMN EMBEDDING VECTOR(768, FLOAT32)"

# Read the CSV file line by line
while IFS=',' read -r patient_id vector_str; do

  # Remove both the outer single and double quotes
  # vector_str=$(echo $vector_str | sed "s/^['\"]//;s/['\"]$//")
  vector_str=$(echo $vector_str | sed 's/^"//;s/"$//')

  # echo $vector_str

  # Construct the SQL update statement

  sql_insert="UPDATE PATIENTS SET EMBEDDING = VECTOR($vector_str, 768, FLOAT32) WHERE PATIENT_ID = $patient_id;"

  echo $sql_insert>temp.sql

  # Execute the SQL update
  db2 -tvf temp.sql

done < patients-vectors.csv

# Commit the transaction
db2 commit

# Disconnect from Db2
db2 "CONNECT RESET"

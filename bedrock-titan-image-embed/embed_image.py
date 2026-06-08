"""Minimal AWS Bedrock image-embedding client, with Db2 storage.

Reads sample.jpg, embeds it with Amazon Titan Multimodal Embeddings G1, prints
the vector, then stores the image (BLOB) and its embedding (VECTOR) in a table
in the Db2 SAMPLE database. Auth + region come from .env (see .env.example).
"""

import base64
import json
import os

import boto3
import ibm_db
from dotenv import load_dotenv

load_dotenv()  # AWS_BEARER_TOKEN_BEDROCK + AWS_REGION from .env -> environment

with open("sample.jpg", "rb") as f:
    image_bytes = f.read()

# --- Embed the image with Bedrock ---
client = boto3.client("bedrock-runtime", region_name=os.environ["AWS_REGION"])
resp = client.invoke_model(
    modelId="amazon.titan-embed-image-v1",
    body=json.dumps({"inputImage": base64.b64encode(image_bytes).decode()}),
)
embedding = json.loads(resp["body"].read())["embedding"]  # 1024-dim, Titan default
print("Embedding dimension:", len(embedding))
print("First 10 values:", embedding[:10])

# --- Store image (BLOB) + embedding (VECTOR) in Db2 SAMPLE ---
# Set DB2_HOSTNAME (+ DB2_UID/DB2_PWD) in .env to run remotely; leave it unset to
# use a local trusted connection on the Db2 host itself.
db = os.environ.get("DB2_DATABASE", "SAMPLE")
if os.environ.get("DB2_HOSTNAME"):
    conn = ibm_db.connect(
        f"DATABASE={db};HOSTNAME={os.environ['DB2_HOSTNAME']};"
        f"PORT={os.environ.get('DB2_PORT', '50000')};PROTOCOL=TCPIP;"
        f"UID={os.environ['DB2_UID']};PWD={os.environ['DB2_PWD']};",
        "", "",
    )
else:
    conn = ibm_db.connect(db, "", "")
ibm_db.exec_immediate(conn, """
    CREATE TABLE IF NOT EXISTS image_embeddings (
        id        INTEGER GENERATED ALWAYS AS IDENTITY,
        filename  VARCHAR(255),
        image     BLOB(1M),
        embedding VECTOR(1024, FLOAT32)
    )
""")
stmt = ibm_db.prepare(
    conn,
    "INSERT INTO image_embeddings (filename, image, embedding)"
    " VALUES (?, ?, VECTOR(?, 1024, FLOAT32))",
)
ibm_db.bind_param(stmt, 1, "sample.jpg")
ibm_db.bind_param(stmt, 2, image_bytes, ibm_db.SQL_PARAM_INPUT, ibm_db.SQL_BLOB)
ibm_db.bind_param(stmt, 3, json.dumps(embedding))
ibm_db.execute(stmt)
print("Stored sample.jpg + embedding in SAMPLE.image_embeddings")

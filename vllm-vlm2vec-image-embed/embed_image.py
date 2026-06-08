"""Minimal vLLM image-embedding client, with Db2 storage.

Reads sample.jpg, sends it to the local vLLM embedding server, prints the
embedding's dimension and first 10 values, then stores the image (BLOB) and its
embedding (VECTOR) in a table in the Db2 SAMPLE database.

This is learning code: there is intentionally no error handling — if something
goes wrong, the exception (and the server's response) is printed as-is.

The vLLM server URL and Db2 connection are read from a local .env (see
.env.example) so the script can run remotely from the Db2 host.
"""

import base64
import json
import os

import ibm_db
import requests
from dotenv import load_dotenv

load_dotenv()  # VLLM_URL + Db2 settings (DB2_HOSTNAME / DB2_UID / DB2_PWD) from .env

URL = os.environ.get("VLLM_URL", "http://localhost:8000/v1/embeddings")
MODEL = "TIGER-Lab/VLM2Vec-Full"

# 1. Read the image off disk. Keep the raw bytes (for the Db2 BLOB) and
#    base64-encode a copy into a data URL (for the request).
with open("sample.jpg", "rb") as f:
    image_bytes = f.read()
b64 = base64.b64encode(image_bytes).decode("utf-8")
data_url = f"data:image/jpeg;base64,{b64}"

# 2. Build a vLLM embedding request. Note the chat-style `messages` array
#    (OpenAI's vision format) instead of the text-only `input` field.
payload = {
    "model": MODEL,
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": "Represent the given image."},
            ],
        }
    ],
    "encoding_format": "float",
}

# 3. Send it and unpack the vector.
resp = requests.post(URL, json=payload)
print("HTTP status:", resp.status_code)

embedding = resp.json()["data"][0]["embedding"]
print("Embedding dimension:", len(embedding))
print("First 10 values:", embedding[:10])

# 4. Store image (BLOB) + embedding (VECTOR) in Db2 SAMPLE. VLM2Vec is 3072-dim,
#    so this module uses its own table, separate from the Bedrock module's.
#    Set DB2_HOSTNAME (+ DB2_UID/DB2_PWD) in .env to run remotely; leave it unset
#    to use a local trusted connection on the Db2 host itself.
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
    CREATE TABLE IF NOT EXISTS image_embeddings_vlm2vec (
        id        INTEGER GENERATED ALWAYS AS IDENTITY,
        filename  VARCHAR(255),
        image     BLOB(1M),
        embedding VECTOR(3072, FLOAT32)
    )
""")
stmt = ibm_db.prepare(
    conn,
    "INSERT INTO image_embeddings_vlm2vec (filename, image, embedding)"
    # CAST to CLOB: a 3072-float JSON string (~40 KB) exceeds Db2's VARCHAR limit.
    " VALUES (?, ?, VECTOR(CAST(? AS CLOB(1M)), 3072, FLOAT32))",
)
ibm_db.bind_param(stmt, 1, "sample.jpg")
ibm_db.bind_param(stmt, 2, image_bytes, ibm_db.SQL_PARAM_INPUT, ibm_db.SQL_BLOB)
ibm_db.bind_param(stmt, 3, json.dumps(embedding))
ibm_db.execute(stmt)
print("Stored sample.jpg + embedding in SAMPLE.image_embeddings_vlm2vec")

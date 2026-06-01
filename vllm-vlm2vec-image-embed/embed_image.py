"""Minimal vLLM image-embedding client.

Reads sample.jpg, base64-encodes it, sends it to the local vLLM embedding
server, and prints the embedding's dimension and first 10 values.

This is learning code: there is intentionally no error handling — if something
goes wrong, the exception (and the server's response) is printed as-is.
"""

import base64

import requests

URL = "http://localhost:8000/v1/embeddings"
MODEL = "TIGER-Lab/VLM2Vec-Full"

# 1. Read the image off disk and base64-encode it into a data URL.
with open("sample.jpg", "rb") as f:
    b64 = base64.b64encode(f.read()).decode("utf-8")
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

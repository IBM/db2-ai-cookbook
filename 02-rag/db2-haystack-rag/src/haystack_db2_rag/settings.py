"""All configuration, read from .env."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# Local Db2 (needs 12.1.2+ for the VECTOR type)
DB2_DATABASE = os.getenv("DB2_DATABASE", "SAMPLE")
DB2_HOSTNAME = os.getenv("DB2_HOSTNAME", "localhost")
DB2_PORT = int(os.getenv("DB2_PORT", "50000"))
DB2_USERNAME = os.getenv("DB2_USERNAME", "db2inst1")
DB2_PASSWORD = os.getenv("DB2_PASSWORD", "")
DB2_TABLE = os.getenv("DB2_TABLE_NAME", "HAYSTACK_DOCUMENTS")

# The two llama.cpp servers (scripts/llama-servers.sh)
EMBED_BASE_URL = os.getenv("EMBED_BASE_URL", "http://127.0.0.1:8081/v1")
EMBED_MODEL = os.getenv("EMBED_MODEL", "bge-small-en-v1.5")
EMBED_DIM = 384  # bge-small-en-v1.5 produces 384 numbers per embedding

# The chunker counts tokens with the same tokenizer the embedding model uses.
# bge-small accepts 512; we ask for less because Docling prepends section headings
# to each chunk after the budget is applied, which can push it a little over.
EMBED_TOKENIZER = "BAAI/bge-small-en-v1.5"
EMBED_MAX_TOKENS = 448

CHAT_BASE_URL = os.getenv("CHAT_BASE_URL", "http://127.0.0.1:8080/v1")
CHAT_MODEL = os.getenv("CHAT_MODEL", "qwen2.5-3b-instruct")

# llama.cpp ignores the key, but the OpenAI client insists on a non-empty one.
API_KEY = "sk-no-key-required"

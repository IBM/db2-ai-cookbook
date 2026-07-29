# Document Ingestion API

FastAPI service that ingests web documents into a vector database for AI semantic search.

## Setup

```bash
# Install dependencies
uv add fastapi uvicorn httpx pydantic trafilatura spacy \
       langchain-community langchain-text-splitters langchain-core \
       langchain_ibm langchain-db2 langgraph ibm_db python-dotenv \
       llama-cpp-python

# Download models to parent directory
mkdir -p ../models
uv pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl
wget -O ../models/granite-embedding-30m-english-Q6_K.gguf \
  https://huggingface.co/lmstudio-community/granite-embedding-30m-english-GGUF/resolve/main/granite-embedding-30m-english-Q6_K.gguf
```

## Configuration

Create `.env` file in the parent directory:
```env
WATSONX_PROJECT=
WATSONX_APIKEY=
DB_NAME=your_database_name
DB_HOST=your_database_host
DB_PORT=50000
DB_PROTOCOL=TCPIP
DB_USER=your_username
DB_PASSWORD=your_password
```

## Run

```bash
uv run uvicorn ingestion_api:app --reload --host 0.0.0.0 --port 8001
```

Visit: http://localhost:8001/docs

## Usage

### Ingest Document
```bash
curl -X POST "http://localhost:8001/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://community.ibm.com/community/user/blogs/shaikh-quader/2024/05/27/db2ai-pyudf",
    "table_name": "AI_KNOWLEDGE"
  }'
```

### Clear Table
```bash
curl -X POST "http://localhost:8001/clear" \
  -H "Content-Type: application/json" \
  -d '{
    "table_name": "AI_KNOWLEDGE",
    "confirm": true
  }'
```

### Health Check
```bash
curl -X GET "http://localhost:8001/health"
```

## Requirements

- Python 3.13+
- UV package manager
- IBM DB2 database with vector support
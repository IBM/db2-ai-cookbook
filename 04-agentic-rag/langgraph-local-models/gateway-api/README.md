# Gateway API

All-in-one FastAPI service that embeds both document ingestion and intelligent search capabilities. No need to run separate microservices - everything runs in a single process.

## Overview

The Gateway API provides a unified interface for the complete Agentic RAG pipeline:
- **Document Ingestion**: Web scraping, chunking, and vector storage  
- **Intelligent Search**: AI-powered question answering with query rewriting
- **Table Management**: Create, clear, and manage vector database tables

## Setup

### Prerequisites
- Python 3.13+
- UV package manager
- IBM Watsonx account and API key
- IBM DB2 database with vector support

### Installation

```bash
# 1. Create gateway project
mkdir gateway-api && cd gateway-api
uv init --python 3.13

# 2. Install dependencies
uv add fastapi uvicorn pydantic python-dotenv \
       langchain-ibm langgraph langchain langchain-core \
       langchain-community langchain-db2 llama-cpp-python \
       ibm_db httpx trafilatura spacy

# 3. Install spaCy model
uv pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl

# 4. Copy gateway_api.py to this folder
```

### Project Structure

The gateway expects this folder structure:

```
parent-directory/
├── ingestion-api/
│   └── ingestion_api.py
├── search-api/
│   └── search_api.py
├── gateway-api/
│   ├── gateway_api.py
│   ├── pyproject.toml
│   └── README.md
├── models/
│   └── granite-embedding-30m-english-Q6_K.gguf
└── .env
```

### Configuration

Create `.env` file in the parent directory:

```env
# IBM Watsonx Configuration
WATSONX_APIKEY=your_watsonx_api_key_here
WATSONX_PROJECT=your_watsonx_project_id_here

# IBM DB2 Database Configuration
DB_NAME=your_database_name
DB_HOST=your_database_host
DB_PORT=50000
DB_PROTOCOL=TCPIP
DB_USER=your_username
DB_PASSWORD=your_password
```

## Run

```bash
# Single command - starts everything!
uv run uvicorn gateway_api:app --reload --host 0.0.0.0 --port 8000
```

On startup, you should see:
```
Starting All-in-One RAG API...
Ingestion and Search services embedded
Search service initialized successfully
```

## API Documentation

Visit http://localhost:8000/docs for interactive API documentation.

## Usage

### 1. Ingest Documents

```bash
curl -X POST "http://localhost:8000/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://community.ibm.com/community/user/blogs/shaikh-quader/2024/05/27/db2ai-pyudf",
    "table_name": "AI_KNOWLEDGE",
    "max_words": 200,
    "overlap_words": 50
  }'
```

**Response:**
```json
{
  "success": true,
  "message": "Added 23 chunks to existing table 'AI_KNOWLEDGE'",
  "chunks_created": 23
}
```

### 2. Search Documents

```bash
curl -X POST "http://localhost:8000/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How to calculate summary statistics in DB2?",
    "table_name": "AI_KNOWLEDGE"
  }'
```

**Response:**
```json
{
  "success": true,
  "answer": "DB2 provides several built-in functions for calculating summary statistics including AVG(), SUM(), COUNT(), MIN(), MAX(), STDDEV(), and VARIANCE(). These functions can be used in SELECT statements with GROUP BY clauses for grouped statistics."
}
```

### 3. Clear Tables

```bash
curl -X POST "http://localhost:8000/clear" \
  -H "Content-Type: application/json" \
  -d '{
    "table_name": "AI_KNOWLEDGE",
    "confirm": true
  }'
```

### 4. Health Check

```bash
curl "http://localhost:8000/health"
```

**Response:**
```json
{
  "status": "healthy",
  "services": {
    "ingestion": "healthy",
    "search": "healthy"
  },
  "mode": "all-in-one"
}
```

### 5. Service Information

```bash
curl "http://localhost:8000/services"
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Service information and available endpoints |
| POST | `/ingest` | Ingest documents from URLs into vector database |
| POST | `/search` | Search documents using Agentic RAG |
| POST | `/clear` | Clear/delete vector database tables |
| GET | `/health` | Health check for all embedded services |
| GET | `/services` | List all available services and endpoints |

## How It Works

### Architecture

```
Client Request
     ↓
Gateway API (Single Process)
     ↓
┌─────────────────┬─────────────────┐
│  Ingestion      │   Search        │
│  Functions      │   Functions     │
│                 │                 │
│ • Web scraping  │ • LangGraph     │
│ • Text chunking │ • Query rewrite │
│ • Embedding     │ • Watsonx LLM   │
│ • Vector store  │ • Answer gen    │
└─────────────────┴─────────────────┘
     ↓                    ↓
IBM DB2 Vector Database
```

### Embedded Services

The gateway imports and runs both services directly:
- **No HTTP calls** between services - direct function calls
- **Shared dependencies** - single set of libraries  
- **Unified error handling** - consistent response format
- **Single startup** - all initialization happens together

## Benefits

**Simplified Deployment**
- Single command to start everything
- One set of dependencies to manage
- No service discovery or networking issues

**Development Friendly**
- Fast iteration with hot reload
- Easier debugging - everything in one process
- Reduced complexity for local development

**Production Ready**
- All the same functionality as separate microservices
- Proper error handling and health monitoring
- Configurable through environment variables

## Troubleshooting

### Service Not Available Errors

If you see "Service not available" errors:

1. **Check folder structure**: Ensure `ingestion-api/` and `search-api/` folders exist in parent directory
2. **Verify file names**: Files should be named `ingestion_api.py` and `search_api.py`
3. **Check dependencies**: Run `uv sync` to ensure all packages are installed

### Search Service Initialization Failed

If search service fails to initialize:

1. **Check Watsonx credentials** in `.env` file
2. **Verify database connection** - ensure DB2 is accessible
3. **Check embedding model** - ensure `granite-embedding-30m-english-Q6_K.gguf` exists in `../models/`

### Import Errors

If you see import errors on startup:

```bash
# Check Python path and folder structure
ls -la ../
ls -la ../ingestion-api/
ls -la ../search-api/

# Verify all dependencies are installed
uv sync
```

### Performance Issues

For better performance in production:
- Use `uvicorn` with multiple workers: `--workers 4`
- Consider separating back to microservices for horizontal scaling
- Monitor memory usage as everything runs in single process

## Development

To modify the gateway:

1. **Add new endpoints**: Add routes to `gateway_api.py`
2. **Modify child services**: Edit `ingestion_api.py` or `search_api.py` in their respective folders
3. **Update dependencies**: Use `uv add package_name`
4. **Test changes**: The reload flag will automatically restart on file changes

The gateway automatically picks up changes to the embedded services since they're imported directly.
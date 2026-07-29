# Search API

Minimalistic Agentic RAG Q&A service using IBM Watsonx and LangGraph.

## Setup

```bash
# Install dependencies  
uv add fastapi uvicorn python-dotenv pydantic \
       langchain-ibm langgraph langchain langchain-core \
       langchain-community langchain-db2 llama-cpp-python ibm_db

# Use the same embedding model from document-ingestion-api
# (Model should already be in ../models/ directory)
```

## Configuration

Uses the same `.env` file from parent directory as document-ingestion-api:
```env
# IBM Watsonx Configuration
WATSONX_APIKEY=your_watsonx_api_key_here
WATSONX_PROJECT=your_watsonx_project_id_here

# IBM DB2 Database Configuration (shared with ingestion API)
DB_NAME=your_database_name
DB_HOST=your_database_host  
DB_PORT=50000
DB_PROTOCOL=TCPIP
DB_USER=your_username
DB_PASSWORD=your_password
```

## Run

```bash
uv run uvicorn search_api:app --reload --host 0.0.0.0 --port 8002
```

Visit: http://localhost:8002/docs

## Usage

### Search Documents
```bash
curl -X POST "http://localhost:8002/search" \
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
  "answer": "DB2 provides several built-in functions for calculating summary statistics including AVG(), SUM(), COUNT(), MIN(), MAX(), STDDEV(), and VARIANCE()."
}
```

### Health Check
```bash
curl -X GET "http://localhost:8002/health"
```

## Requirements

- Python 3.11+
- UV package manager  
- IBM Watsonx account and API key
- IBM DB2 database with vector support
- Documents ingested using document-ingestion-api
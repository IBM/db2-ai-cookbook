"""
Document Ingestion API

Ingests web documents into vector database for AI search.
Extracts text from URLs, chunks it, and stores with embeddings.
"""

import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
from dotenv import load_dotenv
import trafilatura
import spacy
import ibm_db_dbi
from langchain_community.embeddings import LlamaCppEmbeddings
from langchain_community.vectorstores.utils import DistanceStrategy
from langchain_db2.db2vs import DB2VS

# Load .env from parent directory
parent_dir = Path(__file__).parent.parent
load_dotenv(parent_dir / ".env")

app = FastAPI(
    title="Document Ingestion API", 
    version="1.0.0",
    description="API for ingesting web documents into vector database for AI search"
)

# ============================================================================
# DATA MODELS
# ============================================================================

class IngestRequest(BaseModel):
    """Request model for document ingestion"""
    url: HttpUrl
    table_name: str = "Documents_EUCLIDEAN"
    max_words: int = 200
    overlap_words: int = 50

class IngestResponse(BaseModel):
    """Response model for document ingestion"""
    success: bool
    message: str
    chunks_created: int = 0

class ClearRequest(BaseModel):
    """Request model for clearing table"""
    table_name: str
    confirm: bool = False  # Safety flag to prevent accidental deletion

class ClearResponse(BaseModel):
    """Response model for clearing table"""
    success: bool
    message: str

# ============================================================================
# INITIALIZATION
# ============================================================================

# Load spaCy model for sentence splitting
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    raise HTTPException(
        status_code=500, 
        detail="spaCy English model not found. Install with: python -m spacy download en_core_web_sm"
    )

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_db_connection():
    """Connect to IBM DB2 database using environment variables"""
    conn_str = f"DATABASE={os.getenv('DB_NAME')};hostname={os.getenv('DB_HOST')};port={os.getenv('DB_PORT')};protocol={os.getenv('DB_PROTOCOL')};uid={os.getenv('DB_USER')};pwd={os.getenv('DB_PASSWORD')}"
    
    try:
        return ibm_db_dbi.connect(conn_str, '', '')
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection failed: {str(e)}")

def get_embeddings():
    """Load Granite embedding model from parent/models/ directory"""
    parent_dir = Path(__file__).parent.parent
    model_paths = [
        parent_dir / "models" / "granite-embedding-30m-english-Q6_K.gguf",  # Preferred: parent/models/
        "models/granite-embedding-30m-english-Q6_K.gguf",  # Fallback: local models/
        Path(__file__).parent / "models" / "granite-embedding-30m-english-Q6_K.gguf",
        "granite-embedding-30m-english-Q6_K.gguf",  # Fallback: current directory
        Path(__file__).parent / "granite-embedding-30m-english-Q6_K.gguf"
    ]
    
    for path in model_paths:
        if Path(path).exists():
            return LlamaCppEmbeddings(model_path=str(path))
    
    raise FileNotFoundError(
        "Embedding model file 'granite-embedding-30m-english-Q6_K.gguf' not found. "
        "Expected locations: parent/models/ directory, local models/ directory, or current directory"
    )

def chunk_text(text, max_words=200, overlap_words=50):
    """Split text into overlapping chunks using sentence boundaries"""
    doc = nlp(text)
    sentences = [sent.text.strip() for sent in doc.sents if sent.text.strip()]
    
    chunks = []
    current_chunk = []
    current_length = 0

    i = 0
    while i < len(sentences):
        sentence = sentences[i]
        sentence_length = len(sentence.split())

        if current_length + sentence_length <= max_words:
            current_chunk.append(sentence)
            current_length += sentence_length
            i += 1
        else:
            # Save current chunk
            chunks.append(" ".join(current_chunk))
            
            # Create overlap for context
            overlap = []
            overlap_len = 0
            j = len(current_chunk) - 1
            
            while j >= 0 and overlap_len < overlap_words:
                s = current_chunk[j]
                overlap.insert(0, s)
                overlap_len += len(s.split())
                j -= 1
                
            current_chunk = overlap
            current_length = overlap_len

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks

def table_exists(connection, table_name):
    """Check if database table exists"""
    cursor = connection.cursor()
    cursor.execute("""
        SELECT COUNT(*) FROM SYSCAT.TABLES 
        WHERE TABNAME = ? AND TABSCHEMA = CURRENT SCHEMA
    """, (table_name.upper(),))
    exists = cursor.fetchone()[0] > 0
    cursor.close()
    return exists

def drop_table(connection, table_name):
    """Drop/delete a database table completely"""
    cursor = connection.cursor()
    try:
        cursor.execute(f"DROP TABLE {table_name}")
        connection.commit()
        cursor.close()
        return True
    except Exception as e:
        cursor.close()
        raise e

def truncate_table(connection, table_name):
    """Remove all rows from table but keep table structure"""
    cursor = connection.cursor()
    try:
        cursor.execute(f"TRUNCATE TABLE {table_name} IMMEDIATE")
        connection.commit()
        cursor.close()
        return True
    except Exception as e:
        cursor.close()
        raise e

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.post("/ingest", response_model=IngestResponse)
async def ingest_document(request: IngestRequest):
    """
    Ingest document from URL into vector database
    
    Steps: fetch URL -> extract text -> chunk -> embed -> store in DB2
    """
    try:
        # Fetch and extract text
        print(f"Fetching content from: {request.url}")
        downloaded = trafilatura.fetch_url(str(request.url))
        if not downloaded:
            raise HTTPException(status_code=400, detail="Failed to fetch content from URL")
        
        print("Extracting text from HTML...")
        article = trafilatura.extract(downloaded)
        if not article:
            raise HTTPException(status_code=400, detail="Failed to extract text from URL")
        
        # Chunk text
        print(f"Splitting text into chunks (max {request.max_words} words, {request.overlap_words} overlap)...")
        chunks = chunk_text(article, request.max_words, request.overlap_words)
        if not chunks:
            raise HTTPException(status_code=400, detail="No text chunks were created")
        print(f"Created {len(chunks)} chunks")
        
        # Setup database and embeddings
        print("Connecting to database...")
        connection = get_db_connection()
        
        print("Loading embedding model...")
        embeddings = get_embeddings()
        
        # Store in database
        print(f"Checking if table '{request.table_name}' exists...")
        
        if table_exists(connection, request.table_name):
            print("Table exists - adding chunks to existing table...")
            vectorstore = DB2VS(
                client=connection, 
                table_name=request.table_name,
                embedding_function=embeddings
            )
            vectorstore.add_texts(texts=chunks)
            message = f"Added {len(chunks)} chunks to existing table '{request.table_name}'"
        else:
            print("Table doesn't exist - creating new table...")
            vectorstore = DB2VS.from_texts(
                texts=chunks,
                embedding=embeddings,
                client=connection,
                table_name=request.table_name,
                distance_strategy=DistanceStrategy.EUCLIDEAN_DISTANCE,
            )
            message = f"Created table '{request.table_name}' with {len(chunks)} chunks"
        
        connection.close()
        print("Ingestion completed successfully!")
        
        return IngestResponse(
            success=True,
            message=message,
            chunks_created=len(chunks)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error during ingestion: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")

@app.post("/clear", response_model=ClearResponse)
async def clear_table(request: ClearRequest):
    """
    Clear/delete a vector database table
    
    Options:
    - Drop table completely (if confirm=True)
    - Truncate table (remove all rows, keep structure)
    """
    try:
        if not request.confirm:
            raise HTTPException(
                status_code=400, 
                detail="Must set 'confirm=true' to clear table. This action cannot be undone."
            )
        
        print(f"Connecting to database...")
        connection = get_db_connection()
        
        print(f"Checking if table '{request.table_name}' exists...")
        if not table_exists(connection, request.table_name):
            connection.close()
            raise HTTPException(
                status_code=404, 
                detail=f"Table '{request.table_name}' does not exist"
            )
        
        # Drop the table completely
        print(f"Dropping table '{request.table_name}'...")
        drop_table(connection, request.table_name)
        
        connection.close()
        print(f"Table '{request.table_name}' cleared successfully!")
        
        return ClearResponse(
            success=True,
            message=f"Table '{request.table_name}' has been completely removed"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error clearing table: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to clear table: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy", 
        "service": "Document Ingestion API",
        "description": "Ready to ingest documents into vector database"
    }

# ============================================================================
# APPLICATION STARTUP
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    print("Starting Document Ingestion API...")
    print("Documentation available at: http://localhost:8001/docs")
    print("Health check at: http://localhost:8001/health")
    uvicorn.run(app, host="0.0.0.0", port=8001)
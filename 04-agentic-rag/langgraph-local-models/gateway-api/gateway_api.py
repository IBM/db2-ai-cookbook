"""
All-in-One RAG API

Single FastAPI application that includes both ingestion and search functionality.
"""

import sys
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Add parent directory to path to import sibling modules
parent_dir = Path(__file__).parent.parent
sys.path.append(str(parent_dir))

# Import the other APIs
try:
    # Add the child API directories to Python path
    sys.path.append(str(parent_dir / "ingestion-api"))
    sys.path.append(str(parent_dir / "search-api"))
    
    from ingestion_api import app as ingestion_app
    from search_api import app as search_app
    SERVICES_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import child APIs: {e}")
    print("Make sure ingestion-api and search-api folders are in parent directory")
    SERVICES_AVAILABLE = False
    ingestion_app = None
    search_app = None

app = FastAPI(
    title="All-in-One RAG API", 
    version="1.0.0",
    description="Unified API with embedded ingestion and search services"
)

# ============================================================================
# MODELS
# ============================================================================

class IngestRequest(BaseModel):
    url: str
    table_name: str = "AI_KNOWLEDGE"
    max_words: int = 200
    overlap_words: int = 50

class SearchRequest(BaseModel):
    query: str
    table_name: str = "AI_KNOWLEDGE"

class ClearRequest(BaseModel):
    table_name: str
    confirm: bool = False

# ============================================================================
# MOUNT SUB-APPLICATIONS
# ============================================================================

if SERVICES_AVAILABLE:
    # Mount the child APIs as sub-applications
    app.mount("/internal/ingestion", ingestion_app)
    app.mount("/internal/search", search_app)

# ============================================================================
# UNIFIED ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint"""
    status = "available" if SERVICES_AVAILABLE else "limited - child APIs not found"
    return {
        "service": "All-in-One RAG API",
        "status": status,
        "endpoints": ["/ingest", "/search", "/clear", "/health"]
    }

@app.post("/ingest")
async def ingest(request: IngestRequest):
    """Ingest document from URL"""
    if not SERVICES_AVAILABLE:
        raise HTTPException(status_code=503, detail="Ingestion service not available")
    
    # Import the ingestion function directly
    sys.path.append(str(parent_dir / "ingestion-api"))
    from ingestion_api import ingest_document
    return await ingest_document(request)

@app.post("/search")
async def search(request: SearchRequest):
    """Search documents using Agentic RAG"""
    if not SERVICES_AVAILABLE:
        raise HTTPException(status_code=503, detail="Search service not available")
    
    # Import the search function directly
    sys.path.append(str(parent_dir / "search-api"))
    from search_api import search
    return await search(request)

@app.post("/clear")
async def clear_table(request: ClearRequest):
    """Clear/delete a vector database table"""
    if not SERVICES_AVAILABLE:
        raise HTTPException(status_code=503, detail="Ingestion service not available")
    
    # Import the clear function directly
    sys.path.append(str(parent_dir / "ingestion-api"))
    from ingestion_api import clear_table
    return await clear_table(request)

@app.get("/health")
async def health():
    """Health check for all services"""
    if not SERVICES_AVAILABLE:
        return {
            "status": "degraded",
            "message": "Child APIs not available",
            "services": {
                "ingestion": "not_imported",
                "search": "not_imported"
            }
        }
    
    services = {}
    
    # Check ingestion service
    try:
        sys.path.append(str(parent_dir / "ingestion-api"))
        from ingestion_api import health_check
        await health_check()
        services["ingestion"] = "healthy"
    except Exception as e:
        services["ingestion"] = f"error: {str(e)}"
    
    # Check search service
    try:
        sys.path.append(str(parent_dir / "search-api"))
        from search_api import health_check
        await health_check()
        services["search"] = "healthy"
    except Exception as e:
        services["search"] = f"error: {str(e)}"
    
    # Overall status
    status = "healthy" if all("error" not in str(v) for v in services.values()) else "degraded"
    
    return {
        "status": status,
        "services": services,
        "mode": "all-in-one"
    }

# ============================================================================
# DIRECT ACCESS ENDPOINTS (Optional)
# ============================================================================

@app.get("/services")
async def list_services():
    """List available services and their endpoints"""
    if not SERVICES_AVAILABLE:
        return {"message": "No child services available"}
    
    return {
        "services": {
            "ingestion": {
                "mounted_at": "/internal/ingestion",
                "endpoints": ["POST /ingest", "POST /clear", "GET /health"]
            },
            "search": {
                "mounted_at": "/internal/search", 
                "endpoints": ["POST /search", "GET /health"]
            }
        },
        "unified_endpoints": ["/ingest", "/search", "/clear", "/health"]
    }

# ============================================================================
# APPLICATION STARTUP
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize embedded services on startup"""
    if SERVICES_AVAILABLE:
        try:
            # Initialize search service components
            sys.path.append(str(parent_dir / "search-api"))
            from search_api import initialize_components
            initialize_components()
            print("Search service initialized successfully")
        except Exception as e:
            print(f"Warning: Failed to initialize search service: {e}")

if __name__ == "__main__":
    import uvicorn
    print("Starting All-in-One RAG API...")
    if SERVICES_AVAILABLE:
        print("Ingestion and Search services embedded")
    else:
        print("Child services not available - limited functionality")
    print("API available at: http://localhost:8000")
    print("Documentation at: http://localhost:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000)
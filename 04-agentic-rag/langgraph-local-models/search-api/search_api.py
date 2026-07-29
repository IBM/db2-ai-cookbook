"""
Search API

Minimalistic Agentic RAG Q&A service using IBM Watsonx and LangGraph.
"""

import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from dotenv import load_dotenv
import ibm_db_dbi

# LangGraph imports
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_ibm import ChatWatsonx
from langchain_community.embeddings import LlamaCppEmbeddings
from langchain_db2.db2vs import DB2VS
from langchain.tools import tool

# Load .env from parent directory
parent_dir = Path(__file__).parent.parent
load_dotenv(parent_dir / ".env")

# Global variables
llm = None
graph = None

# ============================================================================
# DATA MODELS
# ============================================================================

class SearchRequest(BaseModel):
    """Request model for search API"""
    query: str = Field(..., description="User's search query", min_length=1)
    table_name: str = Field(default="AI_KNOWLEDGE", description="Vector database table to search")

class SearchResponse(BaseModel):
    """Response model for search API"""
    success: bool
    answer: str

class GradeDocuments(BaseModel):
    """Grade documents using a binary score for relevance check."""
    binary_score: str = Field(description="Relevance score: 'yes' if relevant, or 'no' if not relevant")

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_db_connection():
    """Connect to IBM DB2 database"""
    conn_str = f"DATABASE={os.getenv('DB_NAME')};hostname={os.getenv('DB_HOST')};port={os.getenv('DB_PORT')};protocol={os.getenv('DB_PROTOCOL')};uid={os.getenv('DB_USER')};pwd={os.getenv('DB_PASSWORD')}"
    try:
        return ibm_db_dbi.connect(conn_str, '', '')
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection failed: {str(e)}")

def get_embeddings():
    """Load Granite embedding model"""
    parent_dir = Path(__file__).parent.parent
    model_path = parent_dir / "models" / "granite-embedding-30m-english-Q6_K.gguf"
    
    if model_path.exists():
        return LlamaCppEmbeddings(model_path=str(model_path))
    
    raise FileNotFoundError("Embedding model not found in ../models/ directory")

@tool
def retriever_tool(query: str) -> str:
    """Retrieve relevant documents from vector database"""
    try:
        connection = get_db_connection()
        embeddings = get_embeddings()
        
        vectorstore = DB2VS(
            client=connection,
            table_name="AI_KNOWLEDGE",  # Default table
            embedding_function=embeddings
        )
        
        docs = vectorstore.similarity_search(query, k=3)
        connection.close()
        
        if not docs:
            return "No relevant documents found."
        
        return "\n\n".join([f"Document {i+1}:\n{doc.page_content}" for i, doc in enumerate(docs)])
        
    except Exception as e:
        return f"Error retrieving documents: {str(e)}"

# ============================================================================
# WORKFLOW NODES
# ============================================================================

def generate_query_or_respond(state: MessagesState):
    """Decide whether to retrieve documents or respond directly"""
    response = llm.bind_tools([retriever_tool]).invoke(state["messages"])
    return {"messages": [response]}

def grade_documents(state: MessagesState) -> Literal["generate_answer", "rewrite_question"]:
    """Grade document relevance"""
    question = state["messages"][0].content
    context = state["messages"][-1].content
    
    prompt = f"Grade relevance of document to question. Document: {context}\nQuestion: {question}\nRelevant? Answer 'yes' or 'no'."
    
    response = llm.with_structured_output(GradeDocuments).invoke([{"role": "user", "content": prompt}])
    
    return "generate_answer" if response.binary_score == "yes" else "rewrite_question"

def rewrite_question(state: MessagesState):
    """Rewrite the question for better retrieval"""
    question = state["messages"][0].content
    prompt = f"Rewrite this question for better search results: {question}"
    
    response = llm.invoke([{"role": "user", "content": prompt}])
    return {"messages": [{"role": "user", "content": response.content}]}

def generate_answer(state: MessagesState):
    """Generate final answer"""
    question = state["messages"][0].content
    context = state["messages"][-1].content
    prompt = f"Answer this question using the context. Keep it concise.\nQuestion: {question}\nContext: {context}"
    
    response = llm.invoke([{"role": "user", "content": prompt}])
    return {"messages": [response]}

def build_graph():
    """Build the workflow graph"""
    workflow = StateGraph(MessagesState)
    
    workflow.add_node(generate_query_or_respond)
    workflow.add_node("retrieve", ToolNode([retriever_tool]))
    workflow.add_node(rewrite_question)
    workflow.add_node(generate_answer)
    
    workflow.add_edge(START, "generate_query_or_respond")
    workflow.add_conditional_edges("generate_query_or_respond", tools_condition, {"tools": "retrieve", END: END})
    workflow.add_conditional_edges("retrieve", grade_documents)
    workflow.add_edge("generate_answer", END)
    workflow.add_edge("rewrite_question", "generate_query_or_respond")
    
    return workflow.compile()

def initialize_components():
    """Initialize LLM and graph"""
    global llm, graph
    
    # Test Watsonx connection
    try:
        llm = ChatWatsonx(
            url="https://us-south.ml.cloud.ibm.com",
            apikey=os.getenv("WATSONX_APIKEY"),
            model_id="mistralai/mistral-large",
            project_id=os.getenv("WATSONX_PROJECT"),
            params={"temperature": 0}
        )
        
        # Test connection with a simple call
        test_response = llm.invoke([{"role": "user", "content": "Hello"}])
        
    except Exception as e:
        raise e
    
    graph = build_graph()

# ============================================================================
# FASTAPI APPLICATION
# ============================================================================

app = FastAPI(
    title="Search API",
    version="1.0.0",
    description="Minimalistic Agentic RAG Q&A service"
)

@app.on_event("startup")
async def startup_event():
    """Initialize components on startup"""
    initialize_components()

@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """Perform intelligent search using Agentic RAG"""
    try:
        if graph is None:
            raise HTTPException(status_code=503, detail="Service not initialized")
        
        initial_state = {"messages": [{"role": "user", "content": request.query}]}
        
        final_answer = ""
        try:
            for chunk in graph.stream(initial_state):
                for node, update in chunk.items():
                    if node == "generate_answer" and update.get("messages"):
                        final_answer = update["messages"][-1].content
                        break
        except Exception as graph_error:
            # Fallback: try direct retrieval without the full workflow
            try:
                retrieved_docs = retriever_tool.invoke({"query": request.query})
                
                # Simple prompt for answer generation
                simple_prompt = f"Based on this context, answer the question briefly:\n\nQuestion: {request.query}\n\nContext: {retrieved_docs}"
                
                response = llm.invoke([{"role": "user", "content": simple_prompt}])
                final_answer = response.content
                
            except Exception as fallback_error:
                raise HTTPException(
                    status_code=500, 
                    detail=f"Both main workflow and fallback failed. Watsonx error: {str(graph_error)}"
                )
        
        if not final_answer:
            raise HTTPException(status_code=500, detail="No answer generated")
        
        return SearchResponse(success=True, answer=final_answer)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    status = {"service": "Search API"}
    
    # Check LLM
    try:
        if llm is not None:
            test_response = llm.invoke([{"role": "user", "content": "test"}])
            status["watsonx"] = "healthy"
        else:
            status["watsonx"] = "not_initialized"
    except Exception as e:
        status["watsonx"] = f"error: {str(e)}"
    
    # Check database
    try:
        conn = get_db_connection()
        conn.close()
        status["database"] = "healthy"
    except Exception as e:
        status["database"] = f"error: {str(e)}"
    
    # Check embeddings
    try:
        embeddings = get_embeddings()
        status["embeddings"] = "healthy"
    except Exception as e:
        status["embeddings"] = f"error: {str(e)}"
    
    # Overall status
    if all("error" not in str(v) for v in status.values() if v != "Search API"):
        status["status"] = "healthy"
    else:
        status["status"] = "unhealthy"
    
    return status

@app.get("/test-retrieval")
async def test_retrieval():
    """Test document retrieval without full workflow"""
    try:
        test_query = "test query"
        result = retriever_tool.invoke({"query": test_query})
        return {"success": True, "retrieved_docs": result}
    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
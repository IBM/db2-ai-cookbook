# RAG with IBM Db2 & Local LLMs in Red Hat Linux

[← Db2 AI Cookbook](../../README.md) · [← RAG module](../README.md)

A Retrieval-Augmented Generation (RAG) pipeline that answers questions by grounding responses in web content stored in **IBM Db2's vector database**. This project leverages **Db2's native vector search capabilities** and the **official LangChain-Db2 connector** for seamless integration with local LLM models.

## 🎯 Overview

This project combines several technologies to create an intelligent Q&A system that runs entirely on CPU:

**The Problem:** Large Language Models can hallucinate or provide outdated information.

**The Solution:** RAG grounds LLM responses in specific, retrieved documents.

### Why IBM Db2?

This project showcases **IBM Db2's powerful vector capabilities**:
- 🎯 **Native Vector Support**: Db2's built-in vector data type and similarity search
- 🔗 **Db2 LangChain Connector**: Seamless integration via `langchain-db2` package
- 🏢 **Enterprise-Grade**: Production-ready vector storage with ACID compliance

### Pipeline Architecture
```mermaid
graph TD
    A[🌐 Web Article URL] --> B[📥 Trafilatura<br/>Extract Content]
    B --> C[✂️ SpaCy Chunker<br/>200 words, 50 overlap]
    C --> D[🧠 Local Embedding Model<br/>Granite 30M]
    D --> E[💾 IBM Db2 Vector Store<br/>LangChain Connector<br/>EUCLIDEAN distance]
    
    F[❓ User Question] --> G[🔍 Embed Question<br/>Same model]
    G --> H[🎯 Db2 Similarity Search<br/>Top 3 chunks]
    E --> H
    
    H --> I[📝 Build Prompt<br/>Context + Question]
    I --> J[🤖 Local LLM<br/>Qwen2.5 3B]
    J --> K[✅ Grounded Answer<br/>+ Source Chunks]
    
    style A fill:#e1f5ff
    style F fill:#fff4e1
    style K fill:#e8f5e9
    style E fill:#f3e5f5
```

**Key Benefits:**

▸ Factual answers backed by source documents  
▸ Runs entirely on CPU (no GPU required)  
▸ Works offline with local models (no API costs)  
▸ **Enterprise vector storage with IBM Db2's native vector features**  
▸ **Seamless LangChain integration via official Db2 connector**  
▸ Full control over embedding and generation models

---

## 📦 Prerequisites

- Python 3.13+
- IBM Db2 12.1.2+
- ~4GB disk space for models
- 8GB+ RAM (32+ cores recommended for best performance)
- CPU-only (no GPU required)
- `uv` package manager ([install here](https://github.com/astral-sh/uv))

---

## ⚙️ Quick Setup

### 1. Start Db2
Using terminal or command prompt, start Db2:
```bash
db2start
```

### 2. Download Models

Using terminal or command prompt, navigate to the folder where you want to download the models:

e.g.,
```bash
cd /more_storage/models
```

**Embedding Model** (30M parameters, ~32MB):
```bash
wget -O granite-embedding-30m-english-Q6_K.gguf \
  https://huggingface.co/lmstudio-community/granite-embedding-30m-english-GGUF/resolve/main/granite-embedding-30m-english-Q6_K.gguf
```

**LLM Model** (3B parameters, ~2GB):
```bash
wget -O qwen2.5-3b-instruct-q4_k_m.gguf \
  https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf
```

### 3. Clone the Cookbook
```bash
git clone https://github.com/IBM/db2-ai-cookbook.git
```

Go to this recipe's directory — every path below is relative to it:
```bash
cd db2-ai-cookbook/03-rag/langchain-local-models
```

### 4. Environment & Dependencies
Create virtual environment:
```bash
uv venv --python $(which python3.13)
```

Install dependencies:
```bash
uv pip install -r requirements.txt
```

Install pip:
```bash
uv pip install pip
```

Download spaCy language model:
```bash
uv run python -m spacy download en_core_web_sm
```

### 5. Configure Environment

Create `.env` file in this recipe's folder:
```bash
touch .env
```

If using VS Code, open this recipe's folder using VS Code.

From that folder, add the following to `.env` (replace with your values):
```bash
# IBM Db2 Configuration
DB_NAME=your_database
DB_HOST=hostname.example.com
DB_PORT=50000
DB_PROTOCOL=TCPIP
DB_USER=your_username
DB_PASSWORD=your_password

# Model Paths (MUST be absolute paths)
LLM_PATH=/absolute/path/to/qwen2.5-3b-instruct-q4_k_m.gguf
EMBEDDING_MODEL_PATH=/absolute/path/to/granite-embedding-30m-english-Q6_K.gguf
```

## Usage

### Launch Jupyter
Make sure your virtual environment is activated:
```bash
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
```

Start Jupyter:
```bash
jupyter notebook rag-basic.ipynb
```

### Ask Questions

The notebook creates a `rag` chain that you can query:
```python
# Ask a question
result = rag.invoke('How to build a linear regression model in Db2?')

markdown_output = f"""
## 💡 Answer

{result['result']}

---

## 📚 Retrieved Context
"""

for i, doc in enumerate(result['source_documents'], 1):
    markdown_output += f"\n**📄 Chunk {i}**\n\n{doc.page_content}\n\n---\n"

display(Markdown(markdown_output))
```

**What happens under the hood:**
1. Question is embedded using local embedding model
2. Db2 finds 3 most similar chunks via vector search
3. Chunks are injected into prompt as context
4. Local LLM generates answer grounded in context
5. Returns both answer and source documents

---

## 🧩 Pipeline Components

| Step | Component | Configuration |
|------|-----------|---------------|
| **1. Web Scraping** | `trafilatura` | Fetches article from URL |
| **2. Text Chunking** | `spaCy` + custom chunker | 200 words/chunk, 50-word overlap |
| **3. Embeddings** | `LlamaCppEmbeddings` | Granite 30M, 16 threads |
| **4. Vector Store** | `DB2VS` | EUCLIDEAN distance strategy |
| **5. Retrieval** | `as_retriever()` | Top-3 similarity search |
| **6. LLM** | `LlamaCpp` | Qwen2.5-3B, 30 threads, CPU-only |
| **7. RAG Chain** | `RetrievalQA` | Combines retrieval + generation |


## 🖥️ Optional: VS Code + Jupyter Setup

If using VS Code with Jupyter:

1. **Select Interpreter:**
   - `Cmd+Shift+P` (Mac) or `Ctrl+Shift+P` (Win/Linux)
   - Type: **Python: Select Interpreter**
   - Select `.venv/bin/python`

2. **Select Jupyter Kernel:**
   - `Cmd+Shift+P` → **Jupyter: Select Interpreter to Start Jupyter Server**
   - Choose the same `.venv` Python

3. **If kernel doesn't appear:**
   - Run: `Developer: Reload Window`
   - Or restart VS Code

---

## 🗂️ Tech Stack

| Component | Purpose |
|-----------|---------|
| **LangChain** | RAG framework & orchestration |
| **IBM Db2** | Vector storage & similarity search |
| **llama.cpp** | Efficient local model inference |
| **spaCy** | Sentence segmentation for chunking |
| **trafilatura** | Web content extraction |
| **python-dotenv** | Environment variable management |
| **uv** | Fast Python package management |

---

## 📋 Recipe Layout

```
langchain-local-models/
├── rag-basic.ipynb          # Main notebook — the whole pipeline, with saved outputs
├── requirements.txt         # Python dependencies (pinned versions)
├── .env                     # Configuration (gitignored — DO NOT COMMIT)
└── README.md                # This file
```

The other RAG recipe, [haystack-local-models](../haystack-local-models/), covers the same
ground with a different stack: Haystack pipelines and Docling parsing over a PDF, as
Python scripts rather than a notebook.

---

## 🙏 Acknowledgments

- IBM Db2 team for native vector support and the Db2 connector
- llama.cpp for efficient CPU inference
- Qwen and IBM Granite model teams

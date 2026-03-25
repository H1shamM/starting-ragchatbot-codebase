# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Package Manager

Always use `uv` — never `pip` or `pip install` directly.

## Running the Application

```bash
# Install dependencies
uv sync

# Start the server (from repo root)
bash run.sh

# Or manually
cd backend && uv run uvicorn app:app --reload --port 8000
```

Requires a `.env` file in the repo root with `ANTHROPIC_API_KEY=...` (copy from `.env.example`).

- Web UI: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`

> On Windows, run these commands in Git Bash, not PowerShell or CMD.

## Architecture

This is a full-stack RAG (Retrieval-Augmented Generation) app. The backend is a single FastAPI process (`backend/app.py`) that serves both the API and the static frontend from `../frontend/`.

### Request Flow

1. Frontend (`frontend/script.js`) sends `POST /api/query` with `{query, session_id}`
2. `RAGSystem.query()` (`rag_system.py`) orchestrates the full pipeline
3. `AIGenerator` (`ai_generator.py`) calls Claude with tool-use enabled
4. Claude invokes the `CourseSearchTool` (`search_tools.py`) → `VectorStore.search()` runs semantic search against ChromaDB
5. Claude receives search results and generates a final response with citations
6. `(answer, sources)` returned to the frontend

### Key Relationships

- **`rag_system.py`** is the central coordinator — it holds references to `VectorStore`, `AIGenerator`, `DocumentProcessor`, and `SessionManager`
- **`ai_generator.py`** drives Claude's tool-calling loop; it calls back into `VectorStore` when Claude invokes the search tool
- **`vector_store.py`** maintains two ChromaDB collections: `course_catalog` (course metadata) and `course_content` (text chunks with embeddings)
- **`document_processor.py`** parses `.txt` course files by lesson markers (`Lesson N: Title`) and splits content into sentence-aware chunks

### Document Format

Course files in `docs/` must follow:
```
Course Title: ...
Course Link: ...
Course Instructor: ...

Lesson 0: Title
Lesson Link: ...
<content>

Lesson 1: Title
<content>
```

Documents are loaded at startup from `../docs/` (relative to `backend/`). ChromaDB is persisted to `backend/chroma_db/`.

### Configuration

All tunables are in `backend/config.py` as a single `Config` dataclass (imported as `config` singleton):

| Setting | Default | Purpose |
|---|---|---|
| `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | Claude model used |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformers model |
| `CHUNK_SIZE` | 800 | Max chars per chunk |
| `CHUNK_OVERLAP` | 100 | Overlap chars between chunks |
| `MAX_RESULTS` | 5 | Max semantic search results |
| `MAX_HISTORY` | 2 | Conversation turns remembered |
| `CHROMA_PATH` | `./chroma_db` | ChromaDB persistence path |

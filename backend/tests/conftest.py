import sys
import os
import pytest
from unittest.mock import MagicMock
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

# Add backend directory to path so test files can import backend modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

SAMPLE_ANSWER = "This course covers Python fundamentals."
SAMPLE_SOURCES = [
    {"text": "Test Course - Lesson 1", "url": "http://example.com/lesson/1"}
]
SAMPLE_SESSION_ID = "test-session-123"
SAMPLE_COURSES = {
    "total_courses": 2,
    "course_titles": ["Python Basics", "Advanced RAG"],
}


# ---------------------------------------------------------------------------
# Mock RAGSystem fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_rag():
    """A fully mocked RAGSystem instance."""
    rag = MagicMock()
    rag.query.return_value = (SAMPLE_ANSWER, SAMPLE_SOURCES)
    rag.session_manager.create_session.return_value = SAMPLE_SESSION_ID
    rag.get_course_analytics.return_value = SAMPLE_COURSES
    return rag


# ---------------------------------------------------------------------------
# Test FastAPI app (no static file mount)
# ---------------------------------------------------------------------------

def make_test_app(rag_system):
    """Build a minimal FastAPI app with the same API endpoints but no static files."""

    class QueryRequest(BaseModel):
        query: str
        session_id: Optional[str] = None

    class Source(BaseModel):
        text: str
        url: Optional[str] = None

    class QueryResponse(BaseModel):
        answer: str
        sources: List[Source]
        session_id: str

    class CourseStats(BaseModel):
        total_courses: int
        course_titles: List[str]

    app = FastAPI(title="Test RAG App")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.post("/api/query", response_model=QueryResponse)
    async def query_documents(request: QueryRequest):
        try:
            session_id = request.session_id or rag_system.session_manager.create_session()
            answer, sources = rag_system.query(request.query, session_id)
            return QueryResponse(answer=answer, sources=sources, session_id=session_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/courses", response_model=CourseStats)
    async def get_course_stats():
        try:
            analytics = rag_system.get_course_analytics()
            return CourseStats(
                total_courses=analytics["total_courses"],
                course_titles=analytics["course_titles"],
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.delete("/api/session/{session_id}")
    async def clear_session(session_id: str):
        rag_system.session_manager.clear_session(session_id)
        return {"status": "cleared"}

    return app


@pytest.fixture
def test_app(mock_rag):
    return make_test_app(mock_rag)


@pytest.fixture
def client(test_app):
    from starlette.testclient import TestClient
    return TestClient(test_app)
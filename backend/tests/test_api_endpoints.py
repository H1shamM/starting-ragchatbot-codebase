"""
API endpoint tests for the FastAPI RAG application.

Uses a test app defined in conftest.py (no static file mount) to avoid
file-system dependencies on the frontend/ directory.
"""
import pytest

# Expected values that mirror the mock_rag fixture in conftest.py
SAMPLE_ANSWER = "This course covers Python fundamentals."
SAMPLE_SOURCES = [{"text": "Test Course - Lesson 1", "url": "http://example.com/lesson/1"}]
SAMPLE_SESSION_ID = "test-session-123"
SAMPLE_COURSES = {"total_courses": 2, "course_titles": ["Python Basics", "Advanced RAG"]}


class TestQueryEndpoint:
    def test_post_query_returns_200(self, client):
        resp = client.post("/api/query", json={"query": "What is Python?"})
        assert resp.status_code == 200

    def test_post_query_response_has_expected_fields(self, client):
        data = client.post("/api/query", json={"query": "What is Python?"}).json()
        assert "answer" in data
        assert "sources" in data
        assert "session_id" in data

    def test_post_query_returns_mocked_answer(self, client):
        data = client.post("/api/query", json={"query": "What is Python?"}).json()
        assert data["answer"] == SAMPLE_ANSWER

    def test_post_query_uses_provided_session_id(self, client, mock_rag):
        resp = client.post("/api/query", json={"query": "test", "session_id": "my-session"})
        assert resp.json()["session_id"] == "my-session"
        mock_rag.session_manager.create_session.assert_not_called()

    def test_post_query_creates_session_when_none_provided(self, client, mock_rag):
        resp = client.post("/api/query", json={"query": "test"})
        assert resp.json()["session_id"] == SAMPLE_SESSION_ID
        mock_rag.session_manager.create_session.assert_called_once()

    def test_post_query_calls_rag_with_correct_args(self, client, mock_rag):
        client.post("/api/query", json={"query": "hello", "session_id": "s1"})
        mock_rag.query.assert_called_once_with("hello", "s1")

    def test_post_query_returns_500_on_rag_error(self, client, mock_rag):
        mock_rag.query.side_effect = RuntimeError("RAG failed")
        resp = client.post("/api/query", json={"query": "boom"})
        assert resp.status_code == 500

    def test_post_query_sources_structure(self, client):
        sources = client.post("/api/query", json={"query": "test"}).json()["sources"]
        assert isinstance(sources, list)
        assert sources[0]["text"] == SAMPLE_SOURCES[0]["text"]
        assert sources[0]["url"] == SAMPLE_SOURCES[0]["url"]

    def test_post_query_missing_query_field_returns_422(self, client):
        resp = client.post("/api/query", json={})
        assert resp.status_code == 422


class TestCoursesEndpoint:
    def test_get_courses_returns_200(self, client):
        assert client.get("/api/courses").status_code == 200

    def test_get_courses_response_has_expected_fields(self, client):
        data = client.get("/api/courses").json()
        assert "total_courses" in data
        assert "course_titles" in data

    def test_get_courses_returns_mocked_data(self, client):
        data = client.get("/api/courses").json()
        assert data["total_courses"] == SAMPLE_COURSES["total_courses"]
        assert data["course_titles"] == SAMPLE_COURSES["course_titles"]

    def test_get_courses_returns_500_on_error(self, client, mock_rag):
        mock_rag.get_course_analytics.side_effect = RuntimeError("DB error")
        assert client.get("/api/courses").status_code == 500


class TestSessionEndpoint:
    def test_delete_session_returns_200(self, client):
        assert client.delete("/api/session/abc123").status_code == 200

    def test_delete_session_returns_cleared_status(self, client):
        assert client.delete("/api/session/abc123").json() == {"status": "cleared"}

    def test_delete_session_calls_clear_with_correct_id(self, client, mock_rag):
        client.delete("/api/session/my-session-id")
        mock_rag.session_manager.clear_session.assert_called_once_with("my-session-id")

"""
Tests for the RAG system pipeline, focused on content-query failures.

These tests expose the root cause of 'query failed' errors for content questions:
  - config.MAX_RESULTS is 0, causing ChromaDB to raise ValueError on every search
  - The error propagates as a tool result that Claude receives instead of content
"""

import pytest
from unittest.mock import MagicMock, patch

import chromadb
from chromadb.config import Settings

from config import Config
from vector_store import VectorStore, SearchResults
from search_tools import CourseSearchTool, ToolManager
from models import Course, Lesson, CourseChunk

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ephemeral_vector_store(max_results=5):
    """Return a VectorStore backed by an ephemeral (in-memory) ChromaDB."""
    client = chromadb.EphemeralClient(settings=Settings(anonymized_telemetry=False))

    store = VectorStore.__new__(VectorStore)
    store.max_results = max_results
    store.client = client

    import chromadb.utils.embedding_functions as ef

    store.embedding_function = ef.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    store.course_catalog = store._create_collection("course_catalog")
    store.course_content = store._create_collection("course_content")
    return store


def _seed_store(store):
    """Add one minimal course + one content chunk to the store."""
    course = Course(
        title="Test Course",
        course_link="http://example.com/course",
        instructor="Tester",
        lessons=[
            Lesson(
                lesson_number=1,
                title="Introduction",
                lesson_link="http://example.com/lesson/1",
            )
        ],
    )
    chunk = CourseChunk(
        content="Lesson 1 content: This is an introduction to testing.",
        course_title="Test Course",
        lesson_number=1,
        chunk_index=0,
    )
    store.add_course_metadata(course)
    store.add_course_content([chunk])
    return course, chunk


# ---------------------------------------------------------------------------
# 1. Configuration bug
# ---------------------------------------------------------------------------


class TestConfigBug:
    def test_max_results_is_positive(self):
        """
        FAILS when the bug is present: MAX_RESULTS=0 causes every ChromaDB
        query to raise 'n_results must be a positive integer', which means
        the search tool always returns an error string instead of content.
        """
        cfg = Config()
        assert cfg.MAX_RESULTS > 0, (
            f"BUG: config.MAX_RESULTS = {cfg.MAX_RESULTS}. "
            "ChromaDB requires n_results >= 1. "
            "Fix: set MAX_RESULTS to a positive integer (e.g. 5)."
        )


# ---------------------------------------------------------------------------
# 2. VectorStore – ChromaDB rejects n_results=0
# ---------------------------------------------------------------------------


class TestVectorStoreSearchWithZeroResults:
    def test_chromadb_raises_on_n_results_zero(self):
        """
        ChromaDB itself raises an exception when n_results=0.
        This confirms the mechanism by which MAX_RESULTS=0 breaks searches.
        """
        client = chromadb.EphemeralClient(settings=Settings(anonymized_telemetry=False))
        col = client.create_collection("test_zero")
        col.add(documents=["hello"], ids=["doc1"])

        with pytest.raises(
            Exception, match="(?i)(n_results|requested results|zero|negative)"
        ):
            col.query(query_texts=["hello"], n_results=0)

    def test_vector_store_search_returns_error_when_max_results_zero(self):
        """
        VectorStore.search() catches the ChromaDB exception and returns a
        SearchResults with an error message when max_results=0.
        """
        store = _make_ephemeral_vector_store(max_results=0)
        _seed_store(store)

        results = store.search(query="introduction")

        assert (
            results.error is not None
        ), "Expected an error in SearchResults when max_results=0, got none."
        assert results.is_empty()

    def test_vector_store_search_succeeds_when_max_results_positive(self):
        """
        The same search returns actual results when max_results is a positive integer.
        This is the expected state after fixing MAX_RESULTS in config.py.
        """
        store = _make_ephemeral_vector_store(max_results=5)
        _seed_store(store)

        results = store.search(query="introduction to testing")

        assert results.error is None, f"Unexpected error: {results.error}"
        assert not results.is_empty(), "Expected at least one result."


# ---------------------------------------------------------------------------
# 3. CourseSearchTool – search error string propagates
# ---------------------------------------------------------------------------


class TestCourseSearchToolWithRealStore:
    def test_execute_returns_error_string_when_max_results_zero(self):
        """
        CourseSearchTool.execute() returns the raw error string from the store
        when max_results=0. Claude receives this instead of course content.
        """
        store = _make_ephemeral_vector_store(max_results=0)
        _seed_store(store)

        tool = CourseSearchTool(store)
        result = tool.execute(query="introduction")

        assert (
            "error" in result.lower() or "n_results" in result.lower()
        ), f"Expected an error message, got: {result!r}"

    def test_execute_returns_content_when_max_results_positive(self):
        """
        CourseSearchTool.execute() returns actual content when max_results > 0.
        """
        store = _make_ephemeral_vector_store(max_results=5)
        _seed_store(store)

        tool = CourseSearchTool(store)
        result = tool.execute(query="introduction to testing")

        assert (
            "Test Course" in result or "introduction" in result.lower()
        ), f"Expected course content in result, got: {result!r}"


# ---------------------------------------------------------------------------
# 4. RAGSystem pipeline – end-to-end with mocked AI
# ---------------------------------------------------------------------------


class TestRAGSystemPipeline:
    """
    Full pipeline tests using a real (ephemeral) VectorStore and mocked AI.
    These isolate whether the pipeline wires components together correctly.
    """

    @pytest.fixture
    def store(self):
        s = _make_ephemeral_vector_store(max_results=5)
        _seed_store(s)
        return s

    @pytest.fixture
    def tool_manager(self, store):
        manager = ToolManager()
        manager.register_tool(CourseSearchTool(store))
        return manager

    def test_search_tool_returns_content_and_sources(self, store, tool_manager):
        """
        The search tool returns content and populates sources for the UI.
        Verifies the pipeline from ToolManager.execute_tool → sources.
        """
        result = tool_manager.execute_tool(
            "search_course_content", query="introduction to testing"
        )

        assert "Test Course" in result or "introduction" in result.lower()
        sources = tool_manager.get_last_sources()
        assert len(sources) >= 1
        assert sources[0]["text"].startswith("Test Course")

    def test_rag_query_with_mocked_ai(self, store):
        """
        Full RAGSystem.query() succeeds with working MAX_RESULTS and mocked AI.
        """
        import tempfile
        from rag_system import RAGSystem

        with (
            patch("ai_generator.anthropic.Anthropic") as mock_anthropic_class,
            tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_chroma,
        ):

            mock_client = MagicMock()
            mock_anthropic_class.return_value = mock_client

            # Simulate: AI decides to call the search tool
            tool_use_block = MagicMock()
            tool_use_block.type = "tool_use"
            tool_use_block.name = "search_course_content"
            tool_use_block.id = "tool_123"
            tool_use_block.input = {"query": "introduction to testing"}

            initial_response = MagicMock()
            initial_response.stop_reason = "tool_use"
            initial_response.content = [tool_use_block]

            final_block = MagicMock()
            final_block.type = "text"
            final_block.text = "Lesson 1 introduces testing concepts."

            final_response = MagicMock()
            final_response.stop_reason = "end_turn"
            final_response.content = [final_block]

            mock_client.messages.create.side_effect = [initial_response, final_response]

            # Build RAGSystem with working config and a real temp path for ChromaDB
            cfg = MagicMock()
            cfg.ANTHROPIC_API_KEY = "test-key"
            cfg.ANTHROPIC_MODEL = "claude-test"
            cfg.EMBEDDING_MODEL = "all-MiniLM-L6-v2"
            cfg.CHUNK_SIZE = 800
            cfg.CHUNK_OVERLAP = 100
            cfg.MAX_RESULTS = 5
            cfg.MAX_HISTORY = 2
            cfg.CHROMA_PATH = tmp_chroma

            rag = RAGSystem(cfg)
            # Replace the VectorStore with our seeded ephemeral one
            rag.vector_store = store
            rag.search_tool.store = store
            rag.outline_tool.store = store

            answer, sources = rag.query("What is in lesson 1?")

        assert answer == "Lesson 1 introduces testing concepts."
        # Sources come from the search tool's last_sources
        assert isinstance(sources, list)

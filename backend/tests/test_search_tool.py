"""
Tests for CourseSearchTool.execute() in search_tools.py
"""
import pytest
from unittest.mock import MagicMock

from search_tools import CourseSearchTool, ToolManager
from vector_store import SearchResults


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_results(documents, metadata, error=None):
    if error:
        return SearchResults.empty(error)
    return SearchResults(
        documents=documents,
        metadata=metadata,
        distances=[0.5] * len(documents)
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_store():
    store = MagicMock()
    store.get_lesson_link.return_value = "http://example.com/lesson/1"
    return store


@pytest.fixture
def tool(mock_store):
    return CourseSearchTool(mock_store)


# ---------------------------------------------------------------------------
# execute() – success path
# ---------------------------------------------------------------------------

class TestExecuteSuccess:
    def test_returns_formatted_content(self, tool, mock_store):
        """Results are formatted with course title, lesson number, and text."""
        mock_store.search.return_value = make_results(
            documents=["Python is great."],
            metadata=[{"course_title": "Intro to Python", "lesson_number": 1}]
        )

        result = tool.execute(query="What is Python?")

        assert "Intro to Python" in result
        assert "Lesson 1" in result
        assert "Python is great." in result

    def test_populates_last_sources(self, tool, mock_store):
        """last_sources is populated with text and url after a successful search."""
        mock_store.search.return_value = make_results(
            documents=["Content."],
            metadata=[{"course_title": "MCP Course", "lesson_number": 3}]
        )
        mock_store.get_lesson_link.return_value = "http://example.com/lesson/3"

        tool.execute(query="MCP tools")

        assert len(tool.last_sources) == 1
        assert tool.last_sources[0]["text"] == "MCP Course - Lesson 3"
        assert tool.last_sources[0]["url"] == "http://example.com/lesson/3"

    def test_source_omits_lesson_when_none(self, tool, mock_store):
        """Source text has no lesson suffix when lesson_number is None."""
        mock_store.search.return_value = make_results(
            documents=["General content."],
            metadata=[{"course_title": "General Course", "lesson_number": None}]
        )

        tool.execute(query="general stuff")

        assert tool.last_sources[0]["text"] == "General Course"
        assert tool.last_sources[0]["url"] is None

    def test_multiple_results_all_formatted(self, tool, mock_store):
        """Multiple result chunks are all included in the formatted output."""
        mock_store.search.return_value = make_results(
            documents=["Chunk A.", "Chunk B."],
            metadata=[
                {"course_title": "Course X", "lesson_number": 1},
                {"course_title": "Course X", "lesson_number": 2},
            ]
        )

        result = tool.execute(query="overview")

        assert "Chunk A." in result
        assert "Chunk B." in result
        assert len(tool.last_sources) == 2


# ---------------------------------------------------------------------------
# execute() – filter forwarding
# ---------------------------------------------------------------------------

class TestExecuteFilters:
    def test_passes_query_only(self, tool, mock_store):
        mock_store.search.return_value = make_results([], [])
        tool.execute(query="hello")
        mock_store.search.assert_called_once_with(
            query="hello", course_name=None, lesson_number=None
        )

    def test_passes_course_name(self, tool, mock_store):
        mock_store.search.return_value = make_results([], [])
        tool.execute(query="hello", course_name="Intro Python")
        mock_store.search.assert_called_once_with(
            query="hello", course_name="Intro Python", lesson_number=None
        )

    def test_passes_lesson_number(self, tool, mock_store):
        mock_store.search.return_value = make_results([], [])
        tool.execute(query="hello", lesson_number=2)
        mock_store.search.assert_called_once_with(
            query="hello", course_name=None, lesson_number=2
        )

    def test_passes_both_filters(self, tool, mock_store):
        mock_store.search.return_value = make_results([], [])
        tool.execute(query="hello", course_name="MCP", lesson_number=5)
        mock_store.search.assert_called_once_with(
            query="hello", course_name="MCP", lesson_number=5
        )


# ---------------------------------------------------------------------------
# execute() – empty / error paths
# ---------------------------------------------------------------------------

class TestExecuteEmptyAndErrors:
    def test_empty_results_returns_no_content_message(self, tool, mock_store):
        """Returns 'No relevant content found' when search returns no documents."""
        mock_store.search.return_value = make_results([], [])

        result = tool.execute(query="nonexistent topic")

        assert "No relevant content found" in result

    def test_empty_results_includes_course_filter_in_message(self, tool, mock_store):
        """'No relevant content found' message includes the course name filter."""
        mock_store.search.return_value = make_results([], [])

        result = tool.execute(query="something", course_name="MCP Course")

        assert "No relevant content found" in result
        assert "MCP Course" in result

    def test_empty_results_includes_lesson_filter_in_message(self, tool, mock_store):
        """'No relevant content found' message includes the lesson number filter."""
        mock_store.search.return_value = make_results([], [])

        result = tool.execute(query="something", lesson_number=4)

        assert "No relevant content found" in result
        assert "4" in result

    def test_store_search_error_is_returned(self, tool, mock_store):
        """When store.search() returns an error, execute() returns it directly."""
        mock_store.search.return_value = make_results(
            [], [], error="Search error: n_results must be a positive integer."
        )

        result = tool.execute(query="What is Python?")

        assert "Search error" in result

    def test_course_not_found_error_is_returned(self, tool, mock_store):
        """When course_name matches nothing, the error from the store is returned."""
        mock_store.search.return_value = SearchResults.empty(
            "No course found matching 'Ghost Course'"
        )

        result = tool.execute(query="anything", course_name="Ghost Course")

        assert "No course found" in result
        assert "Ghost Course" in result

    def test_last_sources_empty_after_error(self, tool, mock_store):
        """last_sources is not populated when search returns an error."""
        mock_store.search.return_value = make_results(
            [], [], error="Search error: something went wrong."
        )

        tool.execute(query="anything")

        assert tool.last_sources == []


# ---------------------------------------------------------------------------
# ToolManager integration
# ---------------------------------------------------------------------------

class TestToolManager:
    def test_register_and_execute_search_tool(self, mock_store):
        mock_store.search.return_value = make_results(
            documents=["Result."],
            metadata=[{"course_title": "Course A", "lesson_number": 1}]
        )

        manager = ToolManager()
        search_tool = CourseSearchTool(mock_store)
        manager.register_tool(search_tool)

        result = manager.execute_tool("search_course_content", query="test")

        assert "Result." in result
        assert "Course A" in result

    def test_get_last_sources_via_manager(self, mock_store):
        mock_store.search.return_value = make_results(
            documents=["Text."],
            metadata=[{"course_title": "Course B", "lesson_number": 2}]
        )

        manager = ToolManager()
        search_tool = CourseSearchTool(mock_store)
        manager.register_tool(search_tool)
        manager.execute_tool("search_course_content", query="test")

        sources = manager.get_last_sources()

        assert len(sources) == 1
        assert sources[0]["text"] == "Course B - Lesson 2"

    def test_reset_sources_clears_last_sources(self, mock_store):
        mock_store.search.return_value = make_results(
            documents=["Text."],
            metadata=[{"course_title": "Course B", "lesson_number": 2}]
        )

        manager = ToolManager()
        search_tool = CourseSearchTool(mock_store)
        manager.register_tool(search_tool)
        manager.execute_tool("search_course_content", query="test")
        manager.reset_sources()

        assert manager.get_last_sources() == []

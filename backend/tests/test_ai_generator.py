"""
Tests for AIGenerator – verifies that Claude is called correctly and that the
sequential tool-calling loop (up to MAX_TOOL_ROUNDS rounds) works as expected.
"""
import pytest
from unittest.mock import MagicMock, patch

from ai_generator import AIGenerator


# ---------------------------------------------------------------------------
# Helpers – lightweight stand-ins for Anthropic SDK response objects
# ---------------------------------------------------------------------------

class _Block:
    """Minimal content block."""
    def __init__(self, type, *, text=None, name=None, id=None, input=None):
        self.type = type
        self.text = text
        self.name = name
        self.id = id
        self.input = input or {}


class _Response:
    def __init__(self, stop_reason, content):
        self.stop_reason = stop_reason
        self.content = content


def _text_response(text):
    return _Response("end_turn", [_Block("text", text=text)])


def _tool_response(name, tool_id, inputs):
    return _Response("tool_use", [_Block("tool_use", name=name, id=tool_id, input=inputs)])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_client():
    """Patch anthropic.Anthropic so no real HTTP calls are made."""
    with patch("ai_generator.anthropic.Anthropic") as mock_class:
        client = MagicMock()
        mock_class.return_value = client
        yield client


@pytest.fixture
def gen(mock_client):
    return AIGenerator(api_key="test-key", model="claude-test")


# ---------------------------------------------------------------------------
# Direct (no tool) responses
# ---------------------------------------------------------------------------

class TestDirectResponse:
    def test_returns_text_on_end_turn(self, gen, mock_client):
        mock_client.messages.create.return_value = _text_response("42")

        result = gen.generate_response(query="What is 6×7?")

        assert result == "42"

    def test_does_not_include_tools_param_when_none_given(self, gen, mock_client):
        mock_client.messages.create.return_value = _text_response("ok")

        gen.generate_response(query="hello")

        kwargs = mock_client.messages.create.call_args.kwargs
        assert "tools" not in kwargs
        assert "tool_choice" not in kwargs

    def test_system_prompt_is_included(self, gen, mock_client):
        mock_client.messages.create.return_value = _text_response("ok")

        gen.generate_response(query="hello")

        kwargs = mock_client.messages.create.call_args.kwargs
        assert "system" in kwargs
        assert len(kwargs["system"]) > 0

    def test_conversation_history_appended_to_system(self, gen, mock_client):
        mock_client.messages.create.return_value = _text_response("ok")

        gen.generate_response(query="hello", conversation_history="User: hi\nAssistant: hello")

        kwargs = mock_client.messages.create.call_args.kwargs
        assert "Previous conversation" in kwargs["system"]
        assert "User: hi" in kwargs["system"]


# ---------------------------------------------------------------------------
# Single tool-calling round (existing behavior preserved)
# ---------------------------------------------------------------------------

class TestToolCallingLoop:
    def test_tool_use_triggers_tool_manager(self, gen, mock_client):
        """When stop_reason is tool_use, tool_manager.execute_tool is called."""
        mock_client.messages.create.side_effect = [
            _tool_response("search_course_content", "tid1", {"query": "RAG"}),
            _text_response("Here is the answer."),
        ]
        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = "Some search result."

        result = gen.generate_response(
            query="Tell me about RAG",
            tools=[{"name": "search_course_content"}],
            tool_manager=tool_manager,
        )

        tool_manager.execute_tool.assert_called_once_with(
            "search_course_content", query="RAG"
        )
        assert result == "Here is the answer."

    def test_two_api_calls_are_made(self, gen, mock_client):
        """Single tool-use round makes exactly two calls to the Anthropic API."""
        mock_client.messages.create.side_effect = [
            _tool_response("search_course_content", "tid2", {"query": "MCP"}),
            _text_response("Final answer."),
        ]
        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = "Result."

        gen.generate_response(
            query="What is MCP?",
            tools=[{"name": "search_course_content"}],
            tool_manager=tool_manager,
        )

        assert mock_client.messages.create.call_count == 2

    def test_tool_result_sent_back_in_second_call(self, gen, mock_client):
        """The tool execution result is included as a tool_result message in the second API call."""
        mock_client.messages.create.side_effect = [
            _tool_response("search_course_content", "abc123", {"query": "embeddings"}),
            _text_response("Done."),
        ]
        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = "Embeddings are vector representations."

        gen.generate_response(
            query="Explain embeddings",
            tools=[{"name": "search_course_content"}],
            tool_manager=tool_manager,
        )

        second_call_kwargs = mock_client.messages.create.call_args_list[1].kwargs
        messages = second_call_kwargs["messages"]

        tool_result_msgs = [
            m for m in messages
            if m["role"] == "user" and isinstance(m["content"], list)
        ]
        assert len(tool_result_msgs) == 1
        tool_result_content = tool_result_msgs[0]["content"][0]
        assert tool_result_content["type"] == "tool_result"
        assert tool_result_content["tool_use_id"] == "abc123"
        assert tool_result_content["content"] == "Embeddings are vector representations."

    def test_round_2_call_includes_tools(self, gen, mock_client):
        """The follow-up call after a tool round still has tools available."""
        mock_client.messages.create.side_effect = [
            _tool_response("search_course_content", "tid3", {"query": "test"}),
            _text_response("Answer."),
        ]
        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = "Result."

        gen.generate_response(
            query="test",
            tools=[{"name": "search_course_content"}],
            tool_manager=tool_manager,
        )

        second_call_kwargs = mock_client.messages.create.call_args_list[1].kwargs
        assert "tools" in second_call_kwargs

    def test_no_tool_manager_means_no_tool_execution(self, gen, mock_client):
        """
        If tool_manager is None and stop_reason is tool_use, the code falls through
        to `return response.content[0].text`.  With the real Anthropic SDK a tool_use
        block has no .text attribute, so this raises AttributeError in production.
        In this test the mock's .text is None, so the function returns None instead —
        either way the caller gets a broken response (None or an exception).
        """
        tool_block = _Block("tool_use", name="search_course_content", id="t1", input={"query": "x"})
        mock_client.messages.create.return_value = _Response(
            "tool_use", [tool_block]
        )

        result = gen.generate_response(
            query="test",
            tools=[{"name": "search_course_content"}],
            tool_manager=None,   # intentionally None
        )

        # Mock returns None (real SDK raises AttributeError); either way the response is broken.
        assert result is None, (
            "Expected None when tool_manager is None and stop_reason is tool_use. "
            "The real Anthropic SDK would raise AttributeError here."
        )

    def test_tool_choice_auto_set_when_tools_provided(self, gen, mock_client):
        """tool_choice is set to auto when tools are provided."""
        mock_client.messages.create.return_value = _text_response("ok")

        gen.generate_response(
            query="test",
            tools=[{"name": "search_course_content"}],
            tool_manager=MagicMock(),
        )

        first_call_kwargs = mock_client.messages.create.call_args_list[0].kwargs
        assert first_call_kwargs.get("tool_choice") == {"type": "auto"}


# ---------------------------------------------------------------------------
# Search tool error propagation
# ---------------------------------------------------------------------------

class TestSearchErrorPropagation:
    def test_search_error_string_reaches_ai(self, gen, mock_client):
        """When search returns an error string, it is sent back to Claude as the tool result."""
        mock_client.messages.create.side_effect = [
            _tool_response("search_course_content", "err_id", {"query": "test"}),
            _text_response("I could not find that content."),
        ]
        tool_manager = MagicMock()
        # Simulate the error that MAX_RESULTS=0 produces
        tool_manager.execute_tool.return_value = (
            "Search error: n_results must be a positive integer."
        )

        result = gen.generate_response(
            query="Tell me about lesson 1",
            tools=[{"name": "search_course_content"}],
            tool_manager=tool_manager,
        )

        # The AI should still return a (degraded) response
        assert isinstance(result, str)
        assert len(result) > 0

        # Verify the error was forwarded as tool result content
        second_call_kwargs = mock_client.messages.create.call_args_list[1].kwargs
        messages = second_call_kwargs["messages"]
        tool_result_msgs = [
            m for m in messages
            if m["role"] == "user" and isinstance(m["content"], list)
        ]
        assert "Search error" in tool_result_msgs[0]["content"][0]["content"]


# ---------------------------------------------------------------------------
# Sequential tool calling (multi-round)
# ---------------------------------------------------------------------------

class TestSequentialToolCalling:
    def test_max_tool_rounds_constant_is_two(self, gen):
        assert AIGenerator.MAX_TOOL_ROUNDS == 2

    def test_two_rounds_executes_both_tools(self, gen, mock_client):
        """Two sequential tool-use rounds each trigger execute_tool; returns final text."""
        mock_client.messages.create.side_effect = [
            _tool_response("get_course_outline", "t1", {"course_title": "Course X"}),
            _tool_response("search_course_content", "t2", {"query": "lesson 4 topic"}),
            _text_response("Here is the combined answer."),
        ]
        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = "Some result."

        result = gen.generate_response(
            query="Find a course covering the same topic as lesson 4 of Course X",
            tools=[{"name": "get_course_outline"}, {"name": "search_course_content"}],
            tool_manager=tool_manager,
        )

        assert tool_manager.execute_tool.call_count == 2
        assert result == "Here is the combined answer."

    def test_three_api_calls_on_two_rounds(self, gen, mock_client):
        """Two tool rounds + one synthesis call = exactly 3 API calls."""
        mock_client.messages.create.side_effect = [
            _tool_response("get_course_outline", "t1", {"course_title": "Course X"}),
            _tool_response("search_course_content", "t2", {"query": "lesson 4 topic"}),
            _text_response("Final answer."),
        ]
        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = "Result."

        gen.generate_response(
            query="test",
            tools=[{"name": "get_course_outline"}, {"name": "search_course_content"}],
            tool_manager=tool_manager,
        )

        assert mock_client.messages.create.call_count == 3

    def test_early_exit_when_no_tool_use_in_round_2(self, gen, mock_client):
        """If Claude returns a text response in round 2, return it without a synthesis call."""
        mock_client.messages.create.side_effect = [
            _tool_response("search_course_content", "t1", {"query": "topic"}),
            _text_response("Done after one round."),
        ]
        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = "Result."

        result = gen.generate_response(
            query="test",
            tools=[{"name": "search_course_content"}],
            tool_manager=tool_manager,
        )

        assert mock_client.messages.create.call_count == 2
        assert result == "Done after one round."

    def test_synthesis_call_omits_tools(self, gen, mock_client):
        """After two tool rounds the final synthesis call has no tools."""
        mock_client.messages.create.side_effect = [
            _tool_response("get_course_outline", "t1", {"course_title": "Course X"}),
            _tool_response("search_course_content", "t2", {"query": "topic"}),
            _text_response("Synthesis answer."),
        ]
        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = "Result."

        gen.generate_response(
            query="test",
            tools=[{"name": "get_course_outline"}, {"name": "search_course_content"}],
            tool_manager=tool_manager,
        )

        third_call_kwargs = mock_client.messages.create.call_args_list[2].kwargs
        assert "tools" not in third_call_kwargs
        assert "tool_choice" not in third_call_kwargs

    def test_round_2_call_includes_tools(self, gen, mock_client):
        """Intermediate round calls keep tools available."""
        mock_client.messages.create.side_effect = [
            _tool_response("get_course_outline", "t1", {"course_title": "Course X"}),
            _tool_response("search_course_content", "t2", {"query": "topic"}),
            _text_response("Answer."),
        ]
        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = "Result."

        gen.generate_response(
            query="test",
            tools=[{"name": "get_course_outline"}, {"name": "search_course_content"}],
            tool_manager=tool_manager,
        )

        second_call_kwargs = mock_client.messages.create.call_args_list[1].kwargs
        assert "tools" in second_call_kwargs

    def test_tool_exception_returns_string(self, gen, mock_client):
        """An unexpected exception from execute_tool is caught; method returns a string."""
        mock_client.messages.create.side_effect = [
            _tool_response("search_course_content", "t1", {"query": "test"}),
            _text_response("Graceful degraded response."),
        ]
        tool_manager = MagicMock()
        tool_manager.execute_tool.side_effect = RuntimeError("db offline")

        result = gen.generate_response(
            query="test",
            tools=[{"name": "search_course_content"}],
            tool_manager=tool_manager,
        )

        assert isinstance(result, str)
        assert len(result) > 0

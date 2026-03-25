import anthropic
from typing import List, Optional

class AIGenerator:
    """Handles interactions with Anthropic's Claude API for generating responses"""

    # Static system prompt to avoid rebuilding on each call
    SYSTEM_PROMPT = """ You are an AI assistant specialized in course materials and educational content with access to a comprehensive search tool for course information.

Search Tool Usage:
- Use the search tool **only** for questions about specific course content or detailed educational materials
- Use get_course_outline for questions about course structure, syllabus, or lesson list
- When responding to outline queries, include: course title, course link, and all lesson numbers with their titles
- **Up to two sequential searches per query** — use a second search only when the first result is insufficient to fully answer the question
- Synthesize search results into accurate, fact-based responses
- If search yields no results, state this clearly without offering alternatives

Response Protocol:
- **General knowledge questions**: Answer using existing knowledge without searching
- **Course-specific questions**: Search first, then answer
- **No meta-commentary**:
 - Provide direct answers only — no reasoning process, search explanations, or question-type analysis
 - Do not mention "based on the search results"


All responses must be:
1. **Brief, Concise and focused** - Get to the point quickly
2. **Educational** - Maintain instructional value
3. **Clear** - Use accessible language
4. **Example-supported** - Include relevant examples when they aid understanding
Provide only the direct answer to what was asked.
"""

    MAX_TOOL_ROUNDS = 2

    def __init__(self, api_key: str, model: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

        # Pre-build base API parameters
        self.base_params = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 800
        }

    def generate_response(self, query: str,
                         conversation_history: Optional[str] = None,
                         tools: Optional[List] = None,
                         tool_manager=None) -> str:
        """
        Generate AI response with optional tool usage and conversation context.

        Args:
            query: The user's question or request
            conversation_history: Previous messages for context
            tools: Available tools the AI can use
            tool_manager: Manager to execute tools

        Returns:
            Generated response as string
        """

        # Build system content efficiently - avoid string ops when possible
        system_content = (
            f"{self.SYSTEM_PROMPT}\n\nPrevious conversation:\n{conversation_history}"
            if conversation_history
            else self.SYSTEM_PROMPT
        )

        messages = [{"role": "user", "content": query}]

        # Prepare API call parameters
        api_params = {
            **self.base_params,
            "messages": messages,
            "system": system_content
        }

        # Add tools if available
        if tools:
            api_params["tools"] = tools
            api_params["tool_choice"] = {"type": "auto"}

        # Tool-calling loop: up to MAX_TOOL_ROUNDS sequential rounds
        for _ in range(self.MAX_TOOL_ROUNDS):
            response = self.client.messages.create(**api_params)

            # Termination (b): no tool_use — return the text response directly
            if response.stop_reason != "tool_use":
                return response.content[0].text

            # Termination (graceful): tools requested but no manager to execute them
            if not tool_manager:
                return response.content[0].text

            # Append assistant's tool-use turn to the growing messages list
            messages.append({"role": "assistant", "content": response.content})

            # Execute all tool calls and collect results
            tool_results = []
            tool_error = False
            for content_block in response.content:
                if content_block.type == "tool_use":
                    try:
                        result = tool_manager.execute_tool(
                            content_block.name,
                            **content_block.input
                        )
                    except Exception as e:
                        result = f"Tool error: {str(e)}"
                        tool_error = True

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": content_block.id,
                        "content": result
                    })

            messages.append({"role": "user", "content": tool_results})
            api_params["messages"] = messages

            # Termination (c): tool execution failed — exit loop, synthesize with error context
            if tool_error:
                break

        # Termination (a): rounds exhausted (or tool error broke the loop).
        # Make one final synthesis call without tools to force a text answer.
        final_params = {
            **self.base_params,
            "messages": messages,
            "system": system_content
        }
        final_response = self.client.messages.create(**final_params)
        return final_response.content[0].text

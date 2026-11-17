from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from backend.app.ai.llm.gemini_provider import GeminiProvider
from backend.app.ai.llm.schemas import LLMMessage, ToolDefinition
from backend.app.ai.tools.contracts import ToolCall


@pytest.mark.asyncio
async def test_gemini_generate_with_tools_groups_consecutive_tool_responses():
    """Verify that multiple consecutive tool response messages are grouped into

    a single types.Content(role='user', parts=[...]) rather than creating
    multiple consecutive user Content objects, which causes Gemini HTTP 400 Bad Request.
    """
    provider = GeminiProvider(api_key="fake-key", model="gemini-2.5-flash", temperature=0.2, max_tokens=1024)

    mock_client = MagicMock()
    mock_aio = MagicMock()
    mock_client.aio = mock_aio
    mock_response = MagicMock()
    mock_response.candidates = []
    mock_response.usage_metadata = MagicMock(
        prompt_token_count=10,
        candidates_token_count=5,
        total_token_count=15,
        cached_content_token_count=0,
    )
    mock_aio.models.generate_content = AsyncMock(return_value=mock_response)

    messages = [
        LLMMessage(role="user", content="Quel est le prix et le stock ?"),
        LLMMessage(
            role="assistant",
            content="",
            tool_calls=[
                ToolCall(id="call_1", name="get_product_price", arguments={"item": "snowboard"}),
                ToolCall(id="call_2", name="get_product_stock", arguments={"item": "snowboard"}),
            ],
        ),
        LLMMessage(role="tool", name="get_product_price", content='{"price": 499.99}'),
        LLMMessage(role="tool", name="get_product_stock", content='{"stock": 12}'),
    ]

    tools = [
        ToolDefinition(name="get_product_price", description="Get price", parameters_schema={"type": "object"}),
        ToolDefinition(name="get_product_stock", description="Get stock", parameters_schema={"type": "object"}),
    ]

    with patch.object(provider, "_async_client", AsyncMock(return_value=mock_client)):
        await provider.generate_with_tools(
            system_instruction="System prompt",
            messages=messages,
            tools=tools,
        )

    # Inspect contents passed to generate_content
    call_kwargs = mock_aio.models.generate_content.call_args.kwargs
    contents = call_kwargs["contents"]

    # Must have exactly 3 turns:
    # Turn 0: user text
    # Turn 1: model tool calls (2 parts)
    # Turn 2: user tool responses (grouped into 1 Content with 2 parts!)
    assert len(contents) == 3, f"Expected 3 turns, got {len(contents)}"
    assert contents[0].role == "user"
    assert contents[1].role == "model"
    assert contents[2].role == "user"
    assert len(contents[2].parts) == 2, f"Expected 2 parts in tool response Content, got {len(contents[2].parts)}"

from types import SimpleNamespace
from decimal import Decimal
import inspect
from unittest.mock import AsyncMock
import pytest

from backend.app.ai.llm.anthropic_provider import _normalize_anthropic_usage
from backend.app.ai.llm.gemini_provider import _normalize_gemini_usage
from backend.app.ai.llm.openai_provider import _normalize_openai_usage
from backend.app.ai.llm.model_registry import LLMRateCard
from backend.app.ai.llm.schemas import LLMUsage
from backend.app.ai.llm.schemas import LLMMessage, ToolDefinition
from backend.app.ai.llm.anthropic_provider import AnthropicProvider


def test_openai_usage_normalization() -> None:
    response = SimpleNamespace(
        id="chatcmpl-123",
        model="gpt-4o-mini-2024-07-18",
        usage=SimpleNamespace(
            prompt_tokens=120,
            completion_tokens=30,
            prompt_tokens_details=SimpleNamespace(cached_tokens=20),
            completion_tokens_details=SimpleNamespace(reasoning_tokens=8),
        ),
    )

    usage = _normalize_openai_usage(response, "gpt-4o-mini", tool_calls=2)

    assert usage.provider == "openai"
    assert usage.model == "gpt-4o-mini-2024-07-18"
    assert usage.input_tokens == 120
    assert usage.cached_input_tokens == 20
    assert usage.output_tokens == 30
    assert usage.reasoning_tokens == 8
    assert usage.tool_calls == 2
    assert usage.provider_request_id == "chatcmpl-123"


def test_anthropic_usage_normalization() -> None:
    response = SimpleNamespace(
        id="msg_123",
        model="claude-3-5-sonnet-20241022",
        usage=SimpleNamespace(
            input_tokens=80,
            cache_read_input_tokens=25,
            cache_creation_input_tokens=5,
            output_tokens=40,
        ),
    )

    usage = _normalize_anthropic_usage(response, "claude-fallback", tool_calls=1)

    assert usage.provider == "anthropic"
    assert usage.input_tokens == 110
    assert usage.cached_input_tokens == 25
    assert usage.cache_creation_input_tokens == 5
    assert usage.output_tokens == 40
    assert usage.tool_calls == 1
    assert usage.provider_request_id == "msg_123"


def test_gemini_usage_normalization() -> None:
    response = SimpleNamespace(
        response_id="gemini-123",
        model_version="gemini-2.0-flash-001",
        usage_metadata=SimpleNamespace(
            prompt_token_count=90,
            cached_content_token_count=15,
            candidates_token_count=24,
            thoughts_token_count=6,
        ),
    )

    usage = _normalize_gemini_usage(response, "gemini-flash-latest", tool_calls=3)

    assert usage.provider == "gemini"
    assert usage.model == "gemini-2.0-flash-001"
    assert usage.input_tokens == 90
    assert usage.cached_input_tokens == 15
    assert usage.output_tokens == 30
    assert usage.reasoning_tokens == 6
    assert usage.tool_calls == 3
    assert usage.provider_request_id == "gemini-123"


def test_rate_card_uses_configured_alias_rates_for_versioned_model_response() -> None:
    rate_card = LLMRateCard.from_models(
        {"openai": "gpt-4o-mini"},
        {
            "openai:gpt-4o-mini": {
                "input_cost_per_million_usd": "1.00",
                "cached_input_cost_per_million_usd": "0.50",
                "output_cost_per_million_usd": "2.00",
                "tool_call_cost_usd": "0.01",
            }
        },
    )
    usage = LLMUsage(
        provider="openai",
        model="gpt-4o-mini-2024-07-18",
        input_tokens=1_000,
        cached_input_tokens=200,
        output_tokens=100,
        tool_calls=1,
    )

    assert rate_card.cost_for(usage) == Decimal("0.0111")


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["generate", "generate_with_tools", "stream_events"])
async def test_anthropic_adapter_matches_installed_message_api(operation, monkeypatch) -> None:
    from anthropic.resources.messages import AsyncMessages

    response = SimpleNamespace(id="request-test", model="claude-sonnet-4-6",
        usage=SimpleNamespace(input_tokens=10, output_tokens=2),
        content=[SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text="OK")])
    create_signature = inspect.signature(AsyncMessages.create)
    stream_signature = inspect.signature(AsyncMessages.stream)
    async def create(**kwargs):
        create_signature.bind(object(), **kwargs)
        assert "temperature" not in kwargs
        assert kwargs.get("tools", []) is not None
        return response
    class Stream:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None
        @property
        def text_stream(self):
            async def chunks():
                yield "OK"
            return chunks()
        async def get_final_message(self):
            return response
    def stream(**kwargs):
        stream_signature.bind(object(), **kwargs)
        assert "temperature" not in kwargs
        return Stream()
    provider = AnthropicProvider("test-key", "claude-sonnet-4-6", 0.2, 80)
    monkeypatch.setattr(provider, "_client", lambda: SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(side_effect=create), stream=stream)))
    if operation == "generate":
        result = await provider.generate(system_instruction="sys", prompt="hello")
        assert result.content == "OK"
    elif operation == "generate_with_tools":
        result = await provider.generate_with_tools(system_instruction="sys", messages=[LLMMessage(role="user", content="hello")],
            tools=[ToolDefinition(name="read_status", description="Read", parameters_schema={"type": "object", "properties": {}})])
        assert result.content == "OK"
    else:
        events = [event async for event in provider.stream_events(system_instruction="sys", prompt="hello")]
        assert events[0].content == "OK"
        assert events[-1].usage.input_tokens == 10

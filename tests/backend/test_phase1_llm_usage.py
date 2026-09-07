from types import SimpleNamespace
from decimal import Decimal

from backend.app.ai.llm.anthropic_provider import _normalize_anthropic_usage
from backend.app.ai.llm.gemini_provider import _normalize_gemini_usage
from backend.app.ai.llm.openai_provider import _normalize_openai_usage
from backend.app.ai.llm.model_registry import LLMRateCard
from backend.app.ai.llm.schemas import LLMUsage


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
    assert usage.cached_input_tokens == 30
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
    assert usage.output_tokens == 24
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
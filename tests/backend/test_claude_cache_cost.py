from types import SimpleNamespace
from decimal import Decimal
from backend.app.ai.llm.anthropic_provider import _normalize_anthropic_usage
from backend.app.ai.llm.model_registry import LLMModelSpec

def test_claude_cache_writes_are_not_discounted_as_reads():
    response = SimpleNamespace(id="msg_cost", model="claude-sonnet-4-6", usage=SimpleNamespace(
        input_tokens=100, cache_read_input_tokens=1000, cache_creation_input_tokens=2000,
        cache_creation=SimpleNamespace(ephemeral_1h_input_tokens=500), output_tokens=200))
    usage = _normalize_anthropic_usage(response, response.model)
    model = LLMModelSpec("anthropic", response.model, "Claude", frozenset(), 1000000, "standard", "standard", 1,
        input_cost_per_million_usd=Decimal("3"), cached_input_cost_per_million_usd=Decimal("0.3"), output_cost_per_million_usd=Decimal("15"))
    assert usage.input_tokens == 3100
    assert usage.cached_input_tokens == 1000
    assert usage.cache_creation_input_tokens == 2000
    assert model.cost_for(usage) == Decimal("0.012225")

def test_ai_keys_remove_pasted_whitespace_without_disclosing_them():
    from backend.app.config.settings import Settings
    settings = Settings(ANTHROPIC_API_KEY="  sk-ant-test\n-credential \r\n")
    assert settings.anthropic_api_key == "sk-ant-test-credential"

"""Phase 32 — Resilient AI Gateway.

Couvre : fallback simple, échec total -> `AIProvidersUnavailableError`, erreur
non éligible au fallback (config/clé API) qui échoue immédiatement sans
masquage, et le circuit breaker qui saute un fournisseur en échec répété.
"""

from __future__ import annotations

import pytest

from backend.app.ai.llm.base import LLMProvider
from backend.app.ai.llm.circuit_breaker import ProviderCircuitBreaker
from backend.app.ai.llm.exceptions import AIProvidersUnavailableError, LLMProviderError
from backend.app.ai.llm.factory import LLMProviderFactory
from backend.app.ai.llm.gateway import AvenqoAIGateway
from backend.app.ai.llm.health import ProviderHealthRegistry
from backend.app.ai.llm.failure_classification import FailureCategory
from backend.app.ai.llm.model_registry import model_spec
from backend.app.ai.llm.model_registry import LLMRateCard
from backend.app.ai.llm.router import (
    LLMRoutingContext,
    LLMTaskComplexity,
    LLMTaskType,
    SmartModelRouter,
    routing_context_for_chat,
)
from backend.app.ai.llm.schemas import LLMGeneration, LLMStreamChunk, LLMUsage
from backend.app.config.settings import Settings


class FakeProvider(LLMProvider):
    supports_tool_calling = False

    def __init__(self, name: str, *, fail: Exception | None = None, calls: list[str] | None = None) -> None:
        self.name = name
        self._fail = fail
        self._calls = calls if calls is not None else []

    async def generate(self, *, system_instruction: str, prompt: str) -> LLMGeneration:
        self._calls.append(self.name)
        if self._fail is not None:
            raise self._fail
        return LLMGeneration(f"reply-from-{self.name}", self.name, "fake-model", {})

    async def stream(self, *, system_instruction: str, prompt: str):
        self._calls.append(self.name)
        if self._fail is not None:
            raise self._fail
        yield "chunk"


def _smart_router(providers: list[LLMProvider], health: ProviderHealthRegistry) -> SmartModelRouter:
    models = {
        "openai": "gpt-4o-mini",
        "anthropic": "claude-3-5-sonnet-20241022",
        "gemini": "gemini-flash-latest",
    }
    return SmartModelRouter(
        {provider.name: model_spec(provider.name, models[provider.name]) for provider in providers},
        health,
    )


def _gateway(providers: list[LLMProvider], **kwargs) -> AvenqoAIGateway:
    return AvenqoAIGateway(
        providers,
        circuit_breaker=ProviderCircuitBreaker(failure_threshold=2, cooldown_seconds=9999),
        health_registry=ProviderHealthRegistry(),
        max_retries_per_provider=0,
        base_delay_seconds=0.0,
        max_delay_seconds=0.0,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_gateway_falls_back_to_second_provider_on_retryable_failure() -> None:
    calls: list[str] = []
    failure = LLMProviderError("Le fournisseur IA est temporairement indisponible")
    failure.__cause__ = TimeoutError("timed out")
    primary = FakeProvider("primary", fail=failure, calls=calls)
    fallback = FakeProvider("fallback", calls=calls)
    gateway = _gateway([primary, fallback])

    result = await gateway.generate(system_instruction="sys", prompt="hello")

    assert result.content == "reply-from-fallback"
    assert calls == ["primary", "fallback"]
    assert [attempt.success for attempt in result.attempts] == [False, True]


@pytest.mark.asyncio
async def test_gateway_raises_providers_unavailable_when_all_fail() -> None:
    def _err() -> LLMProviderError:
        exc = LLMProviderError("Le fournisseur IA est temporairement indisponible")
        exc.__cause__ = TimeoutError("timed out")
        return exc

    primary = FakeProvider("primary", fail=_err())
    fallback = FakeProvider("fallback", fail=_err())
    gateway = _gateway([primary, fallback])

    with pytest.raises(AIProvidersUnavailableError):
        await gateway.generate(system_instruction="sys", prompt="hello")


@pytest.mark.asyncio
async def test_gateway_does_not_fallback_on_non_retryable_config_error() -> None:
    calls: list[str] = []

    def _config_error() -> LLMProviderError:
        return LLMProviderError("Le fournisseur IA n'est pas configuré")

    primary = FakeProvider("primary", fail=_config_error(), calls=calls)
    fallback = FakeProvider("fallback", calls=calls)
    gateway = _gateway([primary, fallback])

    with pytest.raises(LLMProviderError):
        await gateway.generate(system_instruction="sys", prompt="hello")

    assert calls == ["primary"]  # jamais basculé vers le fallback


@pytest.mark.asyncio
async def test_circuit_breaker_skips_provider_after_repeated_failures() -> None:
    calls: list[str] = []

    def _err() -> LLMProviderError:
        exc = LLMProviderError("Le fournisseur IA est temporairement indisponible")
        exc.__cause__ = TimeoutError("timed out")
        return exc

    breaker = ProviderCircuitBreaker(failure_threshold=1, cooldown_seconds=9999)
    fallback = FakeProvider("fallback", calls=calls)
    gateway = AvenqoAIGateway(
        [FakeProvider("primary", fail=_err(), calls=calls), fallback],
        circuit_breaker=breaker,
        health_registry=ProviderHealthRegistry(),
        max_retries_per_provider=0,
        base_delay_seconds=0.0,
        max_delay_seconds=0.0,
    )

    await gateway.generate(system_instruction="sys", prompt="hello")
    assert calls == ["primary", "fallback"]

    calls.clear()
    await gateway.generate(system_instruction="sys", prompt="hello again")
    # Le circuit du primaire est maintenant ouvert : il est sauté directement.
    assert calls == ["fallback"]


def test_llm_factory_create_gateway_skips_unconfigured_fallback() -> None:
    settings = Settings(
        AI_PRIMARY_PROVIDER="openai",
        AI_FALLBACK_PROVIDER_1="anthropic",
        OPENAI_API_KEY="test-key",
        ANTHROPIC_API_KEY="",
        GOOGLE_AI_API_KEY="",
    )

    gateway = LLMProviderFactory.create_gateway(settings)

    assert isinstance(gateway, AvenqoAIGateway)
    assert [provider.name for provider in gateway._providers] == ["openai"]


def test_llm_factory_create_gateway_includes_configured_fallback() -> None:
    settings = Settings(
        AI_PRIMARY_PROVIDER="openai",
        AI_FALLBACK_PROVIDER_1="anthropic",
        OPENAI_API_KEY="test-key",
        ANTHROPIC_API_KEY="test-key-2",
        GOOGLE_AI_API_KEY="",
    )

    gateway = LLMProviderFactory.create_gateway(settings)

    assert [provider.name for provider in gateway._providers] == ["openai", "anthropic"]


def test_llm_factory_automatically_includes_all_configured_providers() -> None:
    settings = Settings(
        AI_PRIMARY_PROVIDER="openai",
        OPENAI_API_KEY="test-key",
        ANTHROPIC_API_KEY="test-key-2",
        GOOGLE_AI_API_KEY="test-key-3",
    )

    gateway = LLMProviderFactory.create_gateway(settings)

    assert [provider.name for provider in gateway._providers] == ["openai", "anthropic", "gemini"]


def test_smart_router_selects_inexpensive_model_for_simple_task() -> None:
    providers = [FakeProvider("anthropic"), FakeProvider("openai"), FakeProvider("gemini")]
    health = ProviderHealthRegistry()
    router = _smart_router(providers, health)

    ranked = router.rank(
        providers,
        LLMRoutingContext(
            task_type=LLMTaskType.CLASSIFICATION,
            complexity=LLMTaskComplexity.SIMPLE,
            context_tokens=500,
            expected_output_tokens=50,
        ),
    )

    assert ranked[0].name == "gemini"


def test_smart_router_selects_strong_reasoning_model_for_complex_task() -> None:
    providers = [FakeProvider("gemini"), FakeProvider("openai"), FakeProvider("anthropic")]
    health = ProviderHealthRegistry()
    router = _smart_router(providers, health)

    ranked = router.rank(
        providers,
        LLMRoutingContext(
            task_type=LLMTaskType.BUSINESS_REASONING,
            complexity=LLMTaskComplexity.COMPLEX,
            context_tokens=2_000,
            expected_output_tokens=800,
            requires_reasoning=True,
        ),
    )

    assert ranked[0].name == "anthropic"


def test_smart_router_filters_models_without_required_tool_capability() -> None:
    providers = [FakeProvider("gemini"), FakeProvider("openai")]
    providers[0].supports_tool_calling = False
    providers[1].supports_tool_calling = True
    health = ProviderHealthRegistry()
    router = _smart_router(providers, health)

    ranked = router.rank(
        providers,
        LLMRoutingContext(
            task_type=LLMTaskType.TOOL_ORCHESTRATION,
            requires_tool_calling=True,
        ),
    )

    assert [provider.name for provider in ranked] == ["openai"]


def test_smart_router_increases_cost_priority_when_credits_are_low() -> None:
    providers = [FakeProvider("openai"), FakeProvider("gemini")]
    health = ProviderHealthRegistry()
    router = _smart_router(providers, health)

    ranked = router.rank(
        providers,
        LLMRoutingContext(
            task_type=LLMTaskType.BUSINESS_QUESTION,
            context_tokens=4_000,
            expected_output_tokens=800,
            plan_code="demo",
            remaining_credits=2,
        ),
    )

    assert ranked[0].name == "gemini"


def test_smart_router_uses_long_context_compatible_model() -> None:
    providers = [FakeProvider("openai"), FakeProvider("anthropic"), FakeProvider("gemini")]
    health = ProviderHealthRegistry()

    ranked = _smart_router(providers, health).rank(
        providers,
        LLMRoutingContext(context_tokens=300_000),
    )

    assert [provider.name for provider in ranked] == ["gemini"]


def test_smart_router_avoids_degraded_provider() -> None:
    providers = [FakeProvider("openai"), FakeProvider("gemini")]
    health = ProviderHealthRegistry()
    health.record_failure("openai", FailureCategory.TIMEOUT, latency_ms=5_000)
    health.record_success("gemini", latency_ms=100)

    ranked = _smart_router(providers, health).rank(
        providers,
        LLMRoutingContext(context_tokens=500),
    )

    assert ranked[0].name == "gemini"


def test_chat_routing_keeps_task_semantics_separate_from_tool_requirement() -> None:
    simple = routing_context_for_chat(
        query="Classify these customers",
        prompt="short prompt",
        has_tools=True,
        plan_code="demo",
        remaining_credits=5,
        avenqo_request_id="simple",
    )
    complex_context = routing_context_for_chat(
        query="Why did sales decline and what strategy should we use?",
        prompt="business evidence",
        has_tools=True,
        plan_code="enterprise",
        remaining_credits=10_000,
        avenqo_request_id="complex",
    )

    assert simple.task_type == LLMTaskType.EXTRACTION
    assert simple.complexity == LLMTaskComplexity.SIMPLE
    assert simple.requires_tool_calling is True
    assert simple.requires_structured_output is True
    assert complex_context.task_type == LLMTaskType.BUSINESS_REASONING
    assert complex_context.complexity == LLMTaskComplexity.COMPLEX
    assert complex_context.requires_reasoning is True


@pytest.mark.asyncio
async def test_gateway_calls_only_smart_router_primary_when_it_succeeds() -> None:
    calls: list[str] = []
    providers = [FakeProvider("gemini", calls=calls), FakeProvider("anthropic", calls=calls)]
    health = ProviderHealthRegistry()
    models = {
        "gemini": "gemini-flash-latest",
        "anthropic": "claude-3-5-sonnet-20241022",
    }
    rate_card = LLMRateCard.from_models(models)
    gateway = AvenqoAIGateway(
        providers,
        circuit_breaker=ProviderCircuitBreaker(failure_threshold=2, cooldown_seconds=9999),
        health_registry=health,
        router=SmartModelRouter(
            {provider.name: rate_card.spec_for(provider.name, models[provider.name]) for provider in providers},
            health,
        ),
        rate_card=rate_card,
        max_retries_per_provider=0,
        base_delay_seconds=0,
        max_delay_seconds=0,
    )

    with gateway.routing(LLMRoutingContext(
        complexity=LLMTaskComplexity.COMPLEX,
        requires_reasoning=True,
        avenqo_request_id="req-123",
    )):
        result = await gateway.generate(system_instruction="sys", prompt="analyze")

    assert calls == ["anthropic"]
    assert len(result.attempts) == 1
    assert result.attempts[0].usage.avenqo_request_id == "req-123"


@pytest.mark.asyncio
async def test_gateway_accounts_for_billable_failed_attempt_before_fallback() -> None:
    calls: list[str] = []
    billed_usage = LLMUsage(
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=1_000,
        output_tokens=100,
    )
    failure = LLMProviderError(
        "Le fournisseur IA est temporairement indisponible",
        usage=billed_usage,
    )
    failure.__cause__ = TimeoutError("timed out")
    providers = [
        FakeProvider("openai", fail=failure, calls=calls),
        FakeProvider("gemini", calls=calls),
    ]
    rate_card = LLMRateCard.from_models({
        "openai": "gpt-4o-mini",
        "gemini": "gemini-flash-latest",
    })
    gateway = AvenqoAIGateway(
        providers,
        circuit_breaker=ProviderCircuitBreaker(failure_threshold=2, cooldown_seconds=9999),
        health_registry=ProviderHealthRegistry(),
        rate_card=rate_card,
        max_retries_per_provider=0,
        base_delay_seconds=0,
        max_delay_seconds=0,
    )

    result = await gateway.generate(system_instruction="sys", prompt="hello")

    assert calls == ["openai", "gemini"]
    assert result.attempts[0].success is False
    assert result.attempts[0].provider_cost_usd > 0
    assert result.attempts[1].success is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cause",
    [
        TimeoutError("timed out"),
        RuntimeError("429 rate limit"),
        RuntimeError("503 service unavailable"),
        RuntimeError("model unavailable"),
    ],
)
async def test_gateway_falls_back_for_required_temporary_failures(cause: Exception) -> None:
    calls: list[str] = []
    failure = LLMProviderError("temporary failure")
    failure.__cause__ = cause
    gateway = _gateway([
        FakeProvider("primary", fail=failure, calls=calls),
        FakeProvider("fallback", calls=calls),
    ])

    result = await gateway.generate(system_instruction="sys", prompt="hello")

    assert result.provider == "fallback"
    assert calls == ["primary", "fallback"]


@pytest.mark.asyncio
async def test_gateway_stream_surfaces_final_usage_and_metered_attempt() -> None:
    class UsageStreamProvider(FakeProvider):
        async def stream_events(self, *, system_instruction: str, prompt: str):
            self._calls.append(self.name)
            yield LLMStreamChunk(content="hello")
            yield LLMStreamChunk(usage=LLMUsage(
                provider="openai",
                model="gpt-4o-mini",
                input_tokens=1_000,
                output_tokens=100,
                provider_request_id="stream-provider-id",
            ))

    calls: list[str] = []
    provider = UsageStreamProvider("openai", calls=calls)
    rate_card = LLMRateCard.from_models({"openai": "gpt-4o-mini"})
    gateway = AvenqoAIGateway(
        [provider],
        circuit_breaker=ProviderCircuitBreaker(failure_threshold=2, cooldown_seconds=9999),
        health_registry=ProviderHealthRegistry(),
        rate_card=rate_card,
        max_retries_per_provider=0,
        base_delay_seconds=0,
        max_delay_seconds=0,
    )

    with gateway.routing(LLMRoutingContext(avenqo_request_id="stream-req")):
        events = [
            event async for event in gateway.stream_events(
                system_instruction="sys",
                prompt="hello",
            )
        ]

    assert calls == ["openai"]
    assert "".join(event.content for event in events) == "hello"
    assert events[-1].usage is not None
    assert events[-1].usage.avenqo_request_id == "stream-req"
    assert events[-1].attempts[0].provider_cost_usd > 0

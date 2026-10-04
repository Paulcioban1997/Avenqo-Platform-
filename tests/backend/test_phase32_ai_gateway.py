"""Phase 32 — Resilient AI Gateway.

Couvre : fallback simple, échec total -> `AIProvidersUnavailableError`, erreur
non éligible au fallback (config/clé API) qui échoue immédiatement sans
masquage, et le circuit breaker qui saute un fournisseur en échec répété.
"""

from __future__ import annotations

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from backend.app.ai.llm.base import LLMProvider
from backend.app.ai.llm.circuit_breaker import ProviderCircuitBreaker
from backend.app.ai.llm.exceptions import AIProvidersUnavailableError, LLMProviderError
from backend.app.ai.llm.factory import LLMProviderFactory
from backend.app.ai.llm.gateway import AvenqoAIGateway
from backend.app.ai.llm.health import ProviderHealthRegistry
from backend.app.ai.llm.failure_classification import FailureCategory
from backend.app.ai.llm.model_registry import model_spec
from backend.app.ai.llm.model_registry import LLMModelRegistry, LLMRateCard
from backend.app.ai.llm.router import (
    LLMRoutingContext,
    LLMTaskComplexity,
    LLMTaskType,
    SmartModelRouter,
    routing_context_for_chat,
)
from backend.app.ai.llm.provider_registry import DEFAULT_LLM_PROVIDER_REGISTRY
from backend.app.ai.llm.schemas import LLMGeneration, LLMStreamChunk, LLMUsage
from backend.app.ai.llm.schemas import LLMMessage, ToolDefinition
from backend.app.ai.llm.vertex_provider import VertexProvider
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


def test_vertex_is_registered_but_not_implicitly_enabled() -> None:
    settings = Settings(_env_file=None, OPENAI_API_KEY="test", VERTEX_ENABLED=False)
    assert DEFAULT_LLM_PROVIDER_REGISTRY.get("vertex") is not None
    assert LLMProviderFactory._credential_for(settings, "vertex") is None
    gateway = LLMProviderFactory.create_gateway(settings)
    assert all(provider.name != "vertex" for provider in gateway._providers)


@pytest.mark.asyncio
async def test_unobserved_provider_health_is_unknown_not_healthy() -> None:
    from backend.app.ai.tools.support.support_tools import GetAICapabilityStatusTool

    result = await GetAICapabilityStatusTool(ProviderHealthRegistry()).run(Mock(), Mock())
    assert result.data["status"] == "unknown"


def test_supported_production_profiles_have_sourced_rates() -> None:
    from decimal import Decimal

    settings = Settings(_env_file=None)
    rate_card = LLMRateCard.from_models({"anthropic": settings.anthropic_model, "gemini": settings.gemini_model})
    assert rate_card.pricing_for("gemini", settings.gemini_model).output_cost_per_million_usd == Decimal("2.50")
    assert rate_card.pricing_for("anthropic", settings.anthropic_model).input_cost_per_million_usd == Decimal("3.00")
    assert rate_card.pricing_for("gemini", settings.gemini_model).source.startswith("https://")


@pytest.mark.parametrize("code, category", [(403, FailureCategory.AUTH_CONFIG), (404, FailureCategory.MODEL_UNAVAILABLE), (429, FailureCategory.RATE_LIMITED), (500, FailureCategory.PROVIDER_5XX)])
def test_google_http_status_is_classified_without_sensitive_message(code, category) -> None:
    from google.genai.errors import ClientError
    from backend.app.ai.llm.failure_classification import classify_exception

    assert classify_exception(ClientError(code, {})) == category


def test_vertex_requires_explicit_project_location_and_model() -> None:
    settings = Settings(_env_file=None, VERTEX_ENABLED=True, VERTEX_PROJECT="test-project", VERTEX_LOCATION="", VERTEX_MODEL="test-model")
    assert LLMProviderFactory._credential_for(settings, "vertex") is None
    settings.vertex_location = "europe-west4"
    assert LLMProviderFactory._credential_for(settings, "vertex") == "adc"


def _vertex_settings(**overrides) -> Settings:
    values = dict(
        AI_PRIMARY_PROVIDER="vertex",
        OPENAI_API_KEY=None,
        ANTHROPIC_API_KEY=None,
        GOOGLE_AI_API_KEY=None,
        VERTEX_ENABLED=True,
        VERTEX_PROJECT="test-project",
        VERTEX_LOCATION="europe-west4",
        VERTEX_MODEL="gemini-test",
        AI_MODEL_CATALOG={"vertex:gemini-test": {
            "capabilities": ["text", "tool_calling"],
            "context_window": 8192,
            "max_output_tokens": 800,
            "pricing_source": "test-fixture-not-production-pricing",
            "pricing_version": "test",
            "pricing_effective_from": "2026-01-01",
        }},
        AI_MODEL_RATE_CARD={"vertex:gemini-test": {
            "input_cost_per_million_usd": "1",
            "cached_input_cost_per_million_usd": "0.5",
            "output_cost_per_million_usd": "2",
            "reasoning_cost_per_million_usd": "0",
        }},
    )
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _google_response(**overrides):
    values = dict(text="bonjour", model_version="gemini-test-version", response_id="request-test",
                  candidates=[], usage_metadata=SimpleNamespace(prompt_token_count=90,
                  cached_content_token_count=15, candidates_token_count=24, thoughts_token_count=6))
    values.update(overrides)
    return SimpleNamespace(**values)


def test_vertex_client_uses_adc_and_preserves_explicit_region(monkeypatch) -> None:
    credentials = Mock()
    discover = Mock(return_value=(credentials, "ignored-project"))
    client_builder = Mock()
    monkeypatch.setattr("google.auth.default", discover)
    monkeypatch.setattr("google.genai.Client", client_builder)
    provider = LLMProviderFactory.create(_vertex_settings(LLM_PROVIDER="vertex"))
    provider._client()
    provider._client()
    discover.assert_called_once_with(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    options = client_builder.call_args.kwargs
    assert options["vertexai"] is True
    assert options["enterprise"] is True
    assert options["credentials"] is credentials
    assert "api_key" not in options
    assert options["project"] == "test-project"
    assert options["location"] == "europe-west4"
    assert options["http_options"].api_version == "v1"
    assert options["http_options"].timeout == 60000
    assert options["http_options"].retry_options.attempts == 1


def test_vertex_sealed_service_account_config_is_validated_and_never_logged(monkeypatch) -> None:
    import json

    credentials = Mock()
    load_credentials = Mock(return_value=(credentials, "avenqo-509823"))
    client_builder = Mock()
    monkeypatch.setattr("google.auth.load_credentials_from_dict", load_credentials)
    monkeypatch.setattr("google.auth.default", Mock(side_effect=AssertionError("ADC fallback must not be used")))
    monkeypatch.setattr("google.genai.Client", client_builder)
    secret_payload = json.dumps({
        "type": "service_account",
        "project_id": "avenqo-509823",
        "client_email": "avenqo-vertex-runtime@avenqo-509823.iam.gserviceaccount.com",
        "private_key": "never-print-this-test-marker",
    })
    provider = VertexProvider(
        "avenqo-509823", "global", "gemini-3.5-flash-lite", 0.2, 80,
        enabled=True,
        service_account_email="avenqo-vertex-runtime@avenqo-509823.iam.gserviceaccount.com",
        service_account_json=secret_payload,
    )
    provider._client()
    load_credentials.assert_called_once()
    assert load_credentials.call_args.kwargs["scopes"] == ["https://www.googleapis.com/auth/cloud-platform"]
    options = client_builder.call_args.kwargs
    assert options["credentials"] is credentials
    assert "api_key" not in options
    assert "never-print-this-test-marker" not in repr(options)


def test_vertex_rejects_wrong_sealed_service_account_identity(monkeypatch) -> None:
    import json
    from backend.app.ai.llm.exceptions import LLMProviderError

    load_credentials = Mock(side_effect=AssertionError("mismatched identity must be rejected before auth"))
    monkeypatch.setattr("google.auth.load_credentials_from_dict", load_credentials)
    provider = VertexProvider(
        "avenqo-509823", "global", "gemini-3.5-flash-lite", 0.2, 80,
        enabled=True,
        service_account_email="avenqo-vertex-runtime@avenqo-509823.iam.gserviceaccount.com",
        service_account_json=json.dumps({"type": "service_account", "project_id": "other-project", "client_email": "unexpected@example.com", "private_key": "secret-marker"}),
    )
    with pytest.raises(LLMProviderError) as error:
        provider._client()
    assert "secret-marker" not in str(error.value)
    load_credentials.assert_not_called()


def test_google_backend_selection_ignores_environment_defaults(monkeypatch) -> None:
    from google.auth.credentials import AnonymousCredentials
    from backend.app.ai.llm.gemini_provider import GeminiProvider

    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    monkeypatch.setenv("GOOGLE_GENAI_USE_ENTERPRISE", "true")
    direct = GeminiProvider("test-key", "gemini-test", 0.2, 80)._client()
    assert direct.vertexai is False
    direct.close()
    monkeypatch.setattr("google.auth.default", Mock(return_value=(AnonymousCredentials(), None)))
    vertex = VertexProvider("test-project", "europe-west4", "gemini-test", 0.2, 80, enabled=True)._client()
    assert vertex.vertexai is True
    vertex.close()


def test_direct_gemini_sdk_does_not_hide_retries_from_gateway(monkeypatch) -> None:
    from backend.app.ai.llm.gemini_provider import GeminiProvider

    builder = Mock()
    monkeypatch.setattr("google.genai.Client", builder)
    provider = GeminiProvider("test-key", "gemini-test", 0.2, 80)
    provider._client()
    provider._client()
    builder.assert_called_once()
    assert builder.call_args.kwargs["http_options"].retry_options.attempts == 1


@pytest.mark.parametrize("overrides", [
    {"AI_MODEL_RATE_CARD": {}},
    {"AI_MODEL_CATALOG": {}},
    {"VERTEX_ENABLED": False},
])
def test_vertex_invalid_primary_configuration_fails_closed(overrides) -> None:
    settings = _vertex_settings(**overrides)
    if not settings.vertex_enabled:
        with pytest.raises(LLMProviderError):
            LLMProviderFactory.create(settings.model_copy(update={"llm_provider": "vertex"}))._client()
    else:
        with pytest.raises(ValueError):
            LLMProviderFactory.create_gateway(settings)


@pytest.mark.asyncio
async def test_vertex_gateway_attributes_usage_and_prices_reasoning_once() -> None:
    from decimal import Decimal

    gateway = LLMProviderFactory.create_gateway(_vertex_settings())
    provider = gateway._providers[0]
    provider._client_instance = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(
        generate_content=AsyncMock(return_value=_google_response()))))
    with gateway.routing(LLMRoutingContext(tenant_id="tenant-a", user_id="user-a", avenqo_request_id="avenqo-a")):
        result = await gateway.generate(system_instruction="fr", prompt="bonjour")
    assert result.provider == result.usage.provider == "vertex"
    assert result.usage.tenant_id == "tenant-a"
    assert result.usage.user_id == "user-a"
    assert result.usage.output_tokens == 30
    assert result.usage.reasoning_tokens == 6
    assert result.usage.provider_request_id == "request-test"
    assert result.usage.model == "gemini-test"
    assert len(result.attempts) == 1
    assert result.attempts[0].provider_cost_usd == Decimal("0.0001425")


@pytest.mark.asyncio
async def test_vertex_missing_usage_is_unknown_not_free_success() -> None:
    gateway = LLMProviderFactory.create_gateway(_vertex_settings())
    gateway._providers[0]._client_instance = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(
        generate_content=AsyncMock(return_value=_google_response(usage_metadata=None)))))
    with pytest.raises(LLMProviderError) as error:
        await gateway.generate(system_instruction="fr", prompt="bonjour")
    assert len(error.value.attempts) == 1
    assert error.value.attempts[0].request_status == "usage_unavailable"
    assert error.value.attempts[0].success is False


@pytest.mark.asyncio
async def test_vertex_stream_preserves_usage_before_trailing_empty_chunk() -> None:
    async def chunks():
        yield _google_response()
        yield _google_response(text="", usage_metadata=None)

    provider = VertexProvider("test-project", "europe-west4", "gemini-test", 0.2, 80, enabled=True)
    provider._client_instance = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(
        generate_content_stream=AsyncMock(return_value=chunks()))))
    events = [event async for event in provider.stream_events(system_instruction="fr", prompt="bonjour")]
    assert events[0].content == "bonjour"
    assert events[-1].usage.provider == "vertex"
    assert events[-1].usage.output_tokens == 30


@pytest.mark.asyncio
async def test_vertex_tools_return_calls_without_automatic_execution() -> None:
    from google.genai import types

    response = _google_response(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[
        types.Part(function_call=types.FunctionCall(name="retail_status", args={}), thought_signature=b"test")]))])
    generate = AsyncMock(return_value=response)
    provider = VertexProvider("test-project", "europe-west4", "gemini-test", 0.2, 80, enabled=True)
    provider._client_instance = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    result = await provider.generate_with_tools(system_instruction="fr", messages=[LLMMessage(role="user", content="bonjour")],
        tools=[ToolDefinition(name="retail_status", description="Read status", parameters_schema={"type": "object", "properties": {}})])
    assert result.provider == result.usage.provider == "vertex"
    assert result.tool_calls[0].name == "retail_status"
    assert result.tool_calls[0].provider_metadata == b"test"
    assert generate.call_args.kwargs["config"].automatic_function_calling.disable is True


@pytest.mark.asyncio
async def test_vertex_missing_adc_does_not_retry_or_leak_credentials(monkeypatch) -> None:
    from google.auth.exceptions import DefaultCredentialsError

    discover = Mock(side_effect=DefaultCredentialsError("private-test-value"))
    monkeypatch.setattr("google.auth.default", discover)
    gateway = LLMProviderFactory.create_gateway(_vertex_settings())
    with pytest.raises(LLMProviderError) as error:
        await gateway.generate(system_instruction="fr", prompt="bonjour")
    assert "private-test-value" not in str(error.value)
    assert error.value.attempts[0].failure_category == "auth_config"
    discover.assert_called_once()


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


def test_llm_factory_builds_multiple_models_with_catalog_limits_and_timeout() -> None:
    settings = Settings(
        AI_PRIMARY_PROVIDER="openai",
        OPENAI_API_KEY="test-key",
        ANTHROPIC_API_KEY="",
        GOOGLE_AI_API_KEY="",
        LLM_MAX_TOKENS=800,
        AI_PROVIDER_MODELS={"openai": ["gpt-4o-mini", "openai-test-model"]},
        AI_MODEL_CATALOG={
            "openai:openai-test-model": {
                "capabilities": ["text"],
                "context_window": 32_000,
                "max_output_tokens": 1_024,
                "request_timeout_seconds": 12.5,
            },
        },
    )

    gateway = LLMProviderFactory.create_gateway(settings)

    assert [(provider.name, provider._model) for provider in gateway._providers] == [
        ("openai", "gpt-4o-mini"),
        ("openai", "openai-test-model"),
    ]
    assert gateway._providers[1]._max_tokens == 800
    assert gateway._providers[1]._request_timeout_seconds == 12.5


def test_llm_factory_rejects_unknown_model_without_catalog_metadata() -> None:
    settings = Settings(
        AI_PRIMARY_PROVIDER="openai",
        OPENAI_API_KEY="test-key",
        ANTHROPIC_API_KEY="",
        GOOGLE_AI_API_KEY="",
        AI_PROVIDER_MODELS={"openai": ["unregistered-model"]},
    )

    with pytest.raises(ValueError, match="requires explicit capability and limit metadata"):
        LLMProviderFactory.create_gateway(settings)


def test_default_provider_registry_exposes_all_supported_provider_codes() -> None:
    assert DEFAULT_LLM_PROVIDER_REGISTRY.codes() == ("openai", "anthropic", "gemini", "vertex")
    assert DEFAULT_LLM_PROVIDER_REGISTRY.get("OPENAI").model_setting == "openai_model"


def test_model_registry_rejects_invalid_timeout_and_retry_policy() -> None:
    with pytest.raises(ValueError, match="timeout and retry policy"):
        LLMModelRegistry(
            [
                model_spec(
                    "openai",
                    "invalid-policy-model",
                    metadata={
                        "capabilities": ["text"],
                        "context_window": 1_000,
                        "max_output_tokens": 100,
                        "request_timeout_seconds": 0,
                    },
                ),
            ],
        )


@pytest.mark.asyncio
async def test_gateway_breaker_isolated_by_model_and_logs_selection(caplog) -> None:
    calls: list[str] = []
    providers = [FakeProvider("openai", calls=calls), FakeProvider("openai", calls=calls)]
    model_ids = ("gpt-4o-mini", "openai-test-model")
    for provider, model_id in zip(providers, model_ids):
        provider._model = model_id
    catalog = {
        "openai:openai-test-model": {
            "capabilities": ["text"],
            "context_window": 32_000,
            "max_output_tokens": 4_096,
        },
        "openai:gpt-4o-mini": {
            "max_retries": 0,
        },
    }
    rate_card = LLMRateCard.from_models(
        {"openai": model_ids},
        metadata=catalog,
    )
    health = ProviderHealthRegistry()
    router = SmartModelRouter(
        {("openai", model_id): rate_card.spec_for("openai", model_id) for model_id in model_ids},
        health,
    )
    context = LLMRoutingContext(
        tenant_id="tenant-1",
        user_id="user-1",
        conversation_id="conversation-1",
        agent_id="agent-1",
        module_id="retail",
        idempotency_key="request-1",
    )
    first = router.rank(providers, context)[0]
    first._fail = LLMProviderError("Le fournisseur IA est temporairement indisponible")
    first._fail.__cause__ = TimeoutError("timed out")
    breaker = ProviderCircuitBreaker(failure_threshold=1, cooldown_seconds=9999)
    gateway = AvenqoAIGateway(
        providers,
        circuit_breaker=breaker,
        health_registry=health,
        router=router,
        rate_card=rate_card,
        max_retries_per_provider=0,
        base_delay_seconds=0,
        max_delay_seconds=0,
    )

    with caplog.at_level("INFO"), gateway.routing(context):
        result = await gateway.generate(system_instruction="sys", prompt="hello")

    sibling = next(provider for provider in providers if provider is not first)
    assert calls == ["openai", "openai"]
    assert breaker.status_for(f"openai:{first._model}") == "open"
    assert breaker.status_for(f"openai:{sibling._model}") == "closed"
    assert "ai_router_decision" in caplog.text
    assert f"selected_model={first._model}" in caplog.text
    assert gateway.last_router_decision is not None
    assert gateway.last_router_decision.selected_model == first._model
    assert gateway.last_router_decision.selected_provider == "openai"
    assert result.attempts[0].usage.tenant_id == "tenant-1"
    assert result.attempts[0].usage.agent_id == "agent-1"
    assert result.attempts[0].usage.module_id == "retail"
    assert result.attempts[0].usage.idempotency_key == "request-1"


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


def test_smart_router_filters_models_without_streaming_support() -> None:
    model_ids = ("gpt-4o-mini", "openai-non-streaming")
    providers = [FakeProvider("openai"), FakeProvider("openai")]
    for provider, model_id in zip(providers, model_ids):
        provider._model = model_id
    rate_card = LLMRateCard.from_models(
        {"openai": model_ids},
        metadata={
            "openai:openai-non-streaming": {
                "capabilities": ["text"],
                "context_window": 32_000,
                "max_output_tokens": 4_096,
                "streaming": False,
            },
        },
    )
    router = SmartModelRouter(
        {("openai", model_id): rate_card.spec_for("openai", model_id) for model_id in model_ids},
        ProviderHealthRegistry(),
    )

    ranked = router.rank(providers, LLMRoutingContext(requires_streaming=True))

    assert [provider._model for provider in ranked] == ["gpt-4o-mini"]


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
    assert result.attempts[0].model == models["anthropic"]
    assert result.attempts[0].output_cost_per_million_usd > 0
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

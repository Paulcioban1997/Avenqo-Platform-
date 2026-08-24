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
from backend.app.ai.llm.schemas import LLMGeneration
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

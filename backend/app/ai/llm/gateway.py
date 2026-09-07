"""Resilient AI Gateway (Phase 32) — `AvenqoAIGateway`.

Implémente EXACTEMENT l'interface `LLMProvider` (Phase 28) : `ChatService`,
`ToolOrchestrator` et tous les outils prédictifs (Phase 30/31) continuent de
fonctionner sans aucune modification — le Gateway se substitue simplement au
provider unique renvoyé auparavant par `LLMProviderFactory.create()`.

Comportement :
- Classe les modèles compatibles selon la tâche, la santé, la latence et le coût.
- Essaie un seul fournisseur primaire, puis les fallbacks classés, séquentiellement.
- Un circuit ouvert (Phase 32, `ProviderCircuitBreaker`) fait sauter un
  fournisseur temporairement.
- Une erreur "non éligible au fallback" (config/clé API absente, requête
  invalide, contenu rejeté) est propagée immédiatement — jamais masquée par
  un basculement silencieux vers un autre fournisseur.
- Une erreur "retryable" (timeout, réseau, 5xx, surcharge) est retentée sur
  le MÊME fournisseur avec un backoff exponentiel + jitter borné, avant de
  passer au fournisseur suivant.
- Si tous les fournisseurs échouent/ont leur circuit ouvert :
  `AIProvidersUnavailableError`.
- Jamais de nom de fournisseur, de clé API ni de détail technique exposé au
  frontend — seul un message générique traverse `ChatService`.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import replace
from time import perf_counter
from typing import TypeVar

from backend.app.ai.llm.base import LLMProvider
from backend.app.ai.llm.circuit_breaker import ProviderCircuitBreaker
from backend.app.ai.llm.exceptions import AIProvidersUnavailableError, LLMProviderError, ToolCallingUnsupportedError
from backend.app.ai.llm.failure_classification import classify_exception, is_fallback_eligible, is_retryable
from backend.app.ai.llm.health import ProviderHealthRegistry
from backend.app.ai.llm.model_registry import LLMRateCard
from backend.app.ai.llm.router import LLMRoutingContext, SmartModelRouter
from backend.app.ai.llm.schemas import (
    LLMGeneration,
    LLMMessage,
    LLMProviderAttempt,
    LLMStreamChunk,
    LLMToolResponse,
    LLMUsage,
    ToolDefinition,
)

logger = logging.getLogger("avenqo.ai.gateway")

_T = TypeVar("_T")


class AvenqoAIGateway(LLMProvider):
    name = "avenqo-ai-gateway"

    def __init__(
        self,
        providers: list[LLMProvider],
        *,
        circuit_breaker: ProviderCircuitBreaker,
        health_registry: ProviderHealthRegistry,
        router: SmartModelRouter | None = None,
        rate_card: LLMRateCard | None = None,
        max_retries_per_provider: int = 2,
        base_delay_seconds: float = 0.5,
        max_delay_seconds: float = 4.0,
    ) -> None:
        if not providers:
            raise AIProvidersUnavailableError("Aucun fournisseur IA n'est configuré")
        self._providers = providers
        self._breaker = circuit_breaker
        self._health = health_registry
        self._router = router
        self._rate_card = rate_card
        self._max_retries = max_retries_per_provider
        self._base_delay = base_delay_seconds
        self._max_delay = max_delay_seconds
        self._routing_context: ContextVar[LLMRoutingContext | None] = ContextVar(
            f"avenqo_routing_context_{id(self)}",
            default=None,
        )

    @property
    def supports_tool_calling(self) -> bool:
        return any(provider.supports_tool_calling for provider in self._providers)

    @contextmanager
    def routing(self, context: LLMRoutingContext):
        token = self._routing_context.set(context)
        try:
            yield
        finally:
            self._routing_context.reset(token)

    def _ordered_providers(self, operation: str) -> list[LLMProvider]:
        context = self._routing_context.get() or LLMRoutingContext(
            requires_tool_calling=operation == "generate_with_tools",
        )
        if operation == "generate_with_tools" and not context.requires_tool_calling:
            context = replace(context, requires_tool_calling=True)
        if self._router is None:
            return list(self._providers)
        return self._router.rank(self._providers, context)

    def estimate_cost_usd(self, context: object):
        if not isinstance(context, LLMRoutingContext) or self._rate_card is None:
            return None
        providers = (
            self._router.rank(self._providers, context)
            if self._router is not None
            else list(self._providers)
        )
        if not providers:
            return None
        primary = providers[0]
        model_id = str(getattr(primary, "_model", ""))
        if not model_id:
            return None
        spec = self._rate_card.spec_for(primary.name, model_id)
        turns = max(context.expected_tool_calls + 1, 1)
        return spec.cost_for(LLMUsage(
            provider=primary.name,
            model=model_id,
            input_tokens=max(context.context_tokens, 1) * turns,
            output_tokens=max(context.expected_output_tokens, 1) * turns,
            tool_calls=max(context.expected_tool_calls, 0),
        ))

    def _usage_for_result(self, provider: LLMProvider, result) -> LLMUsage:
        usage = result.usage
        if usage is None:
            raw = result.token_usage
            usage = LLMUsage(
                provider=result.provider or provider.name,
                model=result.model,
                input_tokens=int(raw.get("input_tokens", 0) or 0),
                cached_input_tokens=int(raw.get("cached_input_tokens", 0) or 0),
                output_tokens=int(raw.get("output_tokens", 0) or 0),
                reasoning_tokens=int(raw.get("reasoning_tokens", 0) or 0),
                tool_calls=int(raw.get("tool_calls", 0) or 0),
                provider_request_id=raw.get("provider_request_id"),
            )
        context = self._routing_context.get()
        if context is not None and context.avenqo_request_id:
            usage = replace(usage, avenqo_request_id=context.avenqo_request_id)
        return usage

    def _empty_usage(self, provider: LLMProvider) -> LLMUsage:
        context = self._routing_context.get()
        model = getattr(provider, "_model", "")
        return LLMUsage(
            provider=provider.name,
            model=model,
            avenqo_request_id=context.avenqo_request_id if context else None,
        )

    def _attempt(
        self,
        *,
        provider: LLMProvider,
        operation: str,
        attempt_number: int,
        success: bool,
        latency_ms: int,
        usage: LLMUsage,
        failure_category: str | None = None,
    ) -> LLMProviderAttempt:
        if self._rate_card is None or not usage.model:
            return LLMProviderAttempt(
                provider=provider.name,
                model=usage.model,
                operation=operation,
                attempt_number=attempt_number,
                success=success,
                latency_ms=latency_ms,
                usage=usage,
                failure_category=failure_category,
            )
        spec = self._rate_card.spec_for(provider.name, usage.model)
        return LLMProviderAttempt(
            provider=provider.name,
            model=usage.model,
            operation=operation,
            attempt_number=attempt_number,
            success=success,
            latency_ms=latency_ms,
            usage=usage,
            failure_category=failure_category,
            provider_cost_usd=spec.cost_for(usage),
            input_cost_per_million_usd=spec.input_cost_per_million_usd,
            cached_input_cost_per_million_usd=spec.cached_input_cost_per_million_usd,
            output_cost_per_million_usd=spec.output_cost_per_million_usd,
            tool_call_cost_usd=spec.tool_call_cost_usd,
        )

    async def _retry_delay(self, retry_index: int) -> None:
        delay = min(self._max_delay, self._base_delay * (2 ** retry_index))
        delay += random.uniform(0, self._base_delay)
        await asyncio.sleep(delay)

    async def _run(
        self,
        operation: str,
        call: Callable[[LLMProvider], Coroutine[None, None, _T]],
    ) -> _T:
        last_error: Exception | None = None
        attempted_any = False
        attempts: list[LLMProviderAttempt] = []
        attempt_number = 0

        for provider in self._ordered_providers(operation):
            if self._breaker.is_open(provider.name):
                logger.info("ai_gateway_provider_skipped provider=%s operation=%s reason=circuit_open", provider.name, operation)
                continue

            for retry_index in range(self._max_retries + 1):
                attempted_any = True
                attempt_number += 1
                started = perf_counter()
                try:
                    result = await call(provider)
                except ToolCallingUnsupportedError:
                    raise
                except LLMProviderError as exc:
                    category = classify_exception(exc.__cause__ or exc)
                    latency_ms = round((perf_counter() - started) * 1000)
                    self._breaker.record_failure(provider.name)
                    self._health.record_failure(provider.name, category, latency_ms)
                    last_error = exc
                    usage = exc.usage or self._empty_usage(provider)
                    attempts.append(self._attempt(
                        provider=provider,
                        operation=operation,
                        attempt_number=attempt_number,
                        success=False,
                        latency_ms=latency_ms,
                        usage=usage,
                        failure_category=category.value,
                    ))
                    logger.warning(
                        "ai_gateway_failure provider=%s operation=%s attempt=%d category=%s",
                        provider.name, operation, retry_index + 1, category.value,
                    )
                    if not is_fallback_eligible(category):
                        exc.attempts = tuple(attempts)
                        raise
                    if is_retryable(category) and retry_index < self._max_retries:
                        await self._retry_delay(retry_index)
                        continue
                    break  # passe au fournisseur suivant
                else:
                    latency_ms = round((perf_counter() - started) * 1000)
                    self._breaker.record_success(provider.name)
                    self._health.record_success(provider.name, latency_ms)
                    usage = self._usage_for_result(provider, result)
                    attempts.append(self._attempt(
                        provider=provider,
                        operation=operation,
                        attempt_number=attempt_number,
                        success=True,
                        latency_ms=latency_ms,
                        usage=usage,
                    ))
                    logger.info("ai_gateway_success provider=%s operation=%s attempt=%d", provider.name, operation, retry_index + 1)
                    return replace(
                        result,
                        token_usage=usage.as_token_usage(),
                        attempts=tuple(attempts) + tuple(result.attempts),
                        usage=usage,
                    )

        if not attempted_any:
            logger.error("ai_gateway_all_circuits_open operation=%s", operation)
        raise AIProvidersUnavailableError(
            "Avenqo AI est temporairement indisponible. Merci de réessayer dans quelques instants.",
            attempts=tuple(attempts),
        ) from last_error

    async def generate(self, *, system_instruction: str, prompt: str) -> LLMGeneration:
        return await self._run(
            "generate",
            lambda provider: provider.generate(system_instruction=system_instruction, prompt=prompt),
        )

    async def stream(self, *, system_instruction: str, prompt: str) -> AsyncIterator[str]:
        async for event in self.stream_events(system_instruction=system_instruction, prompt=prompt):
            if event.content:
                yield event.content

    async def stream_events(
        self,
        *,
        system_instruction: str,
        prompt: str,
    ) -> AsyncIterator[LLMStreamChunk]:
        last_error: Exception | None = None
        attempts: list[LLMProviderAttempt] = []
        attempt_number = 0
        for provider in self._ordered_providers("stream"):
            if self._breaker.is_open(provider.name):
                continue
            for retry_index in range(self._max_retries + 1):
                attempt_number += 1
                started = perf_counter()
                emitted_content = False
                usage: LLMUsage | None = None
                try:
                    async for event in provider.stream_events(
                        system_instruction=system_instruction,
                        prompt=prompt,
                    ):
                        if event.usage is not None:
                            usage = event.usage
                        if event.content:
                            emitted_content = True
                            yield LLMStreamChunk(content=event.content)
                except LLMProviderError as exc:
                    category = classify_exception(exc.__cause__ or exc)
                    latency_ms = round((perf_counter() - started) * 1000)
                    self._breaker.record_failure(provider.name)
                    self._health.record_failure(provider.name, category, latency_ms)
                    last_error = exc
                    failed_usage = exc.usage or usage or self._empty_usage(provider)
                    attempts.append(self._attempt(
                        provider=provider,
                        operation="stream",
                        attempt_number=attempt_number,
                        success=False,
                        latency_ms=latency_ms,
                        usage=failed_usage,
                        failure_category=category.value,
                    ))
                    if emitted_content or not is_fallback_eligible(category):
                        exc.attempts = tuple(attempts)
                        raise
                    if is_retryable(category) and retry_index < self._max_retries:
                        await self._retry_delay(retry_index)
                        continue
                    break
                else:
                    latency_ms = round((perf_counter() - started) * 1000)
                    self._breaker.record_success(provider.name)
                    self._health.record_success(provider.name, latency_ms)
                    normalized = usage or self._empty_usage(provider)
                    context = self._routing_context.get()
                    if context is not None and context.avenqo_request_id:
                        normalized = replace(normalized, avenqo_request_id=context.avenqo_request_id)
                    attempts.append(self._attempt(
                        provider=provider,
                        operation="stream",
                        attempt_number=attempt_number,
                        success=True,
                        latency_ms=latency_ms,
                        usage=normalized,
                    ))
                    yield LLMStreamChunk(usage=normalized, attempts=tuple(attempts))
                    return
        raise AIProvidersUnavailableError(
            "Avenqo AI est temporairement indisponible. Merci de réessayer dans quelques instants.",
            attempts=tuple(attempts),
        ) from last_error

    async def generate_with_tools(
        self,
        *,
        system_instruction: str,
        messages: list[LLMMessage],
        tools: list[ToolDefinition],
    ) -> LLMToolResponse:
        return await self._run(
            "generate_with_tools",
            lambda provider: provider.generate_with_tools(system_instruction=system_instruction, messages=messages, tools=tools),
        )

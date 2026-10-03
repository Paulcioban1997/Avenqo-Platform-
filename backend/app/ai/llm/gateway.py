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
from backend.app.ai.llm.router import LLMRouterDecision, LLMRoutingContext, SmartModelRouter
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
        self._last_router_decision: LLMRouterDecision | None = None
        self._routing_context: ContextVar[LLMRoutingContext | None] = ContextVar(
            f"avenqo_routing_context_{id(self)}",
            default=None,
        )

    @property
    def supports_tool_calling(self) -> bool:
        return any(provider.supports_tool_calling for provider in self._providers)

    @property
    def last_router_decision(self) -> LLMRouterDecision | None:
        """Latest explainable decision, retained for internal observability."""

        return self._last_router_decision

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
        decision = self._router.decide(self._providers, context)
        self._last_router_decision = decision
        logger.info(
            "ai_router_decision operation=%s selected_provider=%s selected_model=%s reason=%s candidates=%s",
            operation,
            decision.selected_provider,
            decision.selected_model,
            decision.reason,
            ",".join(f"{provider}:{model}" for provider, model in decision.eligible_candidates),
        )
        return self._router.rank(self._providers, context)

    def _retry_policy(self, provider: LLMProvider) -> tuple[int, float, float]:
        if self._rate_card is None:
            return self._max_retries, self._base_delay, self._max_delay
        model_id = self._candidate_id(provider).partition(":")[2]
        spec = self._rate_card.get(provider.name, model_id) if model_id else None
        if spec is None:
            return self._max_retries, self._base_delay, self._max_delay
        return spec.max_retries, spec.base_delay_seconds, spec.max_delay_seconds

    def _candidate_id(self, provider: LLMProvider) -> str:
        model_id = (
            self._router.model_id_for(provider)
            if self._router is not None
            else str(getattr(provider, "model_id", "") or getattr(provider, "_model", ""))
        )
        return f"{provider.name}:{model_id}" if model_id else provider.name

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
        model_id = self._candidate_id(primary).partition(":")[2]
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
                cached_output_tokens=int(raw.get("cached_output_tokens", 0) or 0),
                reasoning_tokens=int(raw.get("reasoning_tokens", 0) or 0),
                text_input_tokens=raw.get("text_input_tokens"),
                cached_text_input_tokens=raw.get("cached_text_input_tokens"),
                text_output_tokens=raw.get("text_output_tokens"),
                audio_input_units=raw.get("audio_input_units", 0) or 0,
                cached_audio_input_units=raw.get("cached_audio_input_units", 0) or 0,
                audio_output_units=raw.get("audio_output_units", 0) or 0,
                audio_input_seconds=raw.get("audio_input_seconds", 0) or 0,
                tool_calls=int(raw.get("tool_calls", 0) or 0),
                provider_request_id=raw.get("provider_request_id"),
            )
        usage = self._registered_usage(provider, usage)
        return self._attribute_usage(usage)

    def _attribute_usage(self, usage: LLMUsage) -> LLMUsage:
        context = self._routing_context.get()
        if context is None:
            return usage
        return replace(
            usage,
            avenqo_request_id=context.avenqo_request_id or usage.avenqo_request_id,
            tenant_id=context.tenant_id or usage.tenant_id,
            user_id=context.user_id or usage.user_id,
            conversation_id=context.conversation_id or usage.conversation_id,
            agent_id=context.agent_id or usage.agent_id,
            module_id=context.module_id or usage.module_id,
            idempotency_key=context.idempotency_key or usage.idempotency_key,
        )

    def _registered_usage(self, provider: LLMProvider, usage: LLMUsage) -> LLMUsage:
        if self._rate_card is None or self._rate_card.get(provider.name, usage.model):
            return usage
        configured_model = str(getattr(provider, "_model", ""))
        if not configured_model and self._router is not None:
            configured_model = self._router.model_id_for(provider) or ""
        if not configured_model:
            models = self._rate_card.specs_for_provider(provider.name)
            configured_model = models[0].model_id if len(models) == 1 else ""
        spec = self._rate_card.get(provider.name, configured_model) if configured_model else None
        if spec is None:
            raise ValueError(
                f"Cannot price unregistered model '{provider.name}:{usage.model}'"
            )
        return replace(usage, provider=provider.name, model=spec.model_id)

    def _empty_usage(self, provider: LLMProvider) -> LLMUsage:
        context = self._routing_context.get()
        model = self._candidate_id(provider).partition(":")[2]
        return self._attribute_usage(LLMUsage(
            provider=provider.name,
            model=model,
            avenqo_request_id=context.avenqo_request_id if context else None,
        ))

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
        fallback_reason: str | None = None,
        request_status: str = "completed",
    ) -> LLMProviderAttempt:
        usage = self._attribute_usage(usage)
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
                fallback_reason=fallback_reason,
                request_status=request_status,
            )
        usage = self._registered_usage(provider, usage)
        spec = self._rate_card.spec_for(provider.name, usage.model)
        pricing = self._rate_card.pricing_for(provider.name, usage.model)
        return LLMProviderAttempt(
            provider=provider.name,
            model=usage.model,
            operation=operation,
            attempt_number=attempt_number,
            success=success,
            latency_ms=latency_ms,
            usage=usage,
            failure_category=failure_category,
            fallback_reason=fallback_reason,
            request_status=request_status,
            provider_cost_usd=pricing.cost_for(usage),
            input_cost_per_million_usd=pricing.input_cost_per_million_usd,
            cached_input_cost_per_million_usd=pricing.cached_input_cost_per_million_usd,
            output_cost_per_million_usd=pricing.output_cost_per_million_usd,
            cached_output_cost_per_million_usd=pricing.cached_output_cost_per_million_usd,
            reasoning_cost_per_million_usd=pricing.reasoning_cost_per_million_usd,
            audio_input_cost_per_million_usd=pricing.audio_input_cost_per_million_usd,
            cached_audio_input_cost_per_million_usd=pricing.cached_audio_input_cost_per_million_usd,
            audio_output_cost_per_million_usd=pricing.audio_output_cost_per_million_usd,
            audio_input_cost_per_second_usd=pricing.audio_input_cost_per_second_usd,
            tool_call_cost_usd=spec.tool_call_cost_usd,
            pricing_version=pricing.version,
            pricing_source=pricing.source,
            pricing_effective_from=pricing.effective_from.isoformat(),
        )

    async def _retry_delay(
        self,
        retry_index: int,
        *,
        base_delay: float,
        max_delay: float,
    ) -> None:
        delay = min(max_delay, base_delay * (2 ** retry_index))
        delay += random.uniform(0, base_delay)
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

        try:
            for provider in self._ordered_providers(operation):
                candidate_id = self._candidate_id(provider)
                model_id = candidate_id.partition(":")[2]
                max_retries, base_delay, max_delay = self._retry_policy(provider)
                if self._breaker.is_open(candidate_id):
                    logger.info(
                        "ai_gateway_candidate_skipped provider=%s model=%s operation=%s reason=circuit_open",
                        provider.name,
                        model_id,
                        operation,
                    )
                    continue

                for retry_index in range(max_retries + 1):
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
                        self._breaker.record_failure(candidate_id)
                        self._health.record_failure(candidate_id, category, latency_ms)
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
                            fallback_reason=category.value,
                            request_status="failed",
                        ))
                        logger.warning(
                            "ai_gateway_failure provider=%s model=%s operation=%s attempt=%d category=%s",
                            provider.name, model_id, operation, retry_index + 1, category.value,
                        )
                        if not is_fallback_eligible(category):
                            exc.attempts = tuple(attempts)
                            raise
                        if is_retryable(category) and retry_index < max_retries:
                            await self._retry_delay(
                                retry_index,
                                base_delay=base_delay,
                                max_delay=max_delay,
                            )
                            continue
                        break  # passe au fournisseur suivant
                    else:
                        latency_ms = round((perf_counter() - started) * 1000)
                        self._breaker.record_success(candidate_id)
                        self._health.record_success(candidate_id, latency_ms)
                        usage = self._usage_for_result(provider, result)
                        attempts.append(self._attempt(
                            provider=provider,
                            operation=operation,
                            attempt_number=attempt_number,
                            success=True,
                            latency_ms=latency_ms,
                            usage=usage,
                        ))
                        logger.info(
                            "ai_gateway_success provider=%s model=%s operation=%s attempt=%d",
                            provider.name,
                            model_id,
                            operation,
                            retry_index + 1,
                        )
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
        except BaseException as exc:
            known = list(attempts)
            for attempt in getattr(exc, "attempts", ()):
                if not any(attempt is recorded for recorded in known):
                    known.append(replace(attempt, attempt_number=len(known) + 1))
            exc.attempts = tuple(known)
            raise

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
            candidate_id = self._candidate_id(provider)
            model_id = candidate_id.partition(":")[2]
            max_retries, base_delay, max_delay = self._retry_policy(provider)
            if self._breaker.is_open(candidate_id):
                logger.info(
                    "ai_gateway_candidate_skipped provider=%s model=%s operation=stream reason=circuit_open",
                    provider.name,
                    model_id,
                )
                continue
            for retry_index in range(max_retries + 1):
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
                    self._breaker.record_failure(candidate_id)
                    self._health.record_failure(candidate_id, category, latency_ms)
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
                        fallback_reason=category.value,
                        request_status="failed",
                    ))
                    if emitted_content or not is_fallback_eligible(category):
                        exc.attempts = tuple(attempts)
                        raise
                    if is_retryable(category) and retry_index < max_retries:
                        await self._retry_delay(
                            retry_index,
                            base_delay=base_delay,
                            max_delay=max_delay,
                        )
                        continue
                    break
                else:
                    latency_ms = round((perf_counter() - started) * 1000)
                    self._breaker.record_success(candidate_id)
                    self._health.record_success(candidate_id, latency_ms)
                    normalized = usage or self._empty_usage(provider)
                    normalized = self._attribute_usage(normalized)
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

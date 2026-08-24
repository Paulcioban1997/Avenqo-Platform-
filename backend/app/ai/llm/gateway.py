"""Resilient AI Gateway (Phase 32) — `AvenqoAIGateway`.

Implémente EXACTEMENT l'interface `LLMProvider` (Phase 28) : `ChatService`,
`ToolOrchestrator` et tous les outils prédictifs (Phase 30/31) continuent de
fonctionner sans aucune modification — le Gateway se substitue simplement au
provider unique renvoyé auparavant par `LLMProviderFactory.create()`.

Comportement :
- Essaie le fournisseur primaire, puis les fallbacks configurés, dans l'ordre.
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
from typing import TypeVar

from backend.app.ai.llm.base import LLMProvider
from backend.app.ai.llm.circuit_breaker import ProviderCircuitBreaker
from backend.app.ai.llm.exceptions import AIProvidersUnavailableError, LLMProviderError, ToolCallingUnsupportedError
from backend.app.ai.llm.failure_classification import classify_exception, is_fallback_eligible, is_retryable
from backend.app.ai.llm.health import ProviderHealthRegistry
from backend.app.ai.llm.schemas import LLMGeneration, LLMMessage, LLMToolResponse, ToolDefinition

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
        max_retries_per_provider: int = 2,
        base_delay_seconds: float = 0.5,
        max_delay_seconds: float = 4.0,
    ) -> None:
        if not providers:
            raise AIProvidersUnavailableError("Aucun fournisseur IA n'est configuré")
        self._providers = providers
        self._breaker = circuit_breaker
        self._health = health_registry
        self._max_retries = max_retries_per_provider
        self._base_delay = base_delay_seconds
        self._max_delay = max_delay_seconds

    @property
    def supports_tool_calling(self) -> bool:
        return any(provider.supports_tool_calling for provider in self._providers)

    async def _run(
        self,
        operation: str,
        call: Callable[[LLMProvider], Coroutine[None, None, _T]],
    ) -> _T:
        last_error: Exception | None = None
        attempted_any = False

        for provider in self._providers:
            if self._breaker.is_open(provider.name):
                logger.info("ai_gateway_provider_skipped provider=%s operation=%s reason=circuit_open", provider.name, operation)
                continue

            for retry_index in range(self._max_retries + 1):
                attempted_any = True
                try:
                    result = await call(provider)
                except ToolCallingUnsupportedError:
                    raise
                except LLMProviderError as exc:
                    category = classify_exception(exc.__cause__ or exc)
                    self._breaker.record_failure(provider.name)
                    self._health.record_failure(provider.name, category)
                    last_error = exc
                    logger.warning(
                        "ai_gateway_failure provider=%s operation=%s attempt=%d category=%s",
                        provider.name, operation, retry_index + 1, category.value,
                    )
                    if not is_fallback_eligible(category):
                        raise
                    if is_retryable(category) and retry_index < self._max_retries:
                        delay = min(self._max_delay, self._base_delay * (2 ** retry_index)) + random.uniform(0, self._base_delay)
                        await asyncio.sleep(delay)
                        continue
                    break  # passe au fournisseur suivant
                else:
                    self._breaker.record_success(provider.name)
                    self._health.record_success(provider.name)
                    logger.info("ai_gateway_success provider=%s operation=%s attempt=%d", provider.name, operation, retry_index + 1)
                    return result

        if not attempted_any:
            logger.error("ai_gateway_all_circuits_open operation=%s", operation)
        raise AIProvidersUnavailableError(
            "Avenqo AI est temporairement indisponible. Merci de réessayer dans quelques instants."
        ) from last_error

    async def generate(self, *, system_instruction: str, prompt: str) -> LLMGeneration:
        return await self._run(
            "generate",
            lambda provider: provider.generate(system_instruction=system_instruction, prompt=prompt),
        )

    async def stream(self, *, system_instruction: str, prompt: str) -> AsyncIterator[str]:
        # Le basculement n'est tenté qu'AVANT le premier chunk émis : on ne
        # duplique/mélange jamais une sortie partielle entre deux
        # fournisseurs (limitation documentée — voir docs Phase 32).
        last_error: Exception | None = None
        for provider in self._providers:
            if self._breaker.is_open(provider.name):
                continue
            agen = provider.stream(system_instruction=system_instruction, prompt=prompt)
            try:
                first_chunk = await agen.__anext__()
            except StopAsyncIteration:
                self._breaker.record_success(provider.name)
                self._health.record_success(provider.name)
                return
            except LLMProviderError as exc:
                category = classify_exception(exc.__cause__ or exc)
                self._breaker.record_failure(provider.name)
                self._health.record_failure(provider.name, category)
                last_error = exc
                if not is_fallback_eligible(category):
                    raise
                continue
            self._breaker.record_success(provider.name)
            self._health.record_success(provider.name)
            yield first_chunk
            async for chunk in agen:
                yield chunk
            return
        raise AIProvidersUnavailableError(
            "Avenqo AI est temporairement indisponible. Merci de réessayer dans quelques instants."
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

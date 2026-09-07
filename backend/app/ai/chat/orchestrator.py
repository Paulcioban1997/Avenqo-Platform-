"""Boucle d'orchestration Tool Calling contrôlée (Phase 30, section 17).

Jamais de boucle infinie : `MAX_TOOL_ITERATIONS` et `MAX_TOOLS_PER_REQUEST`
bornent strictement le nombre d'aller-retours LLM ↔ outils pour une seule
question utilisateur.

Phase 30.1 ajoute `run_streaming()`, consommé par `ChatService.stream()` :
mêmes `ToolRegistry`/`ToolExecutor`/boucle que `run()` (aucune deuxième
implémentation), mais exposée comme un flux d'événements (`status`/`final`)
pour piloter le SSE sans jamais révéler les noms d'outils au client.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field, replace

from backend.app.ai.llm.base import LLMProvider
from backend.app.ai.llm.exceptions import LLMProviderError, ToolCallingUnsupportedError
from backend.app.ai.llm.schemas import LLMMessage, LLMProviderAttempt
from backend.app.ai.tools.base import AITool
from backend.app.ai.tools.contracts import ToolCallResult, ToolExecutionContext, ToolResult
from backend.app.ai.tools.exceptions import ToolError
from backend.app.ai.tools.executor import ToolExecutor

MAX_TOOL_ITERATIONS = 5
MAX_TOOLS_PER_REQUEST = 8

STATUS_ANALYZING_BUSINESS_DATA = "Analyzing your business data..."

IsCancelled = Callable[[], Awaitable[bool]]

logger = logging.getLogger("avenqo.ai.orchestrator")


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    content: str
    tool_call_results: tuple[ToolCallResult, ...] = ()
    provider: str = ""
    model: str = ""
    token_usage: dict[str, object] = field(default_factory=dict)
    attempts: tuple[LLMProviderAttempt, ...] = ()
    status_events: tuple[str, ...] = ()
    cancelled: bool = False


@dataclass(frozen=True, slots=True)
class OrchestrationEvent:
    """Événement intermédiaire de `run_streaming` : soit un statut, soit le résultat final."""

    kind: str  # "status" | "final"
    status: str | None = None
    result: OrchestrationResult | None = None


async def _never_cancelled() -> bool:
    return False


def _collect_response_usage(
    totals: dict[str, int],
    attempts: list[LLMProviderAttempt],
    response,
) -> None:
    if response.attempts:
        for attempt in response.attempts:
            attempts.append(replace(attempt, attempt_number=len(attempts) + 1))
            for key in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens"):
                totals[key] += int(getattr(attempt.usage, key, 0) or 0)
        return
    for key in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens"):
        totals[key] += int(response.token_usage.get(key, 0) or 0)


class ToolOrchestrator:
    def __init__(
        self,
        provider: LLMProvider,
        executor: ToolExecutor,
        max_iterations: int = MAX_TOOL_ITERATIONS,
        max_tools_per_request: int = MAX_TOOLS_PER_REQUEST,
    ) -> None:
        self._provider = provider
        self._executor = executor
        self._max_iterations = max_iterations
        self._max_tools_per_request = max_tools_per_request

    async def run(
        self,
        *,
        system_instruction: str,
        user_query: str,
        context: ToolExecutionContext,
        available_tools: tuple[AITool, ...],
    ) -> OrchestrationResult:
        """Exécute la boucle complète et renvoie uniquement le résultat final."""

        result = OrchestrationResult(content="")
        async for event in self.run_streaming(
            system_instruction=system_instruction,
            user_query=user_query,
            context=context,
            available_tools=available_tools,
        ):
            if event.kind == "final":
                result = event.result or result
        return result

    async def run_streaming(
        self,
        *,
        system_instruction: str,
        user_query: str,
        context: ToolExecutionContext,
        available_tools: tuple[AITool, ...],
        is_cancelled: IsCancelled | None = None,
    ) -> AsyncIterator[OrchestrationEvent]:
        """Même boucle que `run()`, mais émet un événement `status` avant chaque
        lot d'exécution d'outils, pour piloter un flux SSE sans jamais exposer
        de détail technique (nom d'outil, arguments, provider) au client."""

        check_cancelled = is_cancelled or _never_cancelled

        if await check_cancelled():
            yield OrchestrationEvent(kind="final", result=OrchestrationResult(content="", cancelled=True))
            return

        if not self._provider.supports_tool_calling or not available_tools:
            generation = await self._provider.generate(system_instruction=system_instruction, prompt=user_query)
            yield OrchestrationEvent(
                kind="final",
                result=OrchestrationResult(
                    content=generation.content,
                    provider=generation.provider,
                    model=generation.model,
                    token_usage=generation.token_usage,
                    attempts=generation.attempts,
                ),
            )
            return

        logger.info(
            "ai_tools_available available_tools_count=%d provider=%s",
            len(available_tools),
            self._provider.name,
        )

        definitions = [tool.definition() for tool in available_tools]
        messages = [LLMMessage(role="user", content=user_query)]
        tool_call_results: list[ToolCallResult] = []
        status_events: list[str] = []
        tools_called = 0
        attempts: list[LLMProviderAttempt] = []
        usage_totals = {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
        }

        for _iteration in range(self._max_iterations):
            if await check_cancelled():
                yield OrchestrationEvent(
                    kind="final",
                    result=OrchestrationResult(
                        content="", tool_call_results=tuple(tool_call_results),
                        token_usage=dict(usage_totals), attempts=tuple(attempts),
                        status_events=tuple(status_events), cancelled=True,
                    ),
                )
                return

            try:
                response = await self._provider.generate_with_tools(
                    system_instruction=system_instruction, messages=messages, tools=definitions
                )
            except (ToolCallingUnsupportedError, LLMProviderError) as exc:
                prior_attempts = getattr(exc, "attempts", ())
                for attempt in prior_attempts:
                    attempts.append(replace(attempt, attempt_number=len(attempts) + 1))
                try:
                    generation = await self._provider.generate(
                        system_instruction=system_instruction,
                        prompt=user_query,
                    )
                except LLMProviderError as fallback_exc:
                    combined = list(attempts)
                    for attempt in fallback_exc.attempts:
                        combined.append(replace(attempt, attempt_number=len(combined) + 1))
                    fallback_exc.attempts = tuple(combined)
                    raise
                _collect_response_usage(usage_totals, attempts, generation)
                yield OrchestrationEvent(
                    kind="final",
                    result=OrchestrationResult(
                        content=generation.content,
                        tool_call_results=tuple(tool_call_results),
                        provider=generation.provider,
                        model=generation.model,
                        token_usage=dict(usage_totals),
                        attempts=tuple(attempts),
                        status_events=tuple(status_events),
                    ),
                )
                return

            _collect_response_usage(usage_totals, attempts, response)

            if not response.tool_calls:
                yield OrchestrationEvent(
                    kind="final",
                    result=OrchestrationResult(
                        content=response.content or "",
                        tool_call_results=tuple(tool_call_results),
                        provider=response.provider,
                        model=response.model,
                        token_usage=dict(usage_totals),
                        attempts=tuple(attempts),
                        status_events=tuple(status_events),
                    ),
                )
                return

            status_events.append(STATUS_ANALYZING_BUSINESS_DATA)
            yield OrchestrationEvent(kind="status", status=STATUS_ANALYZING_BUSINESS_DATA)

            calls = response.tool_calls[: max(0, self._max_tools_per_request - tools_called)]
            # Rejoue le tour "assistant" tel que produit par le mod\u00e8le AVANT les
            # r\u00e9sultats d'outils : les 3 fournisseurs (OpenAI/Anthropic/Gemini)
            # rejettent un message role="tool" qui ne suit pas imm\u00e9diatement un
            # message assistant portant les m\u00eames tool_calls.
            messages.append(
                LLMMessage(role="assistant", content=response.content or "", tool_calls=calls)
            )
            for call in calls:
                if await check_cancelled():
                    yield OrchestrationEvent(
                        kind="final",
                        result=OrchestrationResult(
                            content="", tool_call_results=tuple(tool_call_results),
                            token_usage=dict(usage_totals), attempts=tuple(attempts),
                            status_events=tuple(status_events), cancelled=True,
                        ),
                    )
                    return

                tools_called += 1
                try:
                    result = await self._executor.execute(call.name, context, call.arguments)
                    logger.info("ai_tool_execution selected_tool_name=%s tool_success=true", call.name)
                except ToolError as exc:
                    result = ToolResult(success=False, error=str(exc))
                    logger.info("ai_tool_execution selected_tool_name=%s tool_success=false", call.name)
                tool_call_results.append(ToolCallResult(call=call, result=result))
                messages.append(
                    LLMMessage(
                        role="tool",
                        content=json.dumps(result.data if result.success else {"error": result.error}, default=str),
                        tool_call_id=call.id,
                        name=call.name,
                    )
                )
                if tools_called >= self._max_tools_per_request:
                    break

        yield OrchestrationEvent(
            kind="final",
            result=OrchestrationResult(
                content="I could not complete this request within the allowed number of steps.",
                tool_call_results=tuple(tool_call_results),
                token_usage=dict(usage_totals),
                attempts=tuple(attempts),
                status_events=tuple(status_events),
            ),
        )


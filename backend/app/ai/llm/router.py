"""Deterministic, request-aware model ranking for the Avenqo AI Gateway."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Mapping, Sequence

from backend.app.ai.llm.base import LLMProvider
from backend.app.ai.llm.health import ProviderHealthRegistry, ProviderHealthStatus
from backend.app.ai.llm.model_registry import LLMCapability, LLMModelSpec
from backend.app.ai.llm.schemas import LLMUsage


class LLMTaskType(StrEnum):
    EXTRACTION = "extraction"
    CLASSIFICATION = "classification"
    BUSINESS_QUESTION = "business_question"
    BUSINESS_REASONING = "business_reasoning"
    TOOL_ORCHESTRATION = "tool_orchestration"


class LLMTaskComplexity(StrEnum):
    SIMPLE = "simple"
    NORMAL = "normal"
    COMPLEX = "complex"


@dataclass(frozen=True, slots=True)
class LLMRoutingContext:
    task_type: LLMTaskType = LLMTaskType.BUSINESS_QUESTION
    complexity: LLMTaskComplexity = LLMTaskComplexity.NORMAL
    context_tokens: int = 0
    expected_output_tokens: int = 512
    requires_tool_calling: bool = False
    requires_structured_output: bool = False
    requires_reasoning: bool = False
    plan_code: str | None = None
    remaining_credits: int | None = None
    expected_tool_calls: int = 0
    avenqo_request_id: str = ""

    @property
    def required_capabilities(self) -> frozenset[LLMCapability]:
        required = {LLMCapability.TEXT}
        if self.requires_tool_calling:
            required.add(LLMCapability.TOOL_CALLING)
        if self.requires_structured_output:
            required.add(LLMCapability.STRUCTURED_OUTPUT)
        if self.requires_reasoning:
            required.add(LLMCapability.REASONING)
        return frozenset(required)


class SmartModelRouter:
    """Ranks compatible providers; the gateway still executes one at a time."""

    _HEALTH_PENALTIES = {
        ProviderHealthStatus.HEALTHY: 0,
        ProviderHealthStatus.UNKNOWN: 5,
        ProviderHealthStatus.DEGRADED: 250,
        ProviderHealthStatus.RATE_LIMITED: 500,
        ProviderHealthStatus.UNAVAILABLE: 1_000,
    }
    _LATENCY_PENALTIES = {"fast": 0, "medium": 15, "slow": 35}

    def __init__(
        self,
        specs: Mapping[str, LLMModelSpec],
        health_registry: ProviderHealthRegistry,
    ) -> None:
        self._specs = {provider.casefold(): spec for provider, spec in specs.items()}
        self._health = health_registry

    def rank(
        self,
        providers: Sequence[LLMProvider],
        context: LLMRoutingContext,
    ) -> list[LLMProvider]:
        indexed = list(enumerate(providers))
        compatible = [
            (index, provider)
            for index, provider in indexed
            if self._is_compatible(provider, context)
        ]
        return [
            provider
            for index, provider in sorted(
                compatible,
                key=lambda candidate: self._score(candidate[1], candidate[0], context),
            )
        ]

    def _is_compatible(self, provider: LLMProvider, context: LLMRoutingContext) -> bool:
        spec = self._specs.get(provider.name.casefold())
        if spec is None or not spec.enabled or context.context_tokens > spec.context_window:
            return False
        if not context.required_capabilities.issubset(spec.capabilities):
            return False
        return not context.requires_tool_calling or provider.supports_tool_calling

    def _score(
        self,
        provider: LLMProvider,
        configured_index: int,
        context: LLMRoutingContext,
    ) -> tuple[float, int]:
        spec = self._specs[provider.name.casefold()]
        health_penalty = self._HEALTH_PENALTIES[self._health.status_for(provider.name)]
        latency_penalty = self._LATENCY_PENALTIES.get(spec.latency_class, 50)
        observed_latency_penalty = (self._health.average_latency_ms(provider.name) or 0) / 100
        estimated_usage = LLMUsage(
            provider=spec.provider,
            model=spec.model_id,
            input_tokens=max(context.context_tokens, 1),
            output_tokens=max(context.expected_output_tokens, 1),
            tool_calls=max(context.expected_tool_calls, 0),
        )
        expected_cost = spec.cost_for(estimated_usage)

        if context.complexity == LLMTaskComplexity.COMPLEX:
            task_penalty = (3 - spec.reasoning_strength) * 300
            cost_weight = Decimal("10000")
        elif context.complexity == LLMTaskComplexity.SIMPLE:
            task_penalty = (spec.reasoning_strength - 1) * 20
            cost_weight = Decimal("1000000")
        else:
            task_penalty = abs(spec.reasoning_strength - 2) * 35
            cost_weight = Decimal("50000")

        if context.task_type in {LLMTaskType.EXTRACTION, LLMTaskType.CLASSIFICATION}:
            task_penalty += 0 if LLMCapability.LOW_COST in spec.capabilities else 100
        elif context.task_type == LLMTaskType.BUSINESS_REASONING:
            task_penalty += (3 - spec.reasoning_strength) * 100

        plan = (context.plan_code or "").casefold()
        if plan == "demo":
            cost_weight *= Decimal("2")
        if context.remaining_credits is not None and context.remaining_credits <= 10:
            cost_weight *= Decimal("10")

        score = (
            health_penalty
            + task_penalty
            + latency_penalty
            + observed_latency_penalty
            + spec.fallback_priority
            + float(expected_cost * cost_weight)
        )
        return score, configured_index


def routing_context_for_chat(
    *,
    query: str,
    prompt: str,
    has_tools: bool,
    plan_code: str | None,
    remaining_credits: int | None,
    avenqo_request_id: str,
) -> LLMRoutingContext:
    normalized = query.casefold()
    simple_markers = ("extract", "classif", "categor", "identify", "parse", "format")
    reasoning_markers = (
        "why", "pourquoi", "analy", "compare", "forecast", "prévi", "predict",
        "cause", "recommend", "stratég", "strategy", "explain", "explique",
    )
    if any(marker in normalized for marker in simple_markers):
        task_type = LLMTaskType.EXTRACTION
    elif any(marker in normalized for marker in reasoning_markers):
        task_type = LLMTaskType.BUSINESS_REASONING
    elif has_tools:
        task_type = LLMTaskType.TOOL_ORCHESTRATION
    else:
        task_type = LLMTaskType.BUSINESS_QUESTION

    if task_type == LLMTaskType.EXTRACTION and len(query) < 1_000:
        complexity = LLMTaskComplexity.SIMPLE
    elif any(marker in normalized for marker in reasoning_markers) or len(prompt) > 24_000:
        complexity = LLMTaskComplexity.COMPLEX
    else:
        complexity = LLMTaskComplexity.NORMAL

    return LLMRoutingContext(
        task_type=task_type,
        complexity=complexity,
        context_tokens=max((len(prompt) + 3) // 4, 1),
        requires_tool_calling=has_tools,
        requires_structured_output=has_tools or task_type == LLMTaskType.EXTRACTION,
        requires_reasoning=complexity == LLMTaskComplexity.COMPLEX,
        plan_code=plan_code,
        remaining_credits=remaining_credits,
        expected_tool_calls=1 if has_tools else 0,
        avenqo_request_id=avenqo_request_id,
    )
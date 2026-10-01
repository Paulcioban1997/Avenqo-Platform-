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
    LOW = "low"
    SIMPLE = "low"
    MEDIUM = "medium"
    NORMAL = "medium"
    HIGH = "high"
    COMPLEX = "high"
    REASONING = "reasoning"


@dataclass(frozen=True, slots=True)
class LLMRoutingContext:
    task_type: LLMTaskType = LLMTaskType.BUSINESS_QUESTION
    complexity: LLMTaskComplexity = LLMTaskComplexity.NORMAL
    context_tokens: int = 0
    expected_output_tokens: int = 512
    requires_tool_calling: bool = False
    requires_structured_output: bool = False
    requires_reasoning: bool = False
    requires_streaming: bool = False
    required_modalities: frozenset[str] = frozenset({"text"})
    required_model_capabilities: frozenset[LLMCapability] = frozenset()
    plan_code: str | None = None
    remaining_credits: int | None = None
    expected_tool_calls: int = 0
    avenqo_request_id: str = ""
    tenant_id: str | None = None
    user_id: str | None = None
    conversation_id: str | None = None
    agent_id: str | None = None
    module_id: str | None = None
    idempotency_key: str | None = None

    @property
    def required_capabilities(self) -> frozenset[LLMCapability]:
        required = {LLMCapability.TEXT}
        if self.requires_tool_calling:
            required.add(LLMCapability.TOOL_CALLING)
        if self.requires_structured_output:
            required.add(LLMCapability.STRUCTURED_OUTPUT)
        if self.requires_reasoning:
            required.add(LLMCapability.REASONING)
        required.update(self.required_model_capabilities)
        return frozenset(required)


@dataclass(frozen=True, slots=True)
class LLMRouterDecision:
    selected_provider: str | None
    selected_model: str | None
    eligible_candidates: tuple[tuple[str, str], ...]
    reason: str
    fallback_candidates: tuple[tuple[str, str], ...]


class SmartModelRouter:
    """Ranks registered models independently of business-agent identity."""

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
        specs: Mapping[str | tuple[str, str], LLMModelSpec],
        health_registry: ProviderHealthRegistry,
    ) -> None:
        self._specs: dict[tuple[str, str], LLMModelSpec] = {}
        for key, spec in specs.items():
            if isinstance(key, tuple):
                provider_id, model_id = key
            else:
                provider_id, model_id = key, spec.model_id
            self._specs[(provider_id.casefold(), model_id)] = spec
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
            if self._spec_for(provider) is not None and self._is_compatible(provider, context)
        ]
        return [
            provider
            for index, provider in sorted(
                compatible,
                key=lambda candidate: self._score(candidate[1], candidate[0], context),
            )
        ]

    def decide(
        self,
        providers: Sequence[LLMProvider],
        context: LLMRoutingContext,
    ) -> LLMRouterDecision:
        ranked = self.rank(providers, context)
        candidates = tuple((provider.name, self._model_id(provider)) for provider in ranked)
        if not ranked:
            return LLMRouterDecision(None, None, (), "no_model_satisfies_requirements", ())
        selected = ranked[0]
        return LLMRouterDecision(
            selected_provider=selected.name,
            selected_model=self._model_id(selected),
            eligible_candidates=candidates,
            reason=self._selection_reason(selected, context),
            fallback_candidates=candidates[1:],
        )

    @staticmethod
    def _model_id(provider: LLMProvider) -> str:
        return str(getattr(provider, "model_id", "") or getattr(provider, "_model", ""))

    def _spec_for(self, provider: LLMProvider) -> LLMModelSpec | None:
        model_id = self._model_id(provider)
        if model_id:
            return self._specs.get((provider.name.casefold(), model_id))
        candidates = [
            spec for (provider_id, _), spec in self._specs.items()
            if provider_id == provider.name.casefold()
        ]
        return candidates[0] if len(candidates) == 1 else None

    def model_id_for(self, provider: LLMProvider) -> str | None:
        spec = self._spec_for(provider)
        return spec.model_id if spec is not None else None

    def _is_compatible(self, provider: LLMProvider, context: LLMRoutingContext) -> bool:
        spec = self._spec_for(provider)
        if (
            spec is None
            or not spec.enabled
            or context.context_tokens > spec.context_window
            or context.expected_output_tokens > spec.max_output_tokens
            or not context.required_modalities.issubset(spec.modalities)
            or (context.requires_streaming and not spec.streaming)
            or (context.requires_tool_calling and not spec.tool_calling)
            or (context.requires_structured_output and not spec.structured_output)
        ):
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
        spec = self._spec_for(provider)
        assert spec is not None
        model_id = self._model_id(provider)
        health_key = f"{provider.name}:{model_id}" if model_id else provider.name
        health_status = self._health.status_for(health_key)
        if health_status == ProviderHealthStatus.UNKNOWN and health_key != provider.name:
            health_status = self._health.status_for(provider.name)
        health_penalty = self._HEALTH_PENALTIES[health_status]
        latency_penalty = max(0, 3 - spec.speed_tier) * 15
        observed_latency = self._health.average_latency_ms(health_key)
        if observed_latency is None and health_key != provider.name:
            observed_latency = self._health.average_latency_ms(provider.name)
        observed_latency_penalty = (observed_latency or 0) / 100
        estimated_usage = LLMUsage(
            provider=spec.provider,
            model=spec.model_id,
            input_tokens=max(context.context_tokens, 1),
            output_tokens=max(context.expected_output_tokens, 1),
            tool_calls=max(context.expected_tool_calls, 0),
        )
        expected_cost = spec.cost_for(estimated_usage)

        if context.complexity in {LLMTaskComplexity.HIGH, LLMTaskComplexity.REASONING}:
            task_penalty = (3 - spec.quality_tier) * 300
            cost_weight = Decimal("10000")
        elif context.complexity == LLMTaskComplexity.LOW:
            task_penalty = (spec.quality_tier - 1) * 20
            cost_weight = Decimal("1000000")
        else:
            task_penalty = abs(spec.quality_tier - 2) * 35
            cost_weight = Decimal("50000")

        if spec.task_suitability and context.task_type.value not in spec.task_suitability:
            task_penalty += 200
        if context.task_type in {LLMTaskType.EXTRACTION, LLMTaskType.CLASSIFICATION}:
            task_penalty += 0 if LLMCapability.LOW_COST in spec.capabilities else 100
        elif context.task_type == LLMTaskType.BUSINESS_REASONING:
            task_penalty += (3 - spec.quality_tier) * 100

        plan = (context.plan_code or "").casefold()
        if plan == "demo":
            cost_weight *= Decimal("2")
        elif plan == "professional" and context.complexity in {
            LLMTaskComplexity.HIGH,
            LLMTaskComplexity.REASONING,
        }:
            cost_weight *= Decimal("10")
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

    def _selection_reason(self, provider: LLMProvider, context: LLMRoutingContext) -> str:
        spec = self._spec_for(provider)
        assert spec is not None
        return (
            f"eligible for {context.task_type.value}/{context.complexity.value}; "
            f"capabilities, modalities, context and output limits satisfied; "
            f"quality_tier={spec.quality_tier}, speed_tier={spec.speed_tier}"
        )


def routing_context_for_chat(
    *,
    query: str,
    prompt: str,
    has_tools: bool,
    plan_code: str | None,
    remaining_credits: int | None,
    avenqo_request_id: str,
    requires_streaming: bool = False,
    required_model_capabilities: frozenset[LLMCapability] = frozenset(),
    required_modalities: frozenset[str] = frozenset({"text"}),
    task_complexity: LLMTaskComplexity | None = None,
    tenant_id: str | None = None,
    user_id: str | None = None,
    conversation_id: str | None = None,
    agent_id: str | None = None,
    module_id: str | None = None,
    idempotency_key: str | None = None,
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

    if task_complexity is not None:
        complexity = task_complexity
    elif task_type == LLMTaskType.EXTRACTION and len(query) < 1_000:
        complexity = LLMTaskComplexity.LOW
    elif any(marker in normalized for marker in reasoning_markers):
        complexity = LLMTaskComplexity.COMPLEX
    elif len(prompt) > 24_000 or (has_tools and len(prompt) > 12_000):
        complexity = LLMTaskComplexity.HIGH
    else:
        complexity = LLMTaskComplexity.MEDIUM

    return LLMRoutingContext(
        task_type=task_type,
        complexity=complexity,
        context_tokens=max((len(prompt) + 3) // 4, 1),
        requires_tool_calling=has_tools,
        requires_structured_output=has_tools or task_type == LLMTaskType.EXTRACTION,
        requires_reasoning=(
            complexity in {LLMTaskComplexity.COMPLEX, LLMTaskComplexity.REASONING}
            or task_type == LLMTaskType.BUSINESS_REASONING
        ),
        requires_streaming=requires_streaming,
        required_modalities=required_modalities,
        required_model_capabilities=required_model_capabilities,
        plan_code=plan_code,
        remaining_credits=remaining_credits,
        expected_tool_calls=1 if has_tools else 0,
        avenqo_request_id=avenqo_request_id,
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conversation_id,
        agent_id=agent_id,
        module_id=module_id,
        idempotency_key=idempotency_key,
    )
"""Deterministic provider-cost and Avenqo credit economics simulation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.app.ai.llm.health import ProviderHealthRegistry
from backend.app.ai.llm.model_registry import LLMModelSpec, LLMRateCard, model_spec
from backend.app.ai.llm.router import LLMRoutingContext, LLMTaskComplexity, LLMTaskType, SmartModelRouter
from backend.app.ai.llm.schemas import LLMUsage
from backend.app.ai.usage.service import credits_from_provider_cost
from backend.app.config.settings import Settings
from payments.plans import AICreditPack, AI_CREDIT_PACKS, PlanCode

MINIMUM_SAFE_GROSS_MARGIN = Decimal("0.70")


@dataclass(frozen=True, slots=True)
class WorkloadScenario:
    code: str
    requests: int
    task_type: LLMTaskType
    complexity: LLMTaskComplexity
    input_tokens: int
    output_tokens: int
    context_tokens: int
    tool_calls: int = 0
    fallback: bool = False


@dataclass(frozen=True, slots=True)
class WorkloadResult:
    code: str
    requests: int
    providers: tuple[str, ...]
    provider_cost_usd: Decimal
    avenqo_credits: int


@dataclass(frozen=True, slots=True)
class PackEconomics:
    code: str
    credits: int
    revenue_usd: Decimal
    maximum_provider_cost_usd: Decimal
    gross_contribution_usd: Decimal
    gross_margin: Decimal
    safe_to_sell: bool


@dataclass(frozen=True, slots=True)
class _RoutingCandidate:
    name: str
    supports_tool_calling: bool = True


DEFAULT_SCENARIOS: tuple[WorkloadScenario, ...] = (
    WorkloadScenario(
        "simple_1000",
        1_000,
        LLMTaskType.EXTRACTION,
        LLMTaskComplexity.SIMPLE,
        input_tokens=800,
        output_tokens=120,
        context_tokens=800,
    ),
    WorkloadScenario(
        "normal_1000",
        1_000,
        LLMTaskType.BUSINESS_QUESTION,
        LLMTaskComplexity.NORMAL,
        input_tokens=2_500,
        output_tokens=500,
        context_tokens=2_500,
    ),
    WorkloadScenario(
        "complex_100",
        100,
        LLMTaskType.BUSINESS_REASONING,
        LLMTaskComplexity.COMPLEX,
        input_tokens=8_000,
        output_tokens=1_500,
        context_tokens=8_000,
    ),
    WorkloadScenario(
        "long_context",
        1,
        LLMTaskType.BUSINESS_REASONING,
        LLMTaskComplexity.COMPLEX,
        input_tokens=180_000,
        output_tokens=1_000,
        context_tokens=180_000,
    ),
    WorkloadScenario(
        "tool_calling",
        1,
        LLMTaskType.TOOL_ORCHESTRATION,
        LLMTaskComplexity.NORMAL,
        input_tokens=8_000,
        output_tokens=1_600,
        context_tokens=4_000,
        tool_calls=2,
    ),
    WorkloadScenario(
        "fallback",
        1,
        LLMTaskType.BUSINESS_QUESTION,
        LLMTaskComplexity.NORMAL,
        input_tokens=2_000,
        output_tokens=500,
        context_tokens=2_000,
        fallback=True,
    ),
)

HEAVY_PROFESSIONAL_MULTIPLIERS: dict[str, int] = {
    "simple_1000": 5,
    "normal_1000": 5,
    "complex_100": 5,
    "long_context": 25,
    "tool_calling": 500,
    "fallback": 100,
}


def _registry(settings: Settings) -> tuple[dict[str, LLMModelSpec], LLMRateCard]:
    models = {
        "openai": settings.openai_model,
        "anthropic": settings.anthropic_model,
        "gemini": settings.gemini_model,
    }
    specs = {
        provider: model_spec(provider, model_id, settings.ai_model_rate_card)
        for provider, model_id in models.items()
    }
    return specs, LLMRateCard({
        (spec.provider, spec.model_id): spec
        for spec in specs.values()
    })


def simulate_workloads(settings: Settings) -> dict[str, WorkloadResult]:
    specs, rate_card = _registry(settings)
    router = SmartModelRouter(specs, ProviderHealthRegistry())
    candidates = [_RoutingCandidate(provider) for provider in specs]
    results: dict[str, WorkloadResult] = {}

    for scenario in DEFAULT_SCENARIOS:
        context = LLMRoutingContext(
            task_type=scenario.task_type,
            complexity=scenario.complexity,
            context_tokens=scenario.context_tokens,
            expected_output_tokens=scenario.output_tokens,
            requires_tool_calling=scenario.tool_calls > 0,
            requires_structured_output=(
                scenario.task_type == LLMTaskType.EXTRACTION or scenario.tool_calls > 0
            ),
            requires_reasoning=scenario.complexity == LLMTaskComplexity.COMPLEX,
            plan_code="professional",
            remaining_credits=25_000,
            expected_tool_calls=scenario.tool_calls,
        )
        ranked = router.rank(candidates, context)  # type: ignore[arg-type]
        if not ranked:
            raise RuntimeError(f"No compatible model for scenario {scenario.code}")
        selected = ranked[:2] if scenario.fallback else ranked[:1]
        attempt_costs: list[Decimal] = []
        for index, candidate in enumerate(selected):
            output_tokens = scenario.output_tokens
            if scenario.fallback and index == 0:
                output_tokens = 0
            usage = LLMUsage(
                provider=candidate.name,
                model=specs[candidate.name].model_id,
                input_tokens=scenario.input_tokens,
                output_tokens=output_tokens,
                tool_calls=scenario.tool_calls if index == len(selected) - 1 else 0,
            )
            attempt_costs.append(rate_card.cost_for(usage))
        cost_per_request = sum(attempt_costs, start=Decimal("0"))
        credits_per_request = credits_from_provider_cost(
            cost_per_request,
            settings.avenqo_provider_cost_per_credit_usd,
        )
        results[scenario.code] = WorkloadResult(
            code=scenario.code,
            requests=scenario.requests,
            providers=tuple(candidate.name for candidate in selected),
            provider_cost_usd=cost_per_request * scenario.requests,
            avenqo_credits=credits_per_request * scenario.requests,
        )

    heavy_cost = Decimal("0")
    heavy_credits = 0
    heavy_requests = 0
    heavy_providers: list[str] = []
    for code, multiplier in HEAVY_PROFESSIONAL_MULTIPLIERS.items():
        result = results[code]
        heavy_cost += result.provider_cost_usd * multiplier
        heavy_credits += result.avenqo_credits * multiplier
        heavy_requests += result.requests * multiplier
        for provider in result.providers:
            if provider not in heavy_providers:
                heavy_providers.append(provider)
    results["heavy_professional"] = WorkloadResult(
        code="heavy_professional",
        requests=heavy_requests,
        providers=tuple(heavy_providers),
        provider_cost_usd=heavy_cost,
        avenqo_credits=heavy_credits,
    )
    return results


def professional_pack_economics(settings: Settings) -> dict[str, PackEconomics]:
    results: dict[str, PackEconomics] = {}
    for pack in AI_CREDIT_PACKS:
        if pack.plan_code != PlanCode.PROFESSIONAL:
            continue
        results[pack.code] = _pack_economics(
            pack,
            settings.avenqo_provider_cost_per_credit_usd,
        )
    return results


def _pack_economics(
    pack: AICreditPack,
    provider_cost_per_credit_usd: Decimal,
) -> PackEconomics:
    revenue = Decimal(pack.price_usd)
    maximum_cost = Decimal(pack.credits) * provider_cost_per_credit_usd
    contribution = revenue - maximum_cost
    margin = contribution / revenue
    return PackEconomics(
        code=pack.code,
        credits=pack.credits,
        revenue_usd=revenue,
        maximum_provider_cost_usd=maximum_cost,
        gross_contribution_usd=contribution,
        gross_margin=margin,
        safe_to_sell=margin >= MINIMUM_SAFE_GROSS_MARGIN,
    )

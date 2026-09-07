"""Print a reproducible JSON report for Avenqo AI credit economics."""

from __future__ import annotations

import json
from decimal import Decimal

from backend.app.ai.usage.economics import (
    DEFAULT_SCENARIOS,
    HEAVY_PROFESSIONAL_MULTIPLIERS,
    MINIMUM_SAFE_GROSS_MARGIN,
    professional_pack_economics,
    simulate_workloads,
)
from backend.app.config.settings import get_settings
from payments.plans import PlanCode, get_plan


def _decimal(value: Decimal) -> str:
    return format(value, "f")


def main() -> None:
    settings = get_settings()
    results = simulate_workloads(settings)
    packs = professional_pack_economics(settings)
    included_credits = get_plan(PlanCode.PROFESSIONAL).monthly_ai_credits or 0
    heavy = results["heavy_professional"]

    report = {
        "provider_cost_per_credit_usd": _decimal(
            settings.avenqo_provider_cost_per_credit_usd
        ),
        "minimum_safe_gross_margin": _decimal(MINIMUM_SAFE_GROSS_MARGIN),
        "scenario_assumptions": {
            scenario.code: {
                "requests": scenario.requests,
                "task_type": scenario.task_type.value,
                "complexity": scenario.complexity.value,
                "input_tokens_per_request": scenario.input_tokens,
                "output_tokens_per_request": scenario.output_tokens,
                "context_tokens": scenario.context_tokens,
                "tool_calls_per_request": scenario.tool_calls,
                "fallback": scenario.fallback,
            }
            for scenario in DEFAULT_SCENARIOS
        },
        "scenario_results": {
            code: {
                "requests": result.requests,
                "providers": result.providers,
                "provider_cost_usd": _decimal(result.provider_cost_usd),
                "avenqo_credits": result.avenqo_credits,
            }
            for code, result in results.items()
            if code != "heavy_professional"
        },
        "heavy_professional": {
            "multipliers": HEAVY_PROFESSIONAL_MULTIPLIERS,
            "requests": heavy.requests,
            "providers": heavy.providers,
            "provider_cost_usd": _decimal(heavy.provider_cost_usd),
            "avenqo_credits": heavy.avenqo_credits,
            "monthly_included_credits": included_credits,
            "additional_credits_required": max(
                heavy.avenqo_credits - included_credits,
                0,
            ),
        },
        "professional_packs": {
            code: {
                "credits": pack.credits,
                "revenue_usd": _decimal(pack.revenue_usd),
                "maximum_provider_cost_usd": _decimal(
                    pack.maximum_provider_cost_usd
                ),
                "gross_contribution_usd": _decimal(pack.gross_contribution_usd),
                "gross_margin_percent": _decimal(pack.gross_margin * 100),
                "safe_to_sell": pack.safe_to_sell,
            }
            for code, pack in packs.items()
        },
        "limitations": [
            "Gross margin includes provider token/tool charges only.",
            "Stripe fees, taxes, infrastructure, support, FX, and retries beyond the modeled fallback are excluded.",
            "Rate-card values must be updated when provider prices change.",
        ],
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

from __future__ import annotations

from decimal import Decimal

from backend.app.ai.usage.economics import (
    MINIMUM_SAFE_GROSS_MARGIN,
    professional_pack_economics,
    simulate_workloads,
)
from backend.app.config.settings import Settings


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        AUTH_JWT_SECRET="a" * 32,
        OPENAI_MODEL="gpt-4o-mini",
        ANTHROPIC_MODEL="claude-3-5-sonnet-20241022",
        GEMINI_MODEL="gemini-flash-latest",
        AI_MODEL_RATE_CARD={},
        AVENQO_PROVIDER_COST_PER_CREDIT_USD=Decimal("0.00030"),
    )


def test_default_workloads_use_router_rate_card_and_request_rounding() -> None:
    results = simulate_workloads(_settings())

    assert {
        code: (
            result.requests,
            result.providers,
            result.provider_cost_usd,
            result.avenqo_credits,
        )
        for code, result in results.items()
        if code != "heavy_professional"
    } == {
        "simple_1000": (1_000, ("gemini",), Decimal("0.128000"), 1_000),
        "normal_1000": (1_000, ("openai",), Decimal("0.675000"), 3_000),
        "complex_100": (100, ("openai",), Decimal("0.2100"), 700),
        "long_context": (1, ("gemini",), Decimal("0.0184"), 62),
        "tool_calling": (1, ("openai",), Decimal("0.00216"), 8),
        "fallback": (1, ("openai", "gemini"), Decimal("0.0007"), 3),
    }


def test_heavy_professional_workload_is_a_reproducible_weighted_mix() -> None:
    result = simulate_workloads(_settings())["heavy_professional"]

    assert result.requests == 11_125
    assert result.providers == ("gemini", "openai")
    assert result.provider_cost_usd == Decimal("6.675000")
    assert result.avenqo_credits == 29_350


def test_professional_pack_provider_margins_meet_floor() -> None:
    packs = professional_pack_economics(_settings())

    assert MINIMUM_SAFE_GROSS_MARGIN == Decimal("0.70")
    assert set(packs) == {"professional_6500", "professional_25000"}

    small = packs["professional_6500"]
    assert small.credits == 6_500
    assert small.revenue_usd == Decimal("10")
    assert small.maximum_provider_cost_usd == Decimal("1.95000")
    assert small.gross_contribution_usd == Decimal("8.05000")
    assert small.gross_margin == Decimal("0.80500")
    assert small.safe_to_sell is True

    large = packs["professional_25000"]
    assert large.credits == 25_000
    assert large.revenue_usd == Decimal("25")
    assert large.maximum_provider_cost_usd == Decimal("7.50000")
    assert large.gross_contribution_usd == Decimal("17.50000")
    assert large.gross_margin == Decimal("0.70000")
    assert large.safe_to_sell is True

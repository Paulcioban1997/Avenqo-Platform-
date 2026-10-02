from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.app.ai.llm.schemas import LLMUsage
from backend.app.ai.usage.credit_policy import AvenqoCreditPolicy
from backend.app.ai.usage.pricing import ProviderPricingCatalog, ProviderPricingEntry


def test_pricing_catalog_selects_effective_version_and_preserves_snapshot() -> None:
    catalog = ProviderPricingCatalog([
        ProviderPricingEntry(
            "openai",
            "gpt-test",
            input_cost_per_million_usd=Decimal("1"),
            output_cost_per_million_usd=Decimal("2"),
            version="2026-01",
            effective_from=date(2026, 1, 1),
            effective_to=date(2026, 7, 1),
            source="provider-rate-card",
            last_updated=date(2026, 1, 2),
        ),
        ProviderPricingEntry(
            "openai",
            "gpt-test",
            input_cost_per_million_usd=Decimal("3"),
            output_cost_per_million_usd=Decimal("4"),
            version="2026-07",
            effective_from=date(2026, 7, 1),
            source="provider-rate-card",
            last_updated=date(2026, 7, 2),
        ),
    ])

    historical = catalog.lookup("openai", "gpt-test", on=date(2026, 3, 1))
    current = catalog.lookup("openai", "gpt-test", on=date(2026, 9, 1))

    assert historical.version == "2026-01"
    assert current.version == "2026-07"
    assert catalog.snapshot("openai", "gpt-test", on=date(2026, 3, 1))["version"] == "2026-01"
    assert historical.cost_for(LLMUsage("openai", "gpt-test", input_tokens=1_000, output_tokens=500)) == Decimal("0.002")


def test_pricing_catalog_rejects_unknown_models_without_zero_cost_fallback() -> None:
    with pytest.raises(LookupError, match="Unknown pricing"):
        ProviderPricingCatalog().lookup("unknown", "model")


def test_pricing_catalog_applies_cached_token_prices() -> None:
    entry = ProviderPricingEntry(
        "gemini",
        "flash-test",
        input_cost_per_million_usd=Decimal("1"),
        cached_input_cost_per_million_usd=Decimal("0.25"),
        output_cost_per_million_usd=Decimal("2"),
    )

    cost = entry.cost_for(LLMUsage(
        "gemini",
        "flash-test",
        input_tokens=1_000,
        cached_input_tokens=400,
        output_tokens=500,
    ))

    assert cost == Decimal("0.0017")


def test_pricing_catalog_accounts_for_cached_audio_and_transcription_duration() -> None:
    entry = ProviderPricingEntry(
        "openai",
        "gpt-realtime-test",
        input_cost_per_million_usd=Decimal("1"),
        cached_input_cost_per_million_usd=Decimal("0.25"),
        output_cost_per_million_usd=Decimal("2"),
        audio_input_cost_per_million_usd=Decimal("10"),
        cached_audio_input_cost_per_million_usd=Decimal("1"),
        audio_output_cost_per_million_usd=Decimal("20"),
        audio_input_cost_per_second_usd=Decimal("0.00005"),
        version="2026-10-01",
        source="openai-api-pricing",
    )
    usage = LLMUsage(
        "openai",
        "gpt-realtime-test",
        input_tokens=1_000_100,
        cached_input_tokens=200_020,
        output_tokens=500_050,
        audio_input_units=Decimal("1000000"),
        cached_audio_input_units=Decimal("200000"),
        audio_output_units=Decimal("500000"),
        audio_input_seconds=Decimal("30"),
    )

    assert entry.cost_for(usage) == Decimal("18.201685")
    snapshot = ProviderPricingCatalog([entry]).snapshot("openai", "gpt-realtime-test")
    assert snapshot["version"] == "2026-10-01"
    assert snapshot["cached_audio_input_cost_per_million_usd"] == "1"
    assert snapshot["audio_input_cost_per_second_usd"] == "0.00005"


def test_credit_policy_preserves_default_conversion_and_enforces_guardrail() -> None:
    policy = AvenqoCreditPolicy()
    assert policy.provider_cost_to_credits(Decimal("0.00030")) == 1
    assert policy.reserve_for_cost(None) == 1

    guarded = AvenqoCreditPolicy(max_estimated_provider_cost_usd=Decimal("0.01"))
    with pytest.raises(ValueError, match="exceeds the configured request budget"):
        guarded.validate_estimate(Decimal("0.0101"))

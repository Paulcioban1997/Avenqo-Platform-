"""Centralized internal conversion and spend guardrails for Avenqo credits."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING


@dataclass(frozen=True, slots=True)
class AvenqoCreditPolicy:
    provider_cost_per_credit_usd: Decimal = Decimal("0.00030")
    minimum_charge_credits: int = 1
    minimum_reserve_credits: int = 1
    margin_protection_factor: Decimal = Decimal("1")
    max_estimated_provider_cost_usd: Decimal | None = None
    max_input_tokens_per_request: int | None = None
    max_output_tokens_per_request: int | None = None
    max_request_credits: int | None = None
    max_session_credits: int | None = None
    max_session_cost_usd: Decimal | None = None
    max_company_monthly_cost_usd: Decimal | None = None
    rounding: str = "ceiling"

    def __post_init__(self) -> None:
        if self.provider_cost_per_credit_usd <= 0:
            raise ValueError("Provider cost per credit must be positive")
        if self.minimum_charge_credits < 0 or self.minimum_reserve_credits < 1:
            raise ValueError("Credit minimums are invalid")
        if self.margin_protection_factor <= 0:
            raise ValueError("Margin protection factor must be positive")
        for value in (
            self.max_estimated_provider_cost_usd,
            self.max_input_tokens_per_request,
            self.max_output_tokens_per_request,
            self.max_request_credits,
            self.max_session_credits,
            self.max_session_cost_usd,
            self.max_company_monthly_cost_usd,
        ):
            if value is not None and value <= 0:
                raise ValueError("Credit guardrails must be positive when configured")
        if self.rounding != "ceiling":
            raise ValueError("Only ceiling credit rounding is supported")

    def provider_cost_to_credits(self, provider_cost_usd: Decimal) -> int:
        if provider_cost_usd <= 0:
            return 0
        protected_cost = provider_cost_usd * self.margin_protection_factor
        credits = int(
            (protected_cost / self.provider_cost_per_credit_usd).to_integral_value(
                rounding=ROUND_CEILING,
            )
        )
        return max(credits, self.minimum_charge_credits)

    def reserve_for_cost(self, provider_cost_usd: Decimal | None) -> int:
        if provider_cost_usd is None:
            return self.minimum_reserve_credits
        return max(self.provider_cost_to_credits(provider_cost_usd), self.minimum_reserve_credits)

    def validate_estimate(self, provider_cost_usd: Decimal | None) -> None:
        if (
            provider_cost_usd is not None
            and self.max_estimated_provider_cost_usd is not None
            and provider_cost_usd > self.max_estimated_provider_cost_usd
        ):
            raise ValueError("Estimated AI provider cost exceeds the configured request budget")
        if (
            provider_cost_usd is not None
            and self.max_request_credits is not None
            and self.provider_cost_to_credits(provider_cost_usd) > self.max_request_credits
        ):
            raise ValueError("Estimated AI credits exceed the configured request budget")

    def validate_session_credits(self, session_credits: int) -> None:
        if self.max_session_credits is not None and session_credits > self.max_session_credits:
            raise ValueError(f"Session AI credit limit exceeded ({self.max_session_credits} max)")

    def validate_session_cost(self, session_cost_usd: Decimal) -> None:
        if self.max_session_cost_usd is not None and session_cost_usd > self.max_session_cost_usd:
            raise ValueError(f"Session AI cost limit exceeded (${self.max_session_cost_usd} max)")

    def validate_company_cost(self, company_monthly_cost_usd: Decimal) -> None:
        if (
            self.max_company_monthly_cost_usd is not None
            and company_monthly_cost_usd > self.max_company_monthly_cost_usd
        ):
            raise ValueError("Company monthly AI budget ceiling reached")


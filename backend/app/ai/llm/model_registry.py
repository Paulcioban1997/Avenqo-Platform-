"""Provider-agnostic registry for generative LLM capabilities.

This registry is intentionally separate from the tenant ML ModelRegistry.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum
from typing import Mapping

from backend.app.ai.llm.schemas import LLMUsage


class LLMCapability(StrEnum):
    TEXT = "text"
    TOOL_CALLING = "tool_calling"
    STRUCTURED_OUTPUT = "structured_output"
    REASONING = "reasoning"
    LONG_CONTEXT = "long_context"
    FAST_RESPONSE = "fast_response"
    LOW_COST = "low_cost"
    VISION = "vision"


@dataclass(frozen=True, slots=True)
class LLMModelSpec:
    provider: str
    model_id: str
    display_name: str
    capabilities: frozenset[LLMCapability]
    context_window: int
    estimated_cost_class: str
    latency_class: str
    fallback_priority: int
    enabled: bool = True
    input_cost_per_million_usd: Decimal = Decimal("0")
    cached_input_cost_per_million_usd: Decimal = Decimal("0")
    output_cost_per_million_usd: Decimal = Decimal("0")
    tool_call_cost_usd: Decimal = Decimal("0")
    reasoning_strength: int = 1

    def cost_for(self, usage: LLMUsage) -> Decimal:
        cached_tokens = min(usage.cached_input_tokens, usage.input_tokens)
        uncached_tokens = max(usage.input_tokens - cached_tokens, 0)
        token_cost = (
            Decimal(uncached_tokens) * self.input_cost_per_million_usd
            + Decimal(cached_tokens) * self.cached_input_cost_per_million_usd
            + Decimal(usage.output_tokens) * self.output_cost_per_million_usd
        ) / Decimal(1_000_000)
        return token_cost + Decimal(usage.tool_calls) * self.tool_call_cost_usd


_DEFAULT_RATES: dict[tuple[str, str], dict[str, str]] = {
    ("openai", "gpt-4o-mini"): {
        "input_cost_per_million_usd": "0.15",
        "cached_input_cost_per_million_usd": "0.075",
        "output_cost_per_million_usd": "0.60",
        "tool_call_cost_usd": "0",
    },
    ("anthropic", "claude-3-5-sonnet-20241022"): {
        "input_cost_per_million_usd": "3.00",
        "cached_input_cost_per_million_usd": "0.30",
        "output_cost_per_million_usd": "15.00",
        "tool_call_cost_usd": "0",
    },
    ("gemini", "gemini-flash-latest"): {
        "input_cost_per_million_usd": "0.10",
        "cached_input_cost_per_million_usd": "0.025",
        "output_cost_per_million_usd": "0.40",
        "tool_call_cost_usd": "0",
    },
}

_PROVIDER_FALLBACK_RATES: dict[str, dict[str, str]] = {
    "openai": _DEFAULT_RATES[("openai", "gpt-4o-mini")],
    "anthropic": _DEFAULT_RATES[("anthropic", "claude-3-5-sonnet-20241022")],
    "gemini": _DEFAULT_RATES[("gemini", "gemini-flash-latest")],
}


def _configured_values(
    provider: str,
    model_id: str,
    overrides: Mapping[str, Mapping[str, object]] | None,
) -> Mapping[str, object]:
    if not overrides:
        return {}
    return (
        overrides.get(f"{provider}:{model_id}")
        or overrides.get(model_id)
        or overrides.get(provider)
        or {}
    )


def _decimal_value(values: Mapping[str, object], key: str, default: str) -> Decimal:
    value = Decimal(str(values.get(key, default)))
    if value < 0:
        raise ValueError(f"Model rate '{key}' cannot be negative")
    return value


def _enabled_value(values: Mapping[str, object]) -> bool:
    value = values.get("enabled", True)
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "on"}
    return bool(value)


def model_spec(
    provider: str,
    model_id: str,
    overrides: Mapping[str, Mapping[str, object]] | None = None,
) -> LLMModelSpec:
    provider = provider.casefold()
    rates = _DEFAULT_RATES.get((provider, model_id), _PROVIDER_FALLBACK_RATES.get(provider, {}))
    configured = _configured_values(provider, model_id, overrides)
    rate_kwargs = {
        "enabled": _enabled_value(configured),
        "input_cost_per_million_usd": _decimal_value(
            configured, "input_cost_per_million_usd", rates.get("input_cost_per_million_usd", "0")
        ),
        "cached_input_cost_per_million_usd": _decimal_value(
            configured,
            "cached_input_cost_per_million_usd",
            rates.get("cached_input_cost_per_million_usd", "0"),
        ),
        "output_cost_per_million_usd": _decimal_value(
            configured, "output_cost_per_million_usd", rates.get("output_cost_per_million_usd", "0")
        ),
        "tool_call_cost_usd": _decimal_value(
            configured, "tool_call_cost_usd", rates.get("tool_call_cost_usd", "0")
        ),
    }
    common = {
        LLMCapability.TEXT,
        LLMCapability.TOOL_CALLING,
        LLMCapability.STRUCTURED_OUTPUT,
    }
    if provider == "openai":
        capabilities = common | {LLMCapability.FAST_RESPONSE, LLMCapability.LOW_COST, LLMCapability.REASONING}
        return LLMModelSpec(
            provider, model_id, "OpenAI", frozenset(capabilities), 128_000,
            "low", "fast", 10, reasoning_strength=2, **rate_kwargs,
        )
    if provider == "anthropic":
        capabilities = common | {LLMCapability.REASONING, LLMCapability.LONG_CONTEXT}
        return LLMModelSpec(
            provider, model_id, "Anthropic Claude", frozenset(capabilities), 200_000,
            "high", "medium", 20, reasoning_strength=3, **rate_kwargs,
        )
    if provider == "gemini":
        capabilities = common | {
            LLMCapability.FAST_RESPONSE,
            LLMCapability.LOW_COST,
            LLMCapability.LONG_CONTEXT,
            LLMCapability.REASONING,
            LLMCapability.VISION,
        }
        return LLMModelSpec(
            provider, model_id, "Google Gemini", frozenset(capabilities), 1_000_000,
            "low", "fast", 30, reasoning_strength=1, **rate_kwargs,
        )
    raise ValueError(f"Unsupported LLM provider: {provider}")


class LLMRateCard:
    """Single source of model prices used for routing and historical metering."""

    def __init__(self, specs: Mapping[tuple[str, str], LLMModelSpec]) -> None:
        self._specs = dict(specs)

    @classmethod
    def from_models(
        cls,
        models: Mapping[str, str],
        overrides: Mapping[str, Mapping[str, object]] | None = None,
    ) -> "LLMRateCard":
        return cls({
            (provider.casefold(), model_id): model_spec(provider, model_id, overrides)
            for provider, model_id in models.items()
        })

    def spec_for(self, provider: str, model_id: str) -> LLMModelSpec:
        key = (provider.casefold(), model_id)
        exact = self._specs.get(key)
        if exact is not None:
            return exact
        provider_specs = [
            spec for (provider_code, _), spec in self._specs.items()
            if provider_code == provider.casefold()
        ]
        if len(provider_specs) == 1:
            return replace(provider_specs[0], model_id=model_id)
        return model_spec(provider, model_id)

    def cost_for(self, usage: LLMUsage) -> Decimal:
        return self.spec_for(usage.provider, usage.model).cost_for(usage)
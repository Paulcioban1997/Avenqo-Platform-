"""Provider-agnostic registry for generative LLM capabilities.

This registry is intentionally separate from the tenant ML ModelRegistry.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from enum import StrEnum
from collections.abc import Iterable, Mapping, Sequence

from backend.app.ai.llm.schemas import LLMUsage
from backend.app.ai.usage.pricing import ProviderPricingCatalog, ProviderPricingEntry


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
    cached_output_cost_per_million_usd: Decimal = Decimal("0")
    reasoning_cost_per_million_usd: Decimal = Decimal("0")
    reasoning_strength: int = 1
    modalities: frozenset[str] = frozenset({"text"})
    streaming: bool = True
    tool_calling: bool = True
    structured_output: bool = True
    max_output_tokens: int = 8192
    quality_tier: int = 2
    speed_tier: int = 2
    task_suitability: frozenset[str] = frozenset()
    request_timeout_seconds: float = 60.0
    max_retries: int = 2
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 4.0
    pricing_version: str = "default"
    pricing_source: str = "configuration"
    pricing_effective_from: str = ""

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

_KNOWN_MODEL_PROFILES: dict[tuple[str, str], dict[str, object]] = {
    ("openai", "gpt-4o-mini"): {
        "capabilities": ["text", "tool_calling", "structured_output", "fast_response", "low_cost", "reasoning"],
        "context_window": 128_000,
        "max_output_tokens": 16_384,
        "quality_tier": 2,
        "speed_tier": 1,
        "task_suitability": ["classification", "extraction", "business_question", "tool_orchestration"],
    },
    ("anthropic", "claude-3-5-sonnet-20241022"): {
        "capabilities": ["text", "tool_calling", "structured_output", "reasoning", "long_context"],
        "context_window": 200_000,
        "max_output_tokens": 8_192,
        "quality_tier": 3,
        "speed_tier": 2,
        "task_suitability": ["business_question", "business_reasoning", "tool_orchestration"],
    },
    ("gemini", "gemini-flash-latest"): {
        "capabilities": ["text", "tool_calling", "structured_output", "fast_response", "low_cost", "long_context", "reasoning", "vision"],
        "context_window": 1_000_000,
        "max_output_tokens": 8_192,
        "quality_tier": 1,
        "speed_tier": 1,
        "task_suitability": ["classification", "extraction", "business_question", "tool_orchestration", "business_reasoning"],
    },
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
    metadata: Mapping[str, object] | None = None,
) -> LLMModelSpec:
    provider = provider.casefold()
    profile = dict(_KNOWN_MODEL_PROFILES.get((provider, model_id), {}))
    if metadata:
        profile.update(metadata)
    if not profile:
        raise ValueError(
            f"Model '{provider}:{model_id}' requires explicit capability and limit metadata"
        )
    required_profile = {"capabilities", "context_window", "max_output_tokens"}
    missing = required_profile - profile.keys()
    if missing:
        raise ValueError(
            f"Model '{provider}:{model_id}' is missing metadata: {', '.join(sorted(missing))}"
        )
    configured = _configured_values(provider, model_id, overrides)
    rate_kwargs = {
        "enabled": _enabled_value(configured),
        "input_cost_per_million_usd": _decimal_value(
            configured,
            "input_cost_per_million_usd",
            str(profile.get("input_cost_per_million_usd", _DEFAULT_RATES.get((provider, model_id), {}).get("input_cost_per_million_usd", "0"))),
        ),
        "cached_input_cost_per_million_usd": _decimal_value(
            configured,
            "cached_input_cost_per_million_usd",
            str(profile.get("cached_input_cost_per_million_usd", _DEFAULT_RATES.get((provider, model_id), {}).get("cached_input_cost_per_million_usd", "0"))),
        ),
        "output_cost_per_million_usd": _decimal_value(
            configured,
            "output_cost_per_million_usd",
            str(profile.get("output_cost_per_million_usd", _DEFAULT_RATES.get((provider, model_id), {}).get("output_cost_per_million_usd", "0"))),
        ),
        "tool_call_cost_usd": _decimal_value(
            configured,
            "tool_call_cost_usd",
            str(profile.get("tool_call_cost_usd", _DEFAULT_RATES.get((provider, model_id), {}).get("tool_call_cost_usd", "0"))),
        ),
        "cached_output_cost_per_million_usd": _decimal_value(
            configured,
            "cached_output_cost_per_million_usd",
            str(profile.get("cached_output_cost_per_million_usd", "0")),
        ),
        "reasoning_cost_per_million_usd": _decimal_value(
            configured,
            "reasoning_cost_per_million_usd",
            str(profile.get("reasoning_cost_per_million_usd", "0")),
        ),
    }
    capabilities = frozenset(LLMCapability(value) for value in profile["capabilities"])
    return LLMModelSpec(
        provider=provider,
        model_id=model_id,
        display_name=str(profile.get("display_name", provider)),
        capabilities=capabilities,
        context_window=int(profile["context_window"]),
        estimated_cost_class=str(profile.get("estimated_cost_class", "unknown")),
        latency_class=str(profile.get("latency_class", "medium")),
        fallback_priority=int(profile.get("fallback_priority", 0)),
        reasoning_strength=int(profile.get("reasoning_strength", 1)),
        modalities=frozenset(str(value) for value in profile.get("modalities", ("text",))),
        streaming=bool(profile.get("streaming", True)),
        tool_calling=bool(profile.get("tool_calling", LLMCapability.TOOL_CALLING in capabilities)),
        structured_output=bool(profile.get("structured_output", LLMCapability.STRUCTURED_OUTPUT in capabilities)),
        max_output_tokens=int(profile["max_output_tokens"]),
        quality_tier=int(profile.get("quality_tier", 1)),
        speed_tier=int(profile.get("speed_tier", 2)),
        task_suitability=frozenset(str(value) for value in profile.get("task_suitability", ())),
        request_timeout_seconds=float(profile.get("request_timeout_seconds", 60.0)),
        max_retries=int(profile.get("max_retries", 2)),
        base_delay_seconds=float(profile.get("base_delay_seconds", 0.5)),
        max_delay_seconds=float(profile.get("max_delay_seconds", 4.0)),
        pricing_version=str(profile.get("pricing_version", "default")),
        pricing_source=str(profile.get("pricing_source", "configuration")),
        pricing_effective_from=str(profile.get("pricing_effective_from", "")),
        **rate_kwargs,
    )


class LLMModelRegistry:
    """Registry of enabled, provider-neutral model capability definitions."""

    def __init__(self, specs: Iterable[LLMModelSpec] = ()) -> None:
        self._specs: dict[tuple[str, str], LLMModelSpec] = {}
        for spec in specs:
            self.register(spec)

    def register(self, spec: LLMModelSpec) -> None:
        key = (spec.provider.casefold(), spec.model_id)
        if key in self._specs:
            raise ValueError(f"Model '{key[0]}:{key[1]}' is already registered")
        if spec.context_window < 1 or spec.max_output_tokens < 1:
            raise ValueError("Model token limits must be positive")
        if spec.request_timeout_seconds <= 0 or spec.max_retries < 0:
            raise ValueError("Model timeout and retry policy are invalid")
        self._specs[key] = spec

    def get(self, provider_id: str, model_id: str) -> LLMModelSpec | None:
        return self._specs.get((provider_id.casefold(), model_id))

    def list_all(self, *, enabled_only: bool = False) -> tuple[LLMModelSpec, ...]:
        items = tuple(self._specs.values())
        return tuple(spec for spec in items if spec.enabled) if enabled_only else items

    def list_for_provider(
        self,
        provider_id: str,
        *,
        enabled_only: bool = False,
    ) -> tuple[LLMModelSpec, ...]:
        return tuple(
            spec for spec in self.list_all(enabled_only=enabled_only)
            if spec.provider.casefold() == provider_id.casefold()
        )


class LLMRateCard:
    """Single source of model prices used for routing and historical metering."""

    def __init__(self, specs: Mapping[tuple[str, str], LLMModelSpec]) -> None:
        self._specs = dict(specs)
        self._pricing = ProviderPricingCatalog(
            ProviderPricingEntry(
                provider_id=spec.provider,
                model_id=spec.model_id,
                input_cost_per_million_usd=spec.input_cost_per_million_usd,
                cached_input_cost_per_million_usd=spec.cached_input_cost_per_million_usd,
                output_cost_per_million_usd=spec.output_cost_per_million_usd,
                cached_output_cost_per_million_usd=spec.cached_output_cost_per_million_usd,
                reasoning_cost_per_million_usd=spec.reasoning_cost_per_million_usd,
                tool_call_cost_usd=spec.tool_call_cost_usd,
                version=spec.pricing_version,
                effective_from=(
                    date.fromisoformat(spec.pricing_effective_from)
                    if spec.pricing_effective_from
                    else date.min
                ),
                source=spec.pricing_source,
            )
            for spec in self._specs.values()
        )

    @classmethod
    def from_models(
        cls,
        models: Mapping[str, str | Sequence[str]],
        overrides: Mapping[str, Mapping[str, object]] | None = None,
        metadata: Mapping[str, Mapping[str, object]] | None = None,
    ) -> "LLMRateCard":
        specs = {}
        for provider, model_ids in models.items():
            ids = (model_ids,) if isinstance(model_ids, str) else tuple(model_ids)
            for model_id in ids:
                key = f"{provider.casefold()}:{model_id}"
                specs[(provider.casefold(), model_id)] = model_spec(
                    provider,
                    model_id,
                    overrides,
                    (metadata or {}).get(key),
                )
        return cls(specs)

    @classmethod
    def from_specs(cls, specs: Iterable[LLMModelSpec]) -> "LLMRateCard":
        return cls({(spec.provider.casefold(), spec.model_id): spec for spec in specs})

    def spec_for(self, provider: str, model_id: str) -> LLMModelSpec:
        key = (provider.casefold(), model_id)
        exact = self._specs.get(key)
        if exact is not None:
            return exact
        return model_spec(provider, model_id)

    def get(self, provider: str, model_id: str) -> LLMModelSpec | None:
        return self._specs.get((provider.casefold(), model_id))

    def specs_for_provider(self, provider: str) -> tuple[LLMModelSpec, ...]:
        return tuple(
            spec for (provider_code, _), spec in self._specs.items()
            if provider_code == provider.casefold()
        )

    def cost_for(self, usage: LLMUsage) -> Decimal:
        return self.pricing_for(usage.provider, usage.model).cost_for(usage)

    def pricing_for(self, provider: str, model_id: str) -> ProviderPricingEntry:
        try:
            return self._pricing.lookup(provider, model_id)
        except LookupError:
            candidates = self.specs_for_provider(provider)
            if len(candidates) != 1:
                raise
            return self._pricing.lookup(provider, candidates[0].model_id)
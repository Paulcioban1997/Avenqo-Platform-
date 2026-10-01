"""Versioned provider pricing for the provider-neutral usage engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from backend.app.ai.llm.schemas import LLMUsage


@dataclass(frozen=True, slots=True)
class ProviderPricingEntry:
    provider_id: str
    model_id: str
    currency: str = "USD"
    input_cost_per_million_usd: Decimal = Decimal("0")
    cached_input_cost_per_million_usd: Decimal = Decimal("0")
    output_cost_per_million_usd: Decimal = Decimal("0")
    cached_output_cost_per_million_usd: Decimal = Decimal("0")
    reasoning_cost_per_million_usd: Decimal = Decimal("0")
    audio_input_cost_per_unit_usd: Decimal = Decimal("0")
    audio_output_cost_per_unit_usd: Decimal = Decimal("0")
    tool_call_cost_usd: Decimal = Decimal("0")
    version: str = "default"
    effective_from: date = date.min
    effective_to: date | None = None
    source: str = "configuration"
    last_updated: date = date.today()

    def __post_init__(self) -> None:
        if self.currency != "USD":
            raise ValueError("Only USD provider pricing is currently supported")
        for field_name in (
            "input_cost_per_million_usd",
            "cached_input_cost_per_million_usd",
            "output_cost_per_million_usd",
            "cached_output_cost_per_million_usd",
            "reasoning_cost_per_million_usd",
            "audio_input_cost_per_unit_usd",
            "audio_output_cost_per_unit_usd",
            "tool_call_cost_usd",
        ):
            if getattr(self, field_name) < 0:
                raise ValueError(f"Pricing value '{field_name}' cannot be negative")
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("Pricing effective_to must be after effective_from")

    def applies_on(self, on: date) -> bool:
        return self.effective_from <= on and (
            self.effective_to is None or on < self.effective_to
        )

    def cost_for(self, usage: LLMUsage) -> Decimal:
        cached_input = min(max(usage.cached_input_tokens, 0), max(usage.input_tokens, 0))
        uncached_input = max(usage.input_tokens - cached_input, 0)
        cached_output = min(max(usage.cached_output_tokens, 0), max(usage.output_tokens, 0))
        uncached_output = max(usage.output_tokens - cached_output, 0)
        return (
            Decimal(uncached_input) * self.input_cost_per_million_usd
            + Decimal(cached_input) * self.cached_input_cost_per_million_usd
            + Decimal(uncached_output) * self.output_cost_per_million_usd
            + Decimal(cached_output) * self.cached_output_cost_per_million_usd
            + Decimal(max(usage.reasoning_tokens, 0)) * self.reasoning_cost_per_million_usd
        ) / Decimal(1_000_000) + (
            Decimal(str(usage.audio_input_units)) * self.audio_input_cost_per_unit_usd
            + Decimal(str(usage.audio_output_units)) * self.audio_output_cost_per_unit_usd
            + Decimal(max(usage.tool_calls, 0)) * self.tool_call_cost_usd
        )


class ProviderPricingCatalog:
    """Immutable-by-snapshot pricing lookup; replacing entries never rewrites history."""

    def __init__(self, entries: Iterable[ProviderPricingEntry] = ()) -> None:
        self._entries: dict[tuple[str, str], tuple[ProviderPricingEntry, ...]] = {}
        for entry in entries:
            self.register(entry)

    def register(self, entry: ProviderPricingEntry) -> None:
        key = (entry.provider_id.casefold(), entry.model_id)
        versions = self._entries.setdefault(key, ())
        if any(existing.version == entry.version for existing in versions):
            raise ValueError(f"Pricing version already exists for {key[0]}:{key[1]}")
        self._entries[key] = tuple(sorted((*versions, entry), key=lambda item: item.effective_from))

    def lookup(self, provider_id: str, model_id: str, *, on: date | None = None) -> ProviderPricingEntry:
        entries = self._entries.get((provider_id.casefold(), model_id), ())
        if not entries:
            raise LookupError(f"Unknown pricing for '{provider_id}:{model_id}'")
        effective_on = on or date.today()
        matches = tuple(entry for entry in entries if entry.applies_on(effective_on))
        if len(matches) != 1:
            raise LookupError(f"No unambiguous pricing for '{provider_id}:{model_id}' on {effective_on}")
        return matches[0]

    def snapshot(self, provider_id: str, model_id: str, *, on: date | None = None) -> dict[str, object]:
        entry = self.lookup(provider_id, model_id, on=on)
        return {
            "provider_id": entry.provider_id,
            "model_id": entry.model_id,
            "currency": entry.currency,
            "version": entry.version,
            "effective_from": entry.effective_from.isoformat(),
            "effective_to": entry.effective_to.isoformat() if entry.effective_to else None,
            "source": entry.source,
            "last_updated": entry.last_updated.isoformat(),
            "input_cost_per_million_usd": str(entry.input_cost_per_million_usd),
            "cached_input_cost_per_million_usd": str(entry.cached_input_cost_per_million_usd),
            "output_cost_per_million_usd": str(entry.output_cost_per_million_usd),
            "cached_output_cost_per_million_usd": str(entry.cached_output_cost_per_million_usd),
            "reasoning_cost_per_million_usd": str(entry.reasoning_cost_per_million_usd),
            "audio_input_cost_per_unit_usd": str(entry.audio_input_cost_per_unit_usd),
            "audio_output_cost_per_unit_usd": str(entry.audio_output_cost_per_unit_usd),
            "tool_call_cost_usd": str(entry.tool_call_cost_usd),
        }

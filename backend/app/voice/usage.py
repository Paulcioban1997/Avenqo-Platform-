"""Normalize actual Realtime SDK usage into Phase 4 provider attempts."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from dataclasses import dataclass, field, replace
import hashlib
from typing import Any
from uuid import UUID

from backend.app.ai.llm.schemas import LLMProviderAttempt, LLMUsage
from backend.app.ai.request_identity import resolve_ai_request_id
from backend.app.ai.usage.pricing import ProviderPricingCatalog, ProviderPricingEntry
from backend.app.ai.usage.service import AIUsageService

_OPENAI_PRICING_SOURCE = "https://developers.openai.com/api/docs/pricing/"
_PRICING_VERSION = "2026-10-01"
_PRICING_EFFECTIVE_FROM = date(2026, 10, 1)


def voice_pricing_catalog(rate_card: dict[str, dict[str, object]] | None = None) -> ProviderPricingCatalog:
    configured = rate_card or {}
    entries = []
    defaults = {
        "gpt-realtime-2.1": {
            "input_cost_per_million_usd": "4",
            "cached_input_cost_per_million_usd": "0.4",
            "output_cost_per_million_usd": "24",
            "audio_input_cost_per_million_usd": "32",
            "cached_audio_input_cost_per_million_usd": "0.4",
            "audio_output_cost_per_million_usd": "64",
        },
        "gpt-realtime": {
            "input_cost_per_million_usd": "4",
            "cached_input_cost_per_million_usd": "0.4",
            "output_cost_per_million_usd": "16",
            "audio_input_cost_per_million_usd": "32",
            "cached_audio_input_cost_per_million_usd": "0.4",
            "audio_output_cost_per_million_usd": "64",
        },
        "gpt-4o-mini-transcribe": {
            "input_cost_per_million_usd": "1.25",
            "output_cost_per_million_usd": "5",
            "audio_input_cost_per_million_usd": "1.25",
            "audio_input_cost_per_second_usd": "0.00005",
        },
        "gpt-4o-mini-tts": {
            "input_cost_per_million_usd": "0.6",
            "audio_output_cost_per_million_usd": "12",
        },
    }
    for model, defaults_for_model in defaults.items():
        override = (
            configured.get(f"openai:{model}")
            or configured.get(model)
            or configured.get("openai")
            or {}
        )
        if not isinstance(override, dict):
            override = {}
        rates = {**defaults_for_model, **override}
        entries.append(ProviderPricingEntry(
            provider_id="openai",
            model_id=model,
            input_cost_per_million_usd=Decimal(str(rates.get("input_cost_per_million_usd", "0"))),
            cached_input_cost_per_million_usd=Decimal(str(rates.get("cached_input_cost_per_million_usd", "0"))),
            output_cost_per_million_usd=Decimal(str(rates.get("output_cost_per_million_usd", "0"))),
            cached_output_cost_per_million_usd=Decimal(str(rates.get("cached_output_cost_per_million_usd", "0"))),
            audio_input_cost_per_million_usd=Decimal(str(rates.get("audio_input_cost_per_million_usd", "0"))),
            cached_audio_input_cost_per_million_usd=Decimal(str(rates.get("cached_audio_input_cost_per_million_usd", "0"))),
            audio_output_cost_per_million_usd=Decimal(str(rates.get("audio_output_cost_per_million_usd", "0"))),
            audio_input_cost_per_second_usd=Decimal(str(rates.get("audio_input_cost_per_second_usd", "0"))),
            version=str(rates.get("pricing_version", _PRICING_VERSION)),
            effective_from=date.fromisoformat(str(rates.get("pricing_effective_from", _PRICING_EFFECTIVE_FROM.isoformat()))),
            source=str(rates.get("pricing_source", _OPENAI_PRICING_SOURCE)),
        ))
    return ProviderPricingCatalog(entries)


def _value(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _nonnegative_int(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _attempt(
    *,
    catalog: ProviderPricingCatalog,
    model: str,
    operation: str,
    raw_usage: LLMUsage,
    attempt_number: int,
    request_id: str,
    provider_request_id: str | None,
    tenant_id: str,
    user_id: str | None = None,
    conversation_id: str | None = None,
    agent_id: str | None = None,
    module_id: str | None = None,
    success: bool = True,
    failure_category: str | None = None,
    request_status: str = "completed",
) -> LLMProviderAttempt:
    pricing = catalog.lookup("openai", model)
    usage = LLMUsage(
        provider="openai",
        model=model,
        input_tokens=raw_usage.input_tokens,
        cached_input_tokens=raw_usage.cached_input_tokens,
        output_tokens=raw_usage.output_tokens,
        cached_output_tokens=raw_usage.cached_output_tokens,
        text_input_tokens=raw_usage.text_input_tokens,
        cached_text_input_tokens=raw_usage.cached_text_input_tokens,
        text_output_tokens=raw_usage.text_output_tokens,
        audio_input_units=raw_usage.audio_input_units,
        cached_audio_input_units=raw_usage.cached_audio_input_units,
        audio_output_units=raw_usage.audio_output_units,
        audio_input_seconds=raw_usage.audio_input_seconds,
        provider_request_id=provider_request_id,
        avenqo_request_id=request_id,
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conversation_id,
        agent_id=agent_id,
        module_id=module_id,
        idempotency_key=f"{request_id}:{provider_request_id or operation}",
    )
    return LLMProviderAttempt(
        provider="openai",
        model=model,
        operation=operation,
        attempt_number=attempt_number,
        success=success,
        latency_ms=0,
        usage=usage,
        failure_category=failure_category,
        request_status=request_status,
        provider_cost_usd=pricing.cost_for(usage),
        input_cost_per_million_usd=pricing.input_cost_per_million_usd,
        cached_input_cost_per_million_usd=pricing.cached_input_cost_per_million_usd,
        output_cost_per_million_usd=pricing.output_cost_per_million_usd,
        cached_output_cost_per_million_usd=pricing.cached_output_cost_per_million_usd,
        audio_input_cost_per_million_usd=pricing.audio_input_cost_per_million_usd,
        cached_audio_input_cost_per_million_usd=pricing.cached_audio_input_cost_per_million_usd,
        audio_output_cost_per_million_usd=pricing.audio_output_cost_per_million_usd,
        audio_input_cost_per_second_usd=pricing.audio_input_cost_per_second_usd,
        pricing_version=pricing.version,
        pricing_source=pricing.source,
        pricing_effective_from=pricing.effective_from.isoformat(),
    )


def transcription_attempt(
    event: Any,
    *,
    catalog: ProviderPricingCatalog,
    model: str,
    attempt_number: int,
    request_id: str,
    tenant_id: str,
    user_id: str | None = None,
    conversation_id: str | None = None,
    agent_id: str | None = None,
    module_id: str | None = None,
) -> LLMProviderAttempt:
    raw = _value(event, "usage")
    usage_type = _value(raw, "type")
    input_details = _value(raw, "input_token_details")
    audio_tokens = _nonnegative_int(_value(input_details, "audio_tokens"))
    text_tokens = _value(input_details, "text_tokens")
    event_id = _value(event, "event_id")
    if usage_type == "duration":
        usage = LLMUsage(
            "openai", model,
            audio_input_seconds=Decimal(str(_value(raw, "seconds", 0) or 0)),
        )
    else:
        input_tokens = _nonnegative_int(_value(raw, "input_tokens"))
        usage = LLMUsage(
            "openai", model,
            input_tokens=input_tokens,
            output_tokens=_nonnegative_int(_value(raw, "output_tokens")),
            text_input_tokens=_nonnegative_int(text_tokens) if text_tokens is not None else None,
            text_output_tokens=_nonnegative_int(_value(raw, "output_tokens")),
            audio_input_units=Decimal(audio_tokens),
        )
    return _attempt(
        catalog=catalog, model=model, operation="voice_stt", raw_usage=usage,
        attempt_number=attempt_number, request_id=request_id,
        provider_request_id=str(event_id) if event_id else None,
        tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id,
        agent_id=agent_id, module_id=module_id,
    )


def realtime_response_attempt(
    event: Any,
    *,
    catalog: ProviderPricingCatalog,
    model: str,
    attempt_number: int,
    request_id: str,
    tenant_id: str,
    user_id: str | None = None,
    conversation_id: str | None = None,
    agent_id: str | None = None,
    module_id: str | None = None,
) -> LLMProviderAttempt | None:
    response = _value(event, "response")
    raw = _value(response, "usage")
    if raw is None:
        return None
    input_details = _value(raw, "input_token_details")
    output_details = _value(raw, "output_token_details")
    cached_details = _value(input_details, "cached_tokens_details")
    audio_input = _nonnegative_int(_value(input_details, "audio_tokens"))
    cached_audio = _nonnegative_int(_value(cached_details, "audio_tokens"))
    audio_output = _nonnegative_int(_value(output_details, "audio_tokens"))
    text_input = _value(input_details, "text_tokens")
    cached_text = _value(cached_details, "text_tokens")
    text_output = _value(output_details, "text_tokens")
    response_id = _value(response, "id")
    status = str(_value(response, "status") or "completed")
    usage = LLMUsage(
        "openai", model,
        input_tokens=_nonnegative_int(_value(raw, "input_tokens")),
        cached_input_tokens=_nonnegative_int(_value(input_details, "cached_tokens")),
        output_tokens=_nonnegative_int(_value(raw, "output_tokens")),
        text_input_tokens=_nonnegative_int(text_input) if text_input is not None else None,
        cached_text_input_tokens=_nonnegative_int(cached_text) if cached_text is not None else None,
        text_output_tokens=_nonnegative_int(text_output) if text_output is not None else None,
        audio_input_units=Decimal(audio_input),
        cached_audio_input_units=Decimal(cached_audio),
        audio_output_units=Decimal(audio_output),
    )
    return _attempt(
        catalog=catalog, model=model, operation="voice_realtime_tts", raw_usage=usage,
        attempt_number=attempt_number, request_id=request_id,
        provider_request_id=str(response_id) if response_id else None,
        tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id,
        agent_id=agent_id, module_id=module_id,
        success=status == "completed",
        failure_category="cancelled" if status == "cancelled" else None,
        request_status=status,
    )


@dataclass(slots=True)
class _VoiceTurnUsage:
    item_id: str
    request_id: str
    attempts: list[LLMProviderAttempt] = field(default_factory=list)
    event_ids: set[str] = field(default_factory=set)
    settled: bool = False


class VoiceUsageLedger:
    """One idempotent Phase 4 reservation and settlement per Realtime item."""

    def __init__(
        self,
        usage_service: AIUsageService,
        catalog: ProviderPricingCatalog,
        *,
        company_id: UUID,
        user_id: UUID | None,
        conversation_id: UUID | None,
        plan_code: str | None,
        request_namespace: UUID | None = None,
    ) -> None:
        self._usage = usage_service
        self._catalog = catalog
        self._company_id = company_id
        self._user_id = user_id
        self._conversation_id = conversation_id
        self._plan_code = plan_code
        self._request_namespace = request_namespace
        self._turns: dict[str, _VoiceTurnUsage] = {}

    def request_id_for(self, item_id: str) -> str:
        if self._request_namespace is not None:
            item_id = hashlib.sha256(f"voice-call:{self._request_namespace}:{item_id}".encode()).hexdigest()
        request_id = resolve_ai_request_id(
            item_id,
            tenant_id=self._company_id,
            user_id=self._user_id,
            conversation_id=self._conversation_id,
        )
        return request_id

    def reserve(self, item_id: str) -> bool:
        existing = self._turns.get(item_id)
        if existing is not None:
            return not existing.settled
        request_id = self.request_id_for(item_id)
        claim = self._usage.claim_credit_reservation(
            self._company_id,
            self._plan_code,
            request_id,
            self._usage.estimate_credits(None),
        )
        if not claim.acquired:
            return False
        self._turns[item_id] = _VoiceTurnUsage(item_id, request_id)
        return True

    def record_transcription(
        self,
        item_id: str,
        event: Any,
        *,
        model: str,
        agent_id: str | None = None,
        module_id: str | None = None,
    ) -> bool:
        if not self.reserve(item_id):
            return False
        turn = self._turns[item_id]
        event_id = str(_value(event, "event_id") or "")
        if event_id and event_id in turn.event_ids:
            return False
        attempt = transcription_attempt(
            event,
            catalog=self._catalog,
            model=model,
            attempt_number=len(turn.attempts) + 1,
            request_id=turn.request_id,
            tenant_id=str(self._company_id),
            user_id=str(self._user_id) if self._user_id is not None else None,
            conversation_id=str(self._conversation_id) if self._conversation_id is not None else None,
            agent_id=agent_id,
            module_id=module_id,
        )
        turn.attempts.append(attempt)
        if event_id:
            turn.event_ids.add(event_id)
        return True

    def record_realtime_response(
        self,
        item_id: str,
        event: Any,
        *,
        model: str,
        agent_id: str | None = None,
        module_id: str | None = None,
    ) -> bool:
        if not self.reserve(item_id):
            return False
        turn = self._turns[item_id]
        event_id = str(_value(event, "event_id") or "")
        if event_id and event_id in turn.event_ids:
            return False
        attempt = realtime_response_attempt(
            event,
            catalog=self._catalog,
            model=model,
            attempt_number=len(turn.attempts) + 1,
            request_id=turn.request_id,
            tenant_id=str(self._company_id),
            user_id=str(self._user_id) if self._user_id is not None else None,
            conversation_id=str(self._conversation_id) if self._conversation_id is not None else None,
            agent_id=agent_id,
            module_id=module_id,
        )
        if attempt is None:
            return False
        turn.attempts.append(attempt)
        if event_id:
            turn.event_ids.add(event_id)
        return True

    def record_provider_failure(
        self,
        item_id: str,
        *,
        model: str,
        operation: str,
        event_id: str,
        failure_category: str,
    ) -> bool:
        if not self.reserve(item_id):
            return False
        turn = self._turns[item_id]
        if event_id in turn.event_ids:
            return False
        turn.attempts.append(_attempt(
            catalog=self._catalog,
            model=model,
            operation=operation,
            raw_usage=LLMUsage("openai", model),
            attempt_number=len(turn.attempts) + 1,
            request_id=turn.request_id,
            provider_request_id=event_id,
            tenant_id=str(self._company_id),
            user_id=str(self._user_id) if self._user_id is not None else None,
            conversation_id=str(self._conversation_id) if self._conversation_id is not None else None,
            agent_id=None,
            module_id=None,
            success=False,
            failure_category=failure_category,
            request_status="failed",
        ))
        turn.event_ids.add(event_id)
        return True

    def attribute(self, item_id: str, agent_id: str | None, module_id: str | None) -> None:
        turn = self._turns.get(item_id)
        if turn is None:
            return
        turn.attempts = [
            replace(
                attempt,
                usage=replace(
                    attempt.usage,
                    agent_id=agent_id or attempt.usage.agent_id,
                    module_id=module_id or attempt.usage.module_id,
                ),
            )
            for attempt in turn.attempts
        ]

    def add_attempts(
        self, item_id: str, attempts: list[LLMProviderAttempt]
    ) -> None:
        turn = self._turns.get(item_id)
        if turn is None or turn.settled:
            return
        for attempt in attempts:
            turn.attempts.append(replace(
                attempt,
                attempt_number=len(turn.attempts) + 1,
                usage=replace(
                    attempt.usage,
                    avenqo_request_id=turn.request_id,
                    tenant_id=str(self._company_id),
                    user_id=str(self._user_id) if self._user_id is not None else None,
                    conversation_id=str(self._conversation_id) if self._conversation_id is not None else None,
                ),
            ))

    def settle(self, item_id: str) -> bool:
        turn = self._turns.get(item_id)
        if turn is None or turn.settled:
            return False
        if not turn.attempts:
            self._usage.release_reservation(
                self._company_id, turn.request_id, reason="voice_turn_without_provider_usage"
            )
            turn.settled = True
            return True
        self._usage.settle_reservation(
            self._company_id,
            self._plan_code,
            turn.request_id,
            tokens=sum(attempt.usage.total_tokens for attempt in turn.attempts),
            attempts=tuple(turn.attempts),
            count_request=True,
        )
        turn.settled = True
        return True

    def settle_pending(self) -> None:
        for item_id in tuple(self._turns):
            self.settle(item_id)
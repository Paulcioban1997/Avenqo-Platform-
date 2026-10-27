"""Tenant call admission and conservative reservations, never a provider hard cap.

Reservations persist in VoiceCall.source_context. PostgreSQL serializes admission
per company; only signed hangup releases concurrency. Unknown final costs retain
the full reservation, rather than silently giving the budget back.
"""
from datetime import datetime, timezone
from decimal import Decimal
from math import floor

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text

from backend.app.models import VoiceBusinessConfig, VoiceCall
from backend.app.models.voice_provisioning import VoiceTelecomCost
from backend.app.services.plan_limits_service import PlanLimitsService


class CallPolicy(BaseModel):
    model_config = ConfigDict(extra="ignore")
    max_call_seconds: int | None = Field(default=3600, ge=60, le=86400)
    idle_seconds: int = Field(default=120, ge=30, le=600)
    concurrent_calls: int = Field(default=1, ge=1, le=100)
    call_budget_usd: Decimal = Field(default=Decimal("5"), gt=0, le=1000, allow_inf_nan=False)
    monthly_budget_usd: Decimal = Field(default=Decimal("50"), gt=0, le=100000, allow_inf_nan=False)
    monthly_minutes: int = Field(default=600, ge=1, le=1000000)
    alert_percent: int = Field(default=80, ge=1, le=99)
    auth_seconds: int = Field(default=600, ge=60, le=86400)
    ivr_enabled: bool | None = None
    lifecycle_status: str | None = None
    ivr_greeting: str | None = None


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def policy_for(db, config, settings):
    policy = CallPolicy.model_validate(config.call_policy or {})
    limits = PlanLimitsService(db).limits_for(config.company_id)
    cap = settings.voice_plan_max_call_seconds.get(limits.plan_code, 3600)
    if policy.max_call_seconds is None and cap is not None:
        raise PermissionError("This plan requires a duration limit")
    if cap is not None and policy.max_call_seconds > cap:
        raise PermissionError("Duration exceeds plan allowance")
    if limits.max_concurrent_calls is not None and policy.concurrent_calls > limits.max_concurrent_calls:
        raise PermissionError("Concurrency exceeds plan allowance")
    if policy.auth_seconds > settings.voice_auth_max_session_seconds:
        raise PermissionError("Authentication lifetime exceeds operator allowance")
    return policy


def admit(db, settings, call, config, *, now=None):
    if not settings.voice_long_calls_enabled:
        return None
    if call.company_id != config.company_id or call.config_id != config.id:
        raise PermissionError("Call ownership mismatch")
    if not config.enabled:
        raise PermissionError("Voice agent unavailable")
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                   {"key": "voice-budget:" + str(call.company_id)})
    db.refresh(call)
    previous = (call.source_context or {}).get("runtime_policy")
    if previous:
        return previous  # Same stored call cannot reserve twice.
    policy = policy_for(db, config, settings)
    rate = settings.voice_budget_rate_ceiling_usd_per_minute
    if rate is None or rate <= 0:
        raise PermissionError("Operator-approved combined cost rate required")
    now = now or datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = db.scalars(select(VoiceCall).where(VoiceCall.company_id == call.company_id,
        VoiceCall.id != call.id)).all()
    active = [row for row in rows if row.ended_at is None
              and ((row.source_context or {}).get("runtime_policy") or row.status in {"answering", "routing", "routed", "in_progress"})]
    if len(active) >= policy.concurrent_calls:
        raise PermissionError("Concurrent call allowance exhausted")
    spent, minutes = Decimal(0), Decimal(0)
    for row in rows:
        snapshot = (row.source_context or {}).get("runtime_policy")
        if snapshot and (row.ended_at is None or (row.started_at and utc(row.started_at) >= month_start)):
            spent += Decimal(snapshot["reserved_usd"])
            minutes += Decimal(snapshot["reserved_seconds"]) / 60
    seconds = min(floor(policy.call_budget_usd / rate * 60),
                  floor((policy.monthly_budget_usd - spent) / rate * 60),
                  floor((Decimal(policy.monthly_minutes) - minutes) * 60))
    if policy.max_call_seconds is not None:
        seconds = min(seconds, policy.max_call_seconds)
    if seconds < 60:
        raise PermissionError("Call budget exhausted")
    snapshot = {**policy.model_dump(mode="json"), "reserved_seconds": seconds,
                "reserved_usd": str(rate * Decimal(seconds) / 60),
                "rate_ceiling_usd_per_minute": str(rate), "started_at": utc(call.started_at or now).isoformat(),
                "cost_status": "RESERVED_UNVERIFIED", "provider_hard_cap": False,
                "budget_alert": (spent + rate * Decimal(seconds) / 60) * 100 >= policy.monthly_budget_usd * policy.alert_percent}
    call.source_context = {**(call.source_context or {}), "runtime_policy": snapshot}
    db.commit()
    return snapshot


def remaining(call, *, now=None):
    snapshot = (call.source_context or {}).get("runtime_policy")
    if not snapshot:
        return None
    now = now or datetime.now(timezone.utc)
    start = datetime.fromisoformat(snapshot["started_at"])
    return max(0.0, float(snapshot["reserved_seconds"]) - max(0.0, (utc(now) - utc(start)).total_seconds()))


def check(db, settings, call):
    if not settings.voice_long_calls_enabled:
        return
    db.refresh(call)
    config = db.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.id == call.config_id,
                                                       VoiceBusinessConfig.company_id == call.company_id))
    if not config or not config.enabled:
        raise PermissionError("Voice agent unavailable")
    policy = policy_for(db, config, settings)
    left = remaining(call)
    if left is None or left <= 0:
        raise PermissionError("Call duration or budget exhausted")
    elapsed = max(0.0, (datetime.now(timezone.utc) - utc(call.started_at)).total_seconds())
    if policy.max_call_seconds is not None and elapsed >= policy.max_call_seconds:
        raise PermissionError("Updated duration exhausted")
    snapshot = call.source_context["runtime_policy"]
    if Decimal(snapshot["reserved_usd"]) > policy.call_budget_usd:
        raise PermissionError("Updated call budget exhausted")
    telecom = db.get(VoiceTelecomCost, call.id)
    reported_usd = Decimal((telecom.costs_by_currency or {}).get("USD", "0")) if telecom else Decimal(0)
    if Decimal(snapshot.get("ai_cost_usd", "0")) + reported_usd >= policy.call_budget_usd:
        raise PermissionError("Recorded model and audio cost allowance exhausted")


def record_ai_cost(db, call, request_id, attempts):
    db.refresh(call)
    snapshot = (call.source_context or {}).get("runtime_policy")
    if not snapshot:
        return
    events = dict(snapshot.get("ai_cost_events", {}))
    if request_id in events:
        return
    totals = {}
    for attempt in attempts:
        category = str(attempt.operation)
        totals[category] = totals.get(category, Decimal(0)) + attempt.provider_cost_usd
    events[request_id] = {key: str(value) for key, value in totals.items()}
    total = sum((Decimal(value) for event in events.values() for value in event.values()), Decimal(0))
    snapshot = {**snapshot, "ai_cost_events": events, "ai_cost_usd": str(total),
                "budget_alert": snapshot["budget_alert"] or total * 100 >= Decimal(snapshot["call_budget_usd"]) * snapshot["alert_percent"]}
    call.source_context = {**call.source_context, "runtime_policy": snapshot}
    db.commit()

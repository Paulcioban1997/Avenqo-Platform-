"""Schémas HTTP publics de l'Avenqo Admin Command Center (Phase 33)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class DashboardResponse(BaseModel):
    total_companies: int
    companies_by_plan: dict[str, int]
    new_companies_last_30_days: int
    active_subscriptions: int
    past_due_subscriptions: int
    ai_requests_current_period: int
    provider_status: dict[str, str]


class CompanyDirectoryEntryResponse(BaseModel):
    id: UUID
    name: str
    country: str
    joined_at: datetime
    plan_code: str
    subscription_status: str
    ai_requests_current_period: int
    monthly_credits: int | None
    monthly_credits_remaining: int | None
    purchased_credits_remaining: int
    total_credits_remaining: int | None
    has_connected_data_source: bool


class CompanyDetailResponse(BaseModel):
    id: UUID
    name: str
    country: str
    joined_at: datetime
    plan_code: str
    subscription_status: str
    cancel_at_period_end: bool
    current_period_end: datetime | None
    ai_requests_current_period: int
    monthly_credits: int | None
    monthly_credits_remaining: int | None
    purchased_credits_remaining: int
    total_credits_remaining: int | None
    users_count: int
    datasets_count: int
    trained_model_count: int
    enterprise_override: dict[str, Any] | None


class SetEnterpriseOverrideRequest(BaseModel):
    quota_overrides: dict[str, int | None] = Field(default_factory=dict)
    capability_overrides: dict[str, bool] = Field(default_factory=dict)
    notes: str | None = Field(default=None, max_length=2000)


class AuditLogEntryResponse(BaseModel):
    id: UUID
    actor_user_id: UUID | None
    action: str
    target_type: str
    target_id: str | None
    company_id: UUID | None
    safe_metadata: dict[str, Any]
    created_at: datetime

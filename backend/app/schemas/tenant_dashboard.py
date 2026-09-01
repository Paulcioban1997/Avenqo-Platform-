from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class DashboardCompanyResponse(BaseModel):
    currency: str
    plan_code: str


class DashboardPeriodResponse(BaseModel):
    start: datetime | None
    end: datetime | None
    comparison_start: datetime | None
    comparison_end: datetime | None


class DashboardKPIResponse(BaseModel):
    key: str
    value: float | int | None
    previous_value: float | int | None = None
    absolute_change: float | int | None = None
    change_percent: float | None = None
    currency: str | None = None
    available: bool


class DashboardPriorityResponse(BaseModel):
    id: str
    type: str
    title: str
    explanation: str
    severity: str
    source_capability: str
    evidence: dict[str, Any]
    suggested_action: str
    action_route: str | None = None


class DashboardConnectionsResponse(BaseModel):
    total: int
    ready: int
    analyzing: int
    preparing_data: int
    training_ai: int
    attention_required: int
    failed: int


class DashboardActivityResponse(BaseModel):
    kind: str
    title: str
    occurred_at: datetime


class TenantDashboardResponse(BaseModel):
    status: str
    generated_at: datetime
    company: DashboardCompanyResponse
    period: DashboardPeriodResponse
    capabilities: list[str]
    kpis: list[DashboardKPIResponse]
    priorities: list[DashboardPriorityResponse]
    connections: DashboardConnectionsResponse
    recent_activity: list[DashboardActivityResponse]
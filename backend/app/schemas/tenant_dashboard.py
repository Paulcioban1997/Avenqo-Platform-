from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


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
    state: str = "UNAVAILABLE"
    value: float | int | None
    previous_value: float | int | None = None
    absolute_change: float | int | None = None
    change_percent: float | None = None
    currency: str | None = None
    available: bool
    metric: dict[str, Any] | None = None


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


class DashboardTrendPointResponse(BaseModel):
    period: str
    revenue: float
    orders: int
    change_percent: float | None = None


class DashboardTrendResponse(BaseModel):
    points: list[DashboardTrendPointResponse] = Field(default_factory=list)


class TenantDashboardResponse(BaseModel):
    status: str
    generated_at: datetime
    company: DashboardCompanyResponse
    period: DashboardPeriodResponse
    capabilities: list[str]
    kpis: list[DashboardKPIResponse]
    metrics: list[dict[str, Any]] = Field(default_factory=list)
    data_freshness: dict[str, Any] = Field(default_factory=dict)
    priorities: list[DashboardPriorityResponse]
    trend: DashboardTrendResponse = Field(default_factory=DashboardTrendResponse)
    connections: DashboardConnectionsResponse
    recent_activity: list[DashboardActivityResponse]
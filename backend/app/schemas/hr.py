"""Schemas Pydantic pour le module Ressources Humaines (HR AI)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class HREmployeeItem(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    email: str
    phone: str | None = None
    role: str
    job_title: str
    department: str
    hierarchy_level: str  # "executive" | "management" | "operational"
    is_active: bool
    has_voice_pin: bool = False
    open_tasks_count: int = 0
    completed_tasks_count: int = 0


class HROverviewResponse(BaseModel):
    total_employees: int
    active_employees: int
    departments_count: int
    departments: list[str]
    hierarchy_breakdown: dict[str, int]
    tasks_metrics: dict[str, int]
    pending_leaves_count: int
    company_industry: str


class HRJobDescriptionSOP(BaseModel):
    role_title: str
    department: str
    hierarchy_level: str
    key_responsibilities: list[str]
    standard_operating_procedure: list[str]
    safety_and_compliance: list[str]
    time_optimization_tips: list[str]
    revenue_booster_actions: list[str]


class HRSectorSOPResponse(BaseModel):
    sector: str
    sector_name: str
    overview: str
    job_descriptions: list[HRJobDescriptionSOP]


class HRSkillItem(BaseModel):
    id: str
    name: str
    category: str  # "Technique", "Commercial", "Sécurité", "Outils"
    level: int  # 1 à 5
    certified: bool
    employee_id: UUID
    employee_name: str


class HRLeaveRequest(BaseModel):
    leave_type: str = Field(default="vacation", description="vacation, sickness, rtt, training, unpaid")
    start_date: datetime
    end_date: datetime
    days_count: float = 1.0
    reason: str | None = None


class HRLeaveItem(BaseModel):
    id: UUID
    user_id: UUID
    employee_name: str
    leave_type: str
    start_date: datetime
    end_date: datetime
    days_count: float
    reason: str | None
    status: str  # "pending", "approved", "rejected"
    approved_by: str | None = None
    created_at: datetime


class HRLeaveStatusUpdate(BaseModel):
    status: str = Field(..., description="approved ou rejected")


class HRPerformanceReviewCreate(BaseModel):
    employee_id: UUID
    review_period: str = "2026"
    rating: float = Field(..., ge=1.0, le=5.0)
    strengths: str
    growth_areas: str
    goals: str


class HRPerformanceReviewItem(BaseModel):
    id: UUID
    user_id: UUID
    employee_name: str
    reviewer_name: str
    review_period: str
    rating: float
    strengths: str | None
    growth_areas: str | None
    goals: str | None
    ai_coach_notes: str | None
    created_at: datetime

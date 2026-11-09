from __future__ import annotations

"""Schémas HTTP du parcours d'onboarding premium multi-pages, personnalisation de thème et validation."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from backend.app.models.base import OnboardingStatus


class OnboardingStatusResponse(BaseModel):
    status: OnboardingStatus
    business_goals: tuple[str, ...]
    current_tools: tuple[str, ...]
    team_size: str | None
    refined_industry: str | None
    completed_at: datetime | None
    activated_modules: tuple[str, ...] = ()
    unavailable_modules: tuple[str, ...] = ()
    current_step: str | None = None
    progress_percent: int = 0
    checklist: tuple[dict, ...] = ()
    company_logo_url: str | None = None
    theme_mode: str | None = "system"
    brand_color: str | None = "#0076FF"
    contracts_pending_count: int = 0
    contracts_signed_count: int = 0


class OnboardingSubmitRequest(BaseModel):
    business_goals: tuple[str, ...] = Field(default=(), max_length=10)
    current_tools: tuple[str, ...] = Field(default=(), max_length=20)
    team_size: str = Field(default="1-10", max_length=50)
    refined_industry: str | None = Field(default=None, max_length=120)
    # Modules Avenqo optionnels sélectionnés pendant l'onboarding
    selected_modules: tuple[str, ...] = Field(default=(), max_length=11)
    current_step: str | None = Field(default=None, max_length=64)
    # Personnalisation de l'espace entreprise (White-Label)
    company_logo_url: str | None = Field(default=None, max_length=1024)
    theme_mode: str | None = Field(default="system", max_length=32)
    brand_color: str | None = Field(default="#0076FF", max_length=32)


class OnboardingDraftRequest(BaseModel):
    current_step: str = Field(min_length=1, max_length=64)
    business_goals: tuple[str, ...] = Field(default=(), max_length=10)
    current_tools: tuple[str, ...] = Field(default=(), max_length=20)
    team_size: str | None = Field(default=None, max_length=50)
    refined_industry: str | None = Field(default=None, max_length=120)
    selected_modules: tuple[str, ...] = Field(default=(), max_length=11)
    company_logo_url: str | None = Field(default=None, max_length=1024)
    theme_mode: str | None = Field(default="system", max_length=32)
    brand_color: str | None = Field(default="#0076FF", max_length=32)


# --- Nouveaux schémas du parcours multi-pages (8 étapes) ---


class CompanyInfoStepPayload(BaseModel):
    commercial_name: str = Field(..., min_length=2, max_length=255)
    legal_name: str | None = Field(default=None, max_length=255)
    country: str = Field(default="Canada", min_length=2, max_length=100)
    region: str = Field(default="Quebec", min_length=2, max_length=100)
    timezone: str = Field(default="America/Montreal", min_length=2, max_length=100)
    industry: str = Field(default="Technologies", min_length=2, max_length=120)
    team_size: str = Field(default="1-10", max_length=50)
    website: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    authorized_rep_first_name: str = Field(..., min_length=1, max_length=100)
    authorized_rep_last_name: str = Field(..., min_length=1, max_length=100)
    authorized_rep_title: str = Field(default="Dirigeant", min_length=1, max_length=120)


class ModulesStepPayload(BaseModel):
    selected_modules: list[str] = Field(default_factory=list, max_length=12)
    industry_category: str | None = Field(default=None, max_length=120)


class DesignStepPayload(BaseModel):
    theme_id: str = Field(default="avenqo_obsidian", max_length=64)
    primary_color: str = Field(default="#0076FF", max_length=32)
    secondary_color: str = Field(default="#0B132B", max_length=32)
    accent_color: str = Field(default="#00D4FF", max_length=32)
    mode: str = Field(default="dark", max_length=16)
    background_style: str = Field(default="mesh_dark", max_length=64)
    company_logo_url: str | None = Field(default=None, max_length=2048)
    company_emblem_url: str | None = Field(default=None, max_length=2048)
    display_name: str | None = Field(default=None, max_length=255)


class ContractsStepPayload(BaseModel):
    accepted_contract_types: list[str] = Field(..., min_length=1)
    accepted_by_name: str = Field(..., min_length=2, max_length=255)
    accepted_by_title: str = Field(..., min_length=2, max_length=120)
    marketing_consent: bool = Field(default=False)


class SubscriptionStepPayload(BaseModel):
    plan_code: str = Field(default="base", max_length=64)
    billing_cycle: str = Field(default="monthly", max_length=32)
    currency: str = Field(default="CAD", max_length=3)


class StepUpdatePayload(BaseModel):
    step_id: str = Field(..., min_length=1, max_length=64)
    data: dict[str, Any] = Field(default_factory=dict)


class MultiStepOnboardingStateResponse(BaseModel):
    status: str
    is_completed: bool
    current_step: str
    progress_percent: int
    completed_steps: list[str]
    company_info: dict[str, Any]
    modules: dict[str, Any]
    design: dict[str, Any]
    contracts: dict[str, Any]
    subscription: dict[str, Any]
    candidate_themes: list[dict[str, Any]]
    can_finalize: bool
    missing_requirements: list[str]
    completed_at: datetime | None = None


class FinalizeOnboardingResponse(BaseModel):
    success: bool
    status: str
    message: str
    dashboard_url: str = "/dashboard"
    activated_modules: list[str]
    plan_code: str
    company_name: str

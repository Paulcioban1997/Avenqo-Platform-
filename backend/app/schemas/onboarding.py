from __future__ import annotations

"""Schémas HTTP du questionnaire d'onboarding post-inscription et personnalisation White-Label."""

from datetime import datetime

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
    business_goals: tuple[str, ...] = Field(min_length=1, max_length=10)
    current_tools: tuple[str, ...] = Field(default=(), max_length=20)
    team_size: str = Field(min_length=1, max_length=50)
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

"""Schémas HTTP du questionnaire d'onboarding post-inscription."""

from __future__ import annotations

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


class OnboardingSubmitRequest(BaseModel):
    business_goals: tuple[str, ...] = Field(min_length=1, max_length=10)
    current_tools: tuple[str, ...] = Field(default=(), max_length=20)
    team_size: str = Field(min_length=1, max_length=50)
    refined_industry: str | None = Field(default=None, max_length=120)
    # Modules Avenqo optionnels sélectionnés pendant l'onboarding (ex. "crm",
    # "accounting"). Activés uniquement si le plan de l'entreprise les
    # autorise (voir `SubscriptionPlan.allows_module`) — jamais en
    # contournement de la facturation.
    selected_modules: tuple[str, ...] = Field(default=(), max_length=10)

"""Schemas for Sector Profiles API (Phase 1)."""

from __future__ import annotations

from pydantic import BaseModel


class DemoStepResponse(BaseModel):
    step_number: int
    title_fr: str
    title_en: str
    description_fr: str
    description_en: str
    active_module: str
    input_data: str
    simulated_output: str
    visual_metric: str


class SectorProfileResponse(BaseModel):
    id: str
    name_fr: str
    name_en: str
    description_fr: str
    description_en: str
    icon_name: str
    recommended_modules: tuple[str, ...]
    use_cases_fr: tuple[str, ...]
    use_cases_en: tuple[str, ...]
    workflow_templates: tuple[str, ...]
    integration_prerequisites: tuple[str, ...]
    regulatory_constraints_fr: str
    regulatory_constraints_en: str
    feature_availability: str
    demo_steps: tuple[DemoStepResponse, ...]

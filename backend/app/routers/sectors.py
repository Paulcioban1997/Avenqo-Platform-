"""Sector profiles router for universal multi-industry discovery."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.schemas.sector import DemoStepResponse, SectorProfileResponse
from shared.sector_profiles import SECTOR_PROFILES, SECTOR_PROFILES_BY_ID

router = APIRouter(prefix="/sectors", tags=["sectors"])


def _to_response(profile) -> SectorProfileResponse:
    return SectorProfileResponse(
        id=profile.id,
        name_fr=profile.name_fr,
        name_en=profile.name_en,
        description_fr=profile.description_fr,
        description_en=profile.description_en,
        icon_name=profile.icon_name,
        recommended_modules=profile.recommended_modules,
        use_cases_fr=profile.use_cases_fr,
        use_cases_en=profile.use_cases_en,
        workflow_templates=profile.workflow_templates,
        integration_prerequisites=profile.integration_prerequisites,
        regulatory_constraints_fr=profile.regulatory_constraints_fr,
        regulatory_constraints_en=profile.regulatory_constraints_en,
        feature_availability=profile.feature_availability,
        demo_steps=tuple(
            DemoStepResponse(
                step_number=step.step_number,
                title_fr=step.title_fr,
                title_en=step.title_en,
                description_fr=step.description_fr,
                description_en=step.description_en,
                active_module=step.active_module,
                input_data=step.input_data,
                simulated_output=step.simulated_output,
                visual_metric=step.visual_metric,
            )
            for step in profile.demo_steps
        ),
    )


@router.get("", response_model=list[SectorProfileResponse])
async def list_sectors() -> list[SectorProfileResponse]:
    """List all available universal sector profiles."""
    return [_to_response(profile) for profile in SECTOR_PROFILES]


@router.get("/{sector_id}", response_model=SectorProfileResponse)
async def get_sector(sector_id: str) -> SectorProfileResponse:
    """Retrieve details for a specific sector profile."""
    profile = SECTOR_PROFILES_BY_ID.get(sector_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Secteur introuvable")
    return _to_response(profile)

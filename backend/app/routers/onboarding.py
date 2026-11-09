"""Routes du parcours d'onboarding premium multi-pages, personnalisation de thème et activation."""

from __future__ import annotations

import base64
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.dependencies.auth import get_tenant_context
from backend.app.schemas.onboarding import (
    FinalizeOnboardingResponse,
    MultiStepOnboardingStateResponse,
    OnboardingDraftRequest,
    OnboardingStatusResponse,
    OnboardingSubmitRequest,
    StepUpdatePayload,
)
from backend.app.services.onboarding_service import OnboardingService
from shared.ai_engine.contracts import TenantContext

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


def get_onboarding_service(db: Session = Depends(get_db)) -> OnboardingService:
    return OnboardingService(db)


# --- Endpoints historiques (rétrocompatibilité 100%) ---


@router.get("", response_model=OnboardingStatusResponse)
def get_onboarding(
    tenant: TenantContext = Depends(get_tenant_context),
    service: OnboardingService = Depends(get_onboarding_service),
) -> OnboardingStatusResponse:
    return service.get_status(tenant)


@router.post("/complete", response_model=OnboardingStatusResponse)
def complete_onboarding(
    request: OnboardingSubmitRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    service: OnboardingService = Depends(get_onboarding_service),
) -> OnboardingStatusResponse:
    return service.submit(tenant, request)


@router.post("/draft", response_model=OnboardingStatusResponse)
def save_onboarding_draft(
    request: OnboardingDraftRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    service: OnboardingService = Depends(get_onboarding_service),
) -> OnboardingStatusResponse:
    return service.save_draft(tenant, request)


@router.post("/skip", response_model=OnboardingStatusResponse)
def skip_onboarding(
    tenant: TenantContext = Depends(get_tenant_context),
    service: OnboardingService = Depends(get_onboarding_service),
) -> OnboardingStatusResponse:
    return service.skip(tenant)


# --- Nouveaux endpoints pour le parcours multi-pages (8 étapes) ---


@router.get("/state", response_model=MultiStepOnboardingStateResponse)
def get_multistep_state(
    tenant: TenantContext = Depends(get_tenant_context),
    service: OnboardingService = Depends(get_onboarding_service),
) -> MultiStepOnboardingStateResponse:
    """Retourne l'état complet du parcours d'onboarding, les thèmes et les données enregistrées."""
    return service.get_multistep_state(tenant)


@router.put("/step/{step_id}", response_model=MultiStepOnboardingStateResponse)
def update_step(
    step_id: str,
    payload: dict[str, Any],
    tenant: TenantContext = Depends(get_tenant_context),
    service: OnboardingService = Depends(get_onboarding_service),
) -> MultiStepOnboardingStateResponse:
    """Sauvegarde les choix de l'étape courante dans la base de données de manière isolée."""
    valid_steps = {"company", "modules", "design", "preview", "contracts", "subscription", "checkout", "complete"}
    if step_id not in valid_steps:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Étape d'onboarding invalide: {step_id}. Étapes valides: {sorted(valid_steps)}",
        )
    return service.update_step(tenant, step_id, payload)


@router.post("/finalize", response_model=FinalizeOnboardingResponse)
def finalize_onboarding(
    tenant: TenantContext = Depends(get_tenant_context),
    service: OnboardingService = Depends(get_onboarding_service),
) -> FinalizeOnboardingResponse:
    """Active l'espace après validation des informations, modules, design, contrats et abonnement."""
    try:
        return service.finalize_onboarding(tenant)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/branding")
def get_branding(
    tenant: TenantContext = Depends(get_tenant_context),
    service: OnboardingService = Depends(get_onboarding_service),
) -> dict[str, Any]:
    """Retourne le thème et la personnalisation de marque de l'entreprise."""
    return service.get_tenant_branding(tenant)


@router.put("/branding")
def update_branding(
    payload: dict[str, Any],
    tenant: TenantContext = Depends(get_tenant_context),
    service: OnboardingService = Depends(get_onboarding_service),
) -> dict[str, Any]:
    """Met à jour le thème ou réinitialise le style pour l'entreprise connectée."""
    return service.update_tenant_branding(tenant, payload)


@router.post("/upload-asset")
async def upload_asset(
    file: UploadFile = File(...),
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict[str, str]:
    """Téléchargement sécurisé de logo ou emblème d'entreprise avec validation de type et taille."""
    allowed_content_types = {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/webp": "webp",
        "image/svg+xml": "svg",
    }
    content_type = file.content_type or ""
    if content_type not in allowed_content_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Format de fichier non autorisé. Formats acceptés : PNG, JPEG, WebP, SVG.",
        )

    # Limite 5 Mo
    MAX_SIZE = 5 * 1024 * 1024
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="L'image ne doit pas dépasser 5 Mo.",
        )

    # Convertir en Data URL sécurisé pour un affichage universel instantané
    encoded = base64.b64encode(content).decode("ascii")
    data_url = f"data:{content_type};base64,{encoded}"

    return {
        "asset_url": data_url,
        "filename": file.filename or "asset",
        "content_type": content_type,
    }

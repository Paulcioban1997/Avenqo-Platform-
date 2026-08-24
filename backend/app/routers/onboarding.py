"""Routes du questionnaire d'onboarding, protégées et scopées au tenant."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.dependencies.auth import get_tenant_context
from backend.app.schemas.onboarding import OnboardingStatusResponse, OnboardingSubmitRequest
from backend.app.services.onboarding_service import OnboardingService
from shared.ai_engine.contracts import TenantContext

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


def get_onboarding_service(db: Session = Depends(get_db)) -> OnboardingService:
    return OnboardingService(db)


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


@router.post("/skip", response_model=OnboardingStatusResponse)
def skip_onboarding(
    tenant: TenantContext = Depends(get_tenant_context),
    service: OnboardingService = Depends(get_onboarding_service),
) -> OnboardingStatusResponse:
    return service.skip(tenant)

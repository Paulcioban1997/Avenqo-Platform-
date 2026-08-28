import logging

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.dependencies.auth import get_tenant_context
from backend.app.dependencies.dashboard import get_tenant_dashboard_service
from backend.app.schemas.tenant_dashboard import TenantDashboardResponse
from backend.app.services.tenant_dashboard_service import TenantDashboardService
from shared.ai_engine.contracts import TenantContext

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=TenantDashboardResponse)
def get_dashboard(
    tenant: TenantContext = Depends(get_tenant_context),
    service: TenantDashboardService = Depends(get_tenant_dashboard_service),
) -> TenantDashboardResponse:
    try:
        return TenantDashboardResponse.model_validate(service.build(tenant))
    except Exception as exc:
        logger.exception("Tenant dashboard generation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Dashboard temporarily unavailable",
        ) from exc
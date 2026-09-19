"""Tenant-scoped business module entitlement routes."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity, require_permission
from backend.app.schemas.modules import CompanyEntitlementsResponse
from backend.app.services.module_entitlement_service import (
    ModuleEntitlementError,
    ModuleEntitlementService,
    ModuleUpgradeRequired,
)
from shared.ai_engine.contracts import TenantContext

router = APIRouter(prefix="/modules", tags=["modules"])
manage_modules = require_permission("modules:manage")


def _response(service: ModuleEntitlementService, tenant: TenantContext) -> CompanyEntitlementsResponse:
    return CompanyEntitlementsResponse(**asdict(service.summary(tenant)))


@router.get("/entitlements", response_model=CompanyEntitlementsResponse)
def entitlements(
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> CompanyEntitlementsResponse:
    tenant = TenantContext(identity.user.company_id)
    result = _response(ModuleEntitlementService(db), tenant)
    db.rollback()
    return result



@router.post("/{module_key}/activate", response_model=CompanyEntitlementsResponse)
def activate_module(
    module_key: str,
    identity: CurrentIdentity = Depends(manage_modules),
    db: Session = Depends(get_db),
) -> CompanyEntitlementsResponse:
    tenant = TenantContext(identity.user.company_id)
    service = ModuleEntitlementService(db)
    try:
        result = service.activate_module(tenant, module_key)
        db.commit()
    except ModuleUpgradeRequired as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ModuleEntitlementError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return CompanyEntitlementsResponse(**asdict(result))


@router.post("/{module_key}/deactivate", response_model=CompanyEntitlementsResponse)
def deactivate_module(
    module_key: str,
    identity: CurrentIdentity = Depends(manage_modules),
    db: Session = Depends(get_db),
) -> CompanyEntitlementsResponse:
    tenant = TenantContext(identity.user.company_id)
    service = ModuleEntitlementService(db)
    result = service.deactivate_module(tenant, module_key)
    db.commit()
    return CompanyEntitlementsResponse(**asdict(result))


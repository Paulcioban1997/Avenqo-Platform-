"""Avenqo Admin Command Center (Phase 33) : routes réservées aux `platform_admin`.

Jamais accessible à un `tenant_admin` (owner/admin d'entreprise) : voir
`require_platform_admin`. Ne renvoie jamais de données métier privées d'un
tenant (ventes, clients, contenu de dataset).
"""

from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.dependencies.admin import get_admin_service, get_audit_log_service
from backend.app.dependencies.auth import CurrentIdentity, require_platform_admin
from backend.app.core.rate_limit import rate_limit
from backend.app.schemas.admin import (
    AuditLogEntryResponse,
    CompanyDetailResponse,
    CompanyDirectoryEntryResponse,
    DashboardResponse,
    SetEnterpriseOverrideRequest,
)
from backend.app.services.admin_service import AdminService
from backend.app.services.audit_log_service import AuditLogService

router = APIRouter(
    prefix="/admin",
    tags=["avenqo-admin"],
    dependencies=[
        Depends(require_platform_admin),
        Depends(rate_limit("admin", "rate_limit_admin_per_minute")),
    ],
)


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(service: AdminService = Depends(get_admin_service)) -> DashboardResponse:
    return DashboardResponse(**asdict(service.dashboard()))


@router.get("/companies", response_model=list[CompanyDirectoryEntryResponse])
def list_companies(
    service: AdminService = Depends(get_admin_service),
    skip: int = 0,
    limit: int = 50,
) -> list[CompanyDirectoryEntryResponse]:
    limit = min(max(limit, 1), 200)
    skip = max(skip, 0)
    entries = [CompanyDirectoryEntryResponse(**asdict(entry)) for entry in service.company_directory()]
    return entries[skip : skip + limit]


@router.get("/companies/{company_id}", response_model=CompanyDetailResponse)
def get_company(company_id: UUID, service: AdminService = Depends(get_admin_service)) -> CompanyDetailResponse:
    detail = service.company_detail(company_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return CompanyDetailResponse(**asdict(detail))


@router.put("/companies/{company_id}/enterprise-override", response_model=CompanyDetailResponse)
def set_enterprise_override(
    company_id: UUID,
    request: SetEnterpriseOverrideRequest,
    identity: CurrentIdentity = Depends(require_platform_admin),
    service: AdminService = Depends(get_admin_service),
) -> CompanyDetailResponse:
    try:
        service.set_enterprise_override(
            actor_user_id=identity.user.id,
            company_id=company_id,
            quota_overrides=request.quota_overrides,
            capability_overrides=request.capability_overrides,
            notes=request.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    detail = service.company_detail(company_id)
    assert detail is not None
    return CompanyDetailResponse(**asdict(detail))


@router.get("/audit-log", response_model=list[AuditLogEntryResponse])
def get_audit_log(
    audit_log: AuditLogService = Depends(get_audit_log_service),
    limit: int = 100,
) -> list[AuditLogEntryResponse]:
    limit = min(max(limit, 1), 500)
    return [
        AuditLogEntryResponse(
            id=entry.id,
            actor_user_id=entry.actor_user_id,
            action=entry.action,
            target_type=entry.target_type,
            target_id=entry.target_id,
            company_id=entry.company_id,
            safe_metadata=entry.safe_metadata,
            created_at=entry.created_at,
        )
        for entry in audit_log.recent(limit=limit)
    ]

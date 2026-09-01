from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.ai.llm.health import ProviderHealthRegistry, get_provider_health_registry
from backend.app.ai.usage.policy import AIQuotaPolicy
from backend.app.ai.usage.service import AIUsageService
from backend.app.config.settings import Settings, get_settings
from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, require_platform_admin
from backend.app.models import Company
from backend.app.services.admin_service import AdminService
from backend.app.services.audit_log_service import AuditLogService
from shared.ai_engine.contracts import TenantContext


def get_admin_tenant_context(
    company_id: UUID,
    identity: CurrentIdentity = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> TenantContext:
    """Build an explicit tenant context only after admin and company validation."""

    del identity
    if db.get(Company, company_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return TenantContext(company_id=company_id)


def get_audit_log_service(db: Session = Depends(get_db)) -> AuditLogService:
    return AuditLogService(db)


def get_admin_service(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    audit_log: AuditLogService = Depends(get_audit_log_service),
) -> AdminService:
    return AdminService(
        db,
        AIUsageService(db, AIQuotaPolicy(settings)),
        get_provider_health_registry(),
        audit_log,
    )

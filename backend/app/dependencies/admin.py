from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.ai.llm.health import ProviderHealthRegistry, get_provider_health_registry
from backend.app.ai.usage.policy import AIQuotaPolicy
from backend.app.ai.usage.service import AIUsageService
from backend.app.config.settings import Settings, get_settings
from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, require_platform_admin
from backend.app.models import Company, CompanyMembership
from backend.app.core.permissions import permissions_for
from backend.app.services.support_access import support_can_read_retail
from backend.app.services.admin_service import AdminService
from backend.app.services.audit_log_service import AuditLogService
from shared.ai_engine.contracts import TenantContext


def get_admin_tenant_context(
    company_id: UUID,
    identity: CurrentIdentity = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> TenantContext:
    """Build an explicit tenant context only after admin and company validation."""

    if db.get(Company, company_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    membership = db.scalar(select(CompanyMembership).where(
        CompanyMembership.user_id == identity.user_id,
        CompanyMembership.company_id == company_id,
        CompanyMembership.is_active.is_(True),
    ))
    own_access = identity.company_id == company_id and "data:read" in permissions_for(identity.user.role)
    member_access = membership is not None and "data:read" in permissions_for(membership.role)
    if not (own_access or member_access or support_can_read_retail(db, company_id, identity.user_id)):
        raise HTTPException(403, "Un accès support explicite, valide et limité est requis")
    AuditLogService(db).record(actor_user_id=identity.user_id, company_id=company_id,
                               action="support_retail_access", target_type="company", target_id=str(company_id))
    return TenantContext(company_id=company_id, user_id=identity.user_id)


def get_audit_log_service(db: Session = Depends(get_db)) -> AuditLogService:
    return AuditLogService(db)


def get_admin_service(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    audit_log: AuditLogService = Depends(get_audit_log_service),
) -> AdminService:
    return AdminService(
        db,
        AIUsageService(
            db,
            AIQuotaPolicy(settings),
            settings.avenqo_provider_cost_per_credit_usd,
            settings.ai_credit_reservation_ttl_minutes,
        ),
        get_provider_health_registry(),
        audit_log,
    )

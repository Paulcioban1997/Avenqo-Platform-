from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.ai.llm.health import ProviderHealthRegistry, get_provider_health_registry
from backend.app.ai.usage.policy import AIQuotaPolicy
from backend.app.ai.usage.service import AIUsageService
from backend.app.config.settings import Settings, get_settings
from backend.app.database import get_db
from backend.app.services.admin_service import AdminService
from backend.app.services.audit_log_service import AuditLogService


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

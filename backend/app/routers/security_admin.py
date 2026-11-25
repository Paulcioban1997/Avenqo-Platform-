"""Admin Security Posture & Optional CrowdStrike NG-SIEM routes (`/api/v1/admin/security/*`).

Strictly restricted to authorized Avenqo platform administrators (`is_platform_admin=True`,
and when `platform_role` is assigned, restricted to `PLATFORM_SUPER_ADMIN` or
`PLATFORM_SECURITY_AUDITOR`). Non-admin and cross-tenant users are rejected fail-closed (HTTP 403).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from backend.app.config.settings import Settings, get_settings
from backend.app.core.permissions import permissions_for
from backend.app.core.rate_limit import rate_limit
from backend.app.core.request_context import request_id_var
from backend.app.core.tenant_execution import TenantExecutionContext, bind_tenant_execution
from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity
from backend.app.security.crowdstrike_siem import (
    CrowdStrikeSIEMConnector,
    SecurityEventType,
    get_crowdstrike_connector,
)
from backend.app.services.audit_log_service import AuditLogService
from backend.app.services.security_posture_service import SecurityPostureService
from backend.app.services.tenant_rls import apply_tenant_rls
from shared.ai_engine.contracts import TenantContext

_ALLOWED_EXPLICIT_PLATFORM_ROLES = frozenset({
    "PLATFORM_SUPER_ADMIN",
    "PLATFORM_SECURITY_AUDITOR",
})


def require_security_platform_admin(
    request: Request,
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
    connector: CrowdStrikeSIEMConnector = Depends(get_crowdstrike_connector),
) -> CurrentIdentity:
    """Fail-closed platform security RBAC check with normalized denial telemetry."""
    client_ip = request.client.host if request.client else None
    if not identity.user.is_platform_admin:
        connector.emit_event(
            SecurityEventType.RBAC_PERMISSION_DENIED,
            summary="Tentative d'accès non autorisée à la console sécurité plateforme.",
            severity="high",
            outcome="denied",
            company_id=identity.company_id,
            actor_id=identity.user_id,
            ip_address=client_ip,
            details={
                "path": request.url.path,
                "method": request.method,
                "tenant_role": identity.user.role.value if hasattr(identity.user.role, "value") else str(identity.user.role),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs sécurité de la plateforme Avenqo",
        )

    explicit_role = getattr(identity.user, "platform_role", None)
    if explicit_role not in _ALLOWED_EXPLICIT_PLATFORM_ROLES:
        connector.emit_event(
            SecurityEventType.RBAC_PERMISSION_DENIED,
            summary="Rôle plateforme insuffisant pour consulter la console sécurité.",
            severity="medium",
            outcome="denied",
            company_id=identity.company_id,
            actor_id=identity.user_id,
            ip_address=client_ip,
            details={
                "path": request.url.path,
                "method": request.method,
                "platform_role": str(explicit_role),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Privilège plateforme insuffisant pour le module Sécurité",
        )

    apply_tenant_rls(db, identity.company_id, bypass=True)
    bind_tenant_execution(
        TenantExecutionContext(
            tenant=TenantContext(company_id=identity.company_id, user_id=identity.user_id),
            user_id=identity.user_id,
            permissions=frozenset(permissions_for(identity.user.role)),
            request_id=request_id_var.get() or "",
            rls_bound=True,
            rls_bypass=True,
            source="platform_admin_security",
        )
    )
    return identity


router = APIRouter(
    prefix="/admin/security",
    tags=["avenqo-admin-security"],
    dependencies=[
        Depends(require_security_platform_admin),
        Depends(rate_limit("admin", "rate_limit_admin_per_minute")),
    ],
)


@router.get("/posture")
def get_security_posture(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    connector: CrowdStrikeSIEMConnector = Depends(get_crowdstrike_connector),
) -> dict[str, Any]:
    """Return honest native security posture and optional CrowdStrike integration status."""
    return SecurityPostureService(db=db, settings=settings, connector=connector).evaluate_posture()


@router.get("/events")
def get_security_events(
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    connector: CrowdStrikeSIEMConnector = Depends(get_crowdstrike_connector),
) -> dict[str, Any]:
    """Return sanitized, normalized recent security alerts across the 10 canonical categories."""
    return SecurityPostureService(db=db, settings=settings, connector=connector).list_normalized_events(limit=limit)


@router.post("/crowdstrike/test-connection")
def test_crowdstrike_connection(
    identity: CurrentIdentity = Depends(require_security_platform_admin),
    db: Session = Depends(get_db),
    connector: CrowdStrikeSIEMConnector = Depends(get_crowdstrike_connector),
) -> dict[str, Any]:
    """Run a non-destructive CrowdStrike NG-SIEM HEC connection check without exposing secrets."""
    result = connector.test_connection()
    AuditLogService(db).record(
        actor_user_id=identity.user_id,
        company_id=identity.company_id,
        action="security.crowdstrike_connection_tested",
        target_type="siem_connector",
        target_id="crowdstrike_hec",
        metadata={
            "status": result.status,
            "siem_enabled": result.siem_enabled,
            "verified": result.verified,
        },
    )
    return result.to_dict()

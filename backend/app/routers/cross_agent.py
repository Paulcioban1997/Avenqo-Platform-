"""Routes API pour le module Cross-Agent AI (Phase 15).

Expose la synthèse 360° et les corrélations stratégiques entre Retail, CRM et Accounting.
"""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.core.permissions import permissions_for
from backend.app.dependencies.auth import get_tenant_context
from backend.app.dependencies.ai_authorization import get_active_ai_membership
from backend.app.services.cross_agent_intelligence_service import CrossAgentIntelligenceService
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from shared.ai_engine.contracts import TenantContext

router = APIRouter(prefix="/cross-agent", tags=["cross-agent"])


@router.get("/synthesis")
def get_cross_agent_synthesis(
    tenant: TenantContext = Depends(get_tenant_context),
    membership=Depends(get_active_ai_membership),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Synthèse exécutive 360° unifiée (Retail ↔ CRM ↔ Accounting)."""
    if "ai:use" not in permissions_for(membership.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    active_modules = frozenset(ModuleEntitlementService(db).get_active_modules(tenant))
    if not {"retail", "crm", "accounting"}.issubset(active_modules):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    service = CrossAgentIntelligenceService(db)
    return service.get_cross_domain_synthesis(tenant.company_id)

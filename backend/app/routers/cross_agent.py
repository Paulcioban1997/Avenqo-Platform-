"""Routes API pour le module Cross-Agent AI (Phase 15).

Expose la synthèse 360° et les corrélations stratégiques entre Retail, CRM et Accounting.
"""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.dependencies.auth import get_tenant_context
from backend.app.services.cross_agent_intelligence_service import CrossAgentIntelligenceService
from shared.ai_engine.contracts import TenantContext

router = APIRouter(prefix="/cross-agent", tags=["cross-agent"])


@router.get("/synthesis")
def get_cross_agent_synthesis(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Synthèse exécutive 360° unifiée (Retail ↔ CRM ↔ Accounting)."""
    service = CrossAgentIntelligenceService(db)
    return service.get_cross_domain_synthesis(tenant.company_id)

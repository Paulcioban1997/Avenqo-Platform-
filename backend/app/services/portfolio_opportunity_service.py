"""Agrégation portefeuille des opportunités métier (Phase 25).

Même principe que `portfolio_decision_service.py` (Phase 22/24) : aucune
persistance, calcul à la demande à partir du dernier dataset importé et des
modèles actifs de ce tenant.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.services.portfolio_decision_service import gather_portfolio_signals
from backend.app.services.prediction_runtime import build_decision_service
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.decision_intelligence.contracts import DecisionContext, Severity
from shared.ai_engine.decision_intelligence.opportunity import BusinessOpportunity, BusinessOpportunityService
from shared.ai_engine.prediction.service import PredictionService


@dataclass(frozen=True, slots=True)
class PortfolioOpportunities:
    company_id: UUID
    opportunity_count: int
    critical_count: int
    high_count: int
    opportunities: tuple[BusinessOpportunity, ...]


def build_portfolio_opportunities(
    session: Session,
    tenant: TenantContext,
    module_code: str,
    prediction_service: PredictionService,
) -> PortfolioOpportunities:
    signals = gather_portfolio_signals(session, tenant, module_code, prediction_service)

    context = DecisionContext(company_id=tenant.company_id, module_code=module_code)
    bundle = build_decision_service(module_code).build_bundle(context, signals)
    opportunities = BusinessOpportunityService().from_bundle(bundle)

    critical_count = sum(1 for opportunity in opportunities if opportunity.priority == Severity.CRITICAL)
    high_count = sum(1 for opportunity in opportunities if opportunity.priority == Severity.HIGH)

    return PortfolioOpportunities(
        company_id=tenant.company_id,
        opportunity_count=len(opportunities),
        critical_count=critical_count,
        high_count=high_count,
        opportunities=opportunities,
    )

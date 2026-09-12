"""Outils IA métier pour la synergie cross-agent (Phase 15).

Permet à AI Central d'exécuter des synthèses transversales et d'orchestrer
Retail Intelligence ↔ CRM AI ↔ Accounting AI dans une même requête sans rupture d'isolation.
"""

from __future__ import annotations

from typing import Any
from pydantic import Field
from sqlalchemy.orm import Session

from backend.app.ai.tools.base import AITool, ToolArguments
from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.services.cross_agent_intelligence_service import CrossAgentIntelligenceService


class CrossAgentGenericArgs(ToolArguments):
    pass


class GetCrossAgentBusinessHealthTool(AITool):
    name = "get_cross_agent_business_health"
    description = (
        "Synthèse exécutive 360° de l'entreprise reliant Retail Intelligence (ventes, commandes, alertes stocks), "
        "CRM AI (pipeline commercial, conversion, prospects chauds, risque de churn) et "
        "Accounting AI (CA confirmé, dépenses, marge brute %, factures impayées et prévision de trésorerie). "
        "À utiliser pour les questions transversales, les bilans complets d'activité ou la stratégie d'entreprise."
    )
    input_schema = CrossAgentGenericArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._service = CrossAgentIntelligenceService(session)

    async def run(self, context: ToolExecutionContext, arguments: CrossAgentGenericArgs) -> ToolResult:
        data = self._service.get_cross_domain_synthesis(context.tenant.company_id)
        return ToolResult(
            success=True,
            data=data,
            source_refs=("normalized_commerce_records", "crm_leads", "crm_opportunities", "accounting_transactions", "accounting_invoices"),
        )

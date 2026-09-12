"""Outils IA métier pour le module CRM AI (Phase 13).

Permet à AI Central et à l'assistant conversationnel de répondre avec précision
aux questions prospects, pipeline, scoring et churn sans jamais halluciner de données.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.ai.tools.base import AITool, ToolArguments
from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.services.crm_intelligence_service import CRMIntelligenceService


class CRMGenericArgs(ToolArguments):
    limit: int = Field(default=5, description="Nombre maximal d'enregistrements à retourner.")


class CRMLeadSearchArgs(ToolArguments):
    prospect_name: str | None = Field(
        default=None,
        description="Nom du prospect, contact ou entreprise pour la recommandation.",
    )


class GetCRMOverviewTool(AITool):
    name = "get_crm_overview"
    description = (
        "Fournit la vue d'ensemble du CRM de l'entreprise : nombre total de prospects, "
        "valeur totale du pipeline, valeur pondérée, taux de conversion et tâches en attente. "
        "À utiliser pour les questions de performance commerciale globale ou de synthèse CRM."
    )
    input_schema = CRMGenericArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._service = CRMIntelligenceService(session)

    async def run(self, context: ToolExecutionContext, arguments: CRMGenericArgs) -> ToolResult:
        data = self._service.get_crm_summary(context.tenant.company_id)
        return ToolResult(
            success=True,
            data=data,
            source_refs=("crm_summary",),
        )


class GetLeadsToContactTool(AITool):
    name = "get_leads_to_contact"
    description = (
        "Retourne la liste priorisée des prospects à contacter aujourd'hui, avec score IA, "
        "valeur estimée et motif de priorité. À utiliser quand l'utilisateur demande "
        "'Quels prospects dois-je contacter aujourd'hui ?' ou 'Quelles relances faire ?'."
    )
    input_schema = CRMGenericArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._service = CRMIntelligenceService(session)

    async def run(self, context: ToolExecutionContext, arguments: CRMGenericArgs) -> ToolResult:
        leads = self._service.get_leads_to_contact_today(
            context.tenant.company_id, limit=arguments.limit
        )
        return ToolResult(
            success=True,
            data={"count": len(leads), "leads_to_contact": leads},
            source_refs=("crm_leads",),
        )


class GetRankedLeadsTool(AITool):
    name = "get_ranked_leads"
    description = (
        "Classe les prospects par probabilité de conversion et score prédictif. "
        "À utiliser quand l'utilisateur demande 'Classe mes leads par probabilité de conversion' "
        "ou veut voir les prospects les plus chauds."
    )
    input_schema = CRMGenericArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._service = CRMIntelligenceService(session)

    async def run(self, context: ToolExecutionContext, arguments: CRMGenericArgs) -> ToolResult:
        ranked = self._service.get_leads_ranked_by_conversion(
            context.tenant.company_id, limit=arguments.limit
        )
        return ToolResult(
            success=True,
            data={"count": len(ranked), "ranked_leads": ranked},
            source_refs=("crm_leads",),
        )


class GetHighRiskCustomersTool(AITool):
    name = "get_high_risk_customers"
    description = (
        "Identifie les clients existants à risque d'attrition / départ (churn risk), "
        "avec niveau de risque, valeur client (CLV) et raison détectée par l'IA. "
        "À utiliser quand l'utilisateur demande 'Quels clients risquent de partir ?'."
    )
    input_schema = CRMGenericArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._service = CRMIntelligenceService(session)

    async def run(self, context: ToolExecutionContext, arguments: CRMGenericArgs) -> ToolResult:
        customers = self._service.get_high_risk_customers(
            context.tenant.company_id, limit=arguments.limit
        )
        return ToolResult(
            success=True,
            data={"count": len(customers), "high_risk_customers": customers},
            source_refs=("crm_contacts",),
        )


class GetTopRevenueDealsTool(AITool):
    name = "get_top_revenue_deals"
    description = (
        "Identifie les opportunités commerciales et prospects représentant le plus de revenus potentiels. "
        "À utiliser quand l'utilisateur demande 'Quels clients représentent le plus de revenus potentiels ?' "
        "ou 'Quels sont mes plus gros deals en cours ?'."
    )
    input_schema = CRMGenericArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._service = CRMIntelligenceService(session)

    async def run(self, context: ToolExecutionContext, arguments: CRMGenericArgs) -> ToolResult:
        deals = self._service.get_top_potential_revenue(
            context.tenant.company_id, limit=arguments.limit
        )
        return ToolResult(
            success=True,
            data={"count": len(deals), "top_deals": deals},
            source_refs=("crm_opportunities",),
        )


class GetFollowUpRecommendationTool(AITool):
    name = "get_follow_up_recommendation"
    description = (
        "Génère une recommandation de suivi et une prochaine action recommandée (Next Best Action) "
        "pour un prospect ou client donné. À utiliser pour 'Génère une recommandation de suivi'."
    )
    input_schema = CRMLeadSearchArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._service = CRMIntelligenceService(session)

    async def run(self, context: ToolExecutionContext, arguments: CRMLeadSearchArgs) -> ToolResult:
        query = arguments.prospect_name or ""
        rec = self._service.generate_follow_up_recommendation(
            context.tenant.company_id, query=query
        )
        return ToolResult(
            success=True,
            data=rec,
            source_refs=("crm_leads",),
        )

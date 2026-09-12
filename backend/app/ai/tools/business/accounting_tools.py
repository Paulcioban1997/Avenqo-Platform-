"""Outils IA métier pour le module Accounting AI (Phase 14).

Permet à AI Central et à l'assistant conversationnel de répondre avec exactitude
aux questions financières, dépenses, marges, factures impayées, prévisions de cash flow
et anomalies comptables en garantissant la séparation stricte données confirmées / projections IA.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.ai.tools.base import AITool, ToolArguments
from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.services.accounting_intelligence_service import AccountingIntelligenceService


class AccountingGenericArgs(ToolArguments):
    pass


class MonthlyExpensesArgs(ToolArguments):
    year: int | None = Field(default=None, description="Année cible (ex: 2026). Par défaut, année courante.")
    month: int | None = Field(default=None, description="Mois cible (1 à 12). Par défaut, mois courant.")


class UnpaidInvoicesArgs(ToolArguments):
    invoice_type: str = Field(
        default="receivable",
        description="Type de facture: 'receivable' (factures clients impayées) ou 'payable' (factures fournisseurs à payer).",
    )


class CashFlowForecastArgs(ToolArguments):
    horizon_days: int = Field(
        default=30,
        description="Horizon de prévision en jours (ex: 30, 60, 90). Par défaut 30 jours.",
    )


class ExpenseAnomaliesArgs(ToolArguments):
    threshold_multiplier: float = Field(
        default=2.0,
        description="Multiplicateur au-dessus de la moyenne de catégorie pour qualifier une dépense d'anomalie.",
    )


class GetFinancialOverviewTool(AITool):
    name = "get_financial_overview"
    description = (
        "Fournit la synthèse financière globale de l'entreprise : chiffre d'affaires total confirmé, "
        "dépenses totales confirmées, résultat net, marge brute %, créances clients en attente et dettes fournisseurs. "
        "À utiliser pour un bilan financier général ou un résumé comptable."
    )
    input_schema = AccountingGenericArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._service = AccountingIntelligenceService(session)

    async def run(self, context: ToolExecutionContext, arguments: AccountingGenericArgs) -> ToolResult:
        data = self._service.get_financial_overview(context.tenant.company_id)
        return ToolResult(
            success=True,
            data=data,
            source_refs=("accounting_transactions", "accounting_invoices"),
        )


class GetMonthlyExpensesTool(AITool):
    name = "get_monthly_expenses"
    description = (
        "Retourne le total des dépenses du mois courant (ou spécifié), la ventilation par catégorie "
        "(COGS, marketing, salaires, logiciels, etc.), la comparaison avec le mois précédent et les dernières dépenses. "
        "À utiliser quand l'utilisateur demande 'Combien ai-je dépensé ce mois-ci ?' ou 'Quelles sont mes dépenses ?'."
    )
    input_schema = MonthlyExpensesArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._service = AccountingIntelligenceService(session)

    async def run(self, context: ToolExecutionContext, arguments: MonthlyExpensesArgs) -> ToolResult:
        data = self._service.get_monthly_expenses(
            context.tenant.company_id,
            year=arguments.year,
            month=arguments.month,
        )
        return ToolResult(
            success=True,
            data=data,
            source_refs=("accounting_transactions",),
        )


class GetProfitMarginTool(AITool):
    name = "get_profit_margin"
    description = (
        "Calcule la marge brute ($ et %), la marge opérationnelle ($ et %), les revenus totaux "
        "et le coût des marchandises vendues (COGS). "
        "À utiliser quand l'utilisateur demande 'Quelle est ma marge ?' ou 'Quelle est ma rentabilité ?'."
    )
    input_schema = AccountingGenericArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._service = AccountingIntelligenceService(session)

    async def run(self, context: ToolExecutionContext, arguments: AccountingGenericArgs) -> ToolResult:
        data = self._service.get_profit_margin(context.tenant.company_id)
        return ToolResult(
            success=True,
            data=data,
            source_refs=("accounting_transactions",),
        )


class GetUnpaidInvoicesTool(AITool):
    name = "get_unpaid_invoices"
    description = (
        "Fournit la liste détaillée des factures impayées et en retard (clients ou fournisseurs), "
        "avec montants restants dus, date d'échéance et nombre de jours de retard. "
        "À utiliser quand l'utilisateur demande 'Quels clients ont des factures impayées ?' ou 'Quelles factures sont en retard ?'."
    )
    input_schema = UnpaidInvoicesArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._service = AccountingIntelligenceService(session)

    async def run(self, context: ToolExecutionContext, arguments: UnpaidInvoicesArgs) -> ToolResult:
        data = self._service.get_unpaid_invoices(
            context.tenant.company_id,
            invoice_type=arguments.invoice_type,
        )
        return ToolResult(
            success=True,
            data=data,
            source_refs=("accounting_invoices",),
        )


class GetExpenseAnomaliesTool(AITool):
    name = "get_expense_anomalies"
    description = (
        "Détecte les dépenses inhabituelles, anormalement élevées ou atypiques par rapport à la moyenne de leur catégorie. "
        "À utiliser quand l'utilisateur demande 'Y a-t-il des dépenses suspectes ou anormales ?' ou 'Détecte les anomalies de dépenses'."
    )
    input_schema = ExpenseAnomaliesArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._service = AccountingIntelligenceService(session)

    async def run(self, context: ToolExecutionContext, arguments: ExpenseAnomaliesArgs) -> ToolResult:
        data = self._service.get_expense_anomalies(
            context.tenant.company_id,
            threshold_multiplier=arguments.threshold_multiplier,
        )
        return ToolResult(
            success=True,
            data=data,
            source_refs=("accounting_transactions",),
        )


class GetCashFlowForecastTool(AITool):
    name = "get_cash_flow_forecast"
    description = (
        "Génère une prévision prédictive de trésorerie (Cash Flow Forecast) sur 30, 60 ou 90 jours "
        "en combinant le solde réel, les encaissements prévus des factures clients, les décaissements et le burn rate récurrent. "
        "Clairement identifiée comme prédiction IA. "
        "À utiliser quand l'utilisateur demande 'Quelle est ma prévision de trésorerie ?' ou 'Mon cash flow à 30 jours ?'."
    )
    input_schema = CashFlowForecastArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._service = AccountingIntelligenceService(session)

    async def run(self, context: ToolExecutionContext, arguments: CashFlowForecastArgs) -> ToolResult:
        data = self._service.get_cash_flow_forecast(
            context.tenant.company_id,
            horizon_days=arguments.horizon_days,
        )
        return ToolResult(
            success=True,
            data=data,
            source_refs=("accounting_transactions", "accounting_invoices"),
        )

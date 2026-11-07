"""Outils IA métier pour le module Accounting AI (Phase 14).

Permet à AI Central et à l'assistant conversationnel de répondre avec exactitude
aux questions financières, dépenses, marges, factures impayées, prévisions de cash flow
et anomalies comptables en garantissant la séparation stricte données confirmées / projections IA.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.ai.tools.base import AccountingAITool, AITool, ToolArguments
from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.models.accounting import AccountingInvoice
from backend.app.services.accounting_intelligence_service import AccountingIntelligenceService
from backend.app.services.secure_document_token_service import SecureDocumentTokenService


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


class SearchInvoicesArgs(ToolArguments):
    query: str = Field(default="", description="Recherche par numéro de facture ou nom de tiers/client/fournisseur.")
    invoice_type: str | None = Field(default=None, description="Type de facture : 'receivable' (client) ou 'payable' (fournisseur).")
    status: str | None = Field(default=None, description="Statut : 'paid', 'unpaid', 'overdue', 'partial'.")
    limit: int = Field(default=10, description="Nombre maximal de factures retournées (1 à 25).")


class GetInvoiceDetailArgs(ToolArguments):
    invoice_id: str | None = Field(default=None, description="Identifiant UUID de la facture.")
    invoice_number: str | None = Field(default=None, description="Numéro officiel de la facture (ex: FAC-2026-001).")


class GetInvoiceDownloadUrlArgs(ToolArguments):
    invoice_id: str = Field(description="Identifiant UUID de la facture à télécharger en PDF.")


class GetFinancialOverviewTool(AccountingAITool):
    name = "get_financial_overview"
    description = (
        "Fournit la synthèse financière globale de l'entreprise : chiffre d'affaires total confirmé, "
        "dépenses totales confirmées, résultat net, marge brute %, créances clients en attente et dettes fournisseurs. "
        "À utiliser pour un bilan financier général ou un résumé comptable."
    )
    input_schema = AccountingGenericArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session) -> None:
        self._service = AccountingIntelligenceService(session)

    async def run(self, context: ToolExecutionContext, arguments: AccountingGenericArgs) -> ToolResult:
        data = self._service.get_financial_overview(context.tenant.company_id)
        return ToolResult(
            success=True,
            data=data,
            source_refs=("accounting_transactions", "accounting_invoices"),
        )


class GetMonthlyExpensesTool(AccountingAITool):
    name = "get_monthly_expenses"
    description = (
        "Retourne le total des dépenses du mois courant (ou spécifié), la ventilation par catégorie "
        "(COGS, marketing, salaires, logiciels, etc.), la comparaison avec le mois précédent et les dernières dépenses. "
        "À utiliser quand l'utilisateur demande 'Combien ai-je dépensé ce mois-ci ?' ou 'Quelles sont mes dépenses ?'."
    )
    input_schema = MonthlyExpensesArgs
    required_permissions = ("ai:use", "data:read")

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


class GetProfitMarginTool(AccountingAITool):
    name = "get_profit_margin"
    description = (
        "Calcule la marge brute ($ et %), la marge opérationnelle ($ et %), les revenus totaux "
        "et le coût des marchandises vendues (COGS). "
        "À utiliser quand l'utilisateur demande 'Quelle est ma marge ?' ou 'Quelle est ma rentabilité ?'."
    )
    input_schema = AccountingGenericArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session) -> None:
        self._service = AccountingIntelligenceService(session)

    async def run(self, context: ToolExecutionContext, arguments: AccountingGenericArgs) -> ToolResult:
        data = self._service.get_profit_margin(context.tenant.company_id)
        return ToolResult(
            success=True,
            data=data,
            source_refs=("accounting_transactions",),
        )


class GetUnpaidInvoicesTool(AccountingAITool):
    name = "get_unpaid_invoices"
    description = (
        "Fournit la liste détaillée des factures impayées et en retard (clients ou fournisseurs), "
        "avec montants restants dus, date d'échéance et nombre de jours de retard. "
        "À utiliser quand l'utilisateur demande 'Quels clients ont des factures impayées ?' ou 'Quelles factures sont en retard ?'."
    )
    input_schema = UnpaidInvoicesArgs
    required_permissions = ("ai:use", "data:read")

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


class GetExpenseAnomaliesTool(AccountingAITool):
    name = "get_expense_anomalies"
    description = (
        "Détecte les dépenses inhabituelles, anormalement élevées ou atypiques par rapport à la moyenne de leur catégorie. "
        "À utiliser quand l'utilisateur demande 'Y a-t-il des dépenses suspectes ou anormales ?' ou 'Détecte les anomalies de dépenses'."
    )
    input_schema = ExpenseAnomaliesArgs
    required_permissions = ("ai:use", "data:read")

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


class GetCashFlowForecastTool(AccountingAITool):
    name = "get_cash_flow_forecast"
    description = (
        "Génère une prévision prédictive de trésorerie (Cash Flow Forecast) sur 30, 60 ou 90 jours "
        "en combinant le solde réel, les encaissements prévus des factures clients, les décaissements et le burn rate récurrent. "
        "Clairement identifiée comme prédiction IA. "
        "À utiliser quand l'utilisateur demande 'Quelle est ma prévision de trésorerie ?' ou 'Mon cash flow à 30 jours ?'."
    )
    input_schema = CashFlowForecastArgs
    required_permissions = ("ai:use", "data:read")

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


class ReconcileSalesAndAccountingTool(AccountingAITool):
    name = "reconcile_sales_and_accounting"
    description = (
        "Compare les ventes e-commerce enregistrées avec le chiffre d'affaires et les écritures comptables confirmées. "
        "Identifie avec exactitude tout écart sans fabriquer ni forcer de réconciliation artificielle. "
        "À utiliser pour l'audit croisé entre le module Retail AI et Accounting AI."
    )
    input_schema = AccountingGenericArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session) -> None:
        self._service = AccountingIntelligenceService(session)

    async def run(self, context: ToolExecutionContext, arguments: AccountingGenericArgs) -> ToolResult:
        data = self._service.reconcile_sales_with_accounting(context.tenant.company_id)
        return ToolResult(
            success=True,
            data=data,
            source_refs=("normalized_commerce_records", "accounting_transactions"),
        )


class SearchInvoicesTool(AccountingAITool):
    name = "search_invoices"
    description = (
        "Recherche parmi les factures clients (créances) et fournisseurs (dettes) de l'entreprise. "
        "Filtre par numéro, nom de tiers, type ou statut de paiement."
    )
    input_schema = SearchInvoicesArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session) -> None:
        self._session = session

    async def run(self, context: ToolExecutionContext, arguments: SearchInvoicesArgs) -> ToolResult:
        query = select(AccountingInvoice).where(AccountingInvoice.company_id == context.tenant.company_id)

        if arguments.invoice_type:
            query = query.where(AccountingInvoice.invoice_type == arguments.invoice_type)

        if arguments.status:
            query = query.where(AccountingInvoice.status == arguments.status)

        search_term = arguments.query.strip()
        if search_term:
            query = query.where(
                or_(
                    AccountingInvoice.invoice_number.ilike(f"%{search_term}%"),
                    AccountingInvoice.party_name.ilike(f"%{search_term}%"),
                    AccountingInvoice.notes.ilike(f"%{search_term}%"),
                )
            )

        limit = max(1, min(arguments.limit, 25))
        query = query.order_by(AccountingInvoice.issue_date.desc()).limit(limit)

        records = self._session.scalars(query).all()
        results = [
            {
                "invoice_id": str(inv.id),
                "invoice_number": inv.invoice_number,
                "invoice_type": inv.invoice_type,
                "party_name": inv.party_name,
                "issue_date": inv.issue_date.strftime("%Y-%m-%d") if inv.issue_date else None,
                "due_date": inv.due_date.strftime("%Y-%m-%d") if inv.due_date else None,
                "total_amount": inv.total_amount,
                "paid_amount": inv.paid_amount,
                "remaining_amount": inv.remaining_amount,
                "currency": inv.currency,
                "status": inv.status,
                "is_confirmed": inv.is_confirmed,
            }
            for inv in records
        ]

        return ToolResult(
            success=True,
            data={
                "count": len(results),
                "invoices": results,
                "message": (
                    f"{len(results)} facture(s) trouvée(s) pour la recherche '{arguments.query}'."
                    if results
                    else f"Aucune facture trouvée pour la recherche '{arguments.query}'."
                ),
            },
            source_refs=("accounting_invoices",),
        )


class GetInvoiceDetailTool(AccountingAITool):
    name = "get_invoice_detail"
    description = (
        "Consulte le détail précis et complet d'une facture client ou fournisseur (montants, dates, statut, tiers)."
    )
    input_schema = GetInvoiceDetailArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session) -> None:
        self._session = session

    async def run(self, context: ToolExecutionContext, arguments: GetInvoiceDetailArgs) -> ToolResult:
        query = select(AccountingInvoice).where(AccountingInvoice.company_id == context.tenant.company_id)

        if arguments.invoice_id:
            try:
                inv_uuid = UUID(arguments.invoice_id)
                query = query.where(AccountingInvoice.id == inv_uuid)
            except ValueError:
                return ToolResult(success=False, error="Format UUID de facture invalide")
        elif arguments.invoice_number:
            query = query.where(AccountingInvoice.invoice_number == arguments.invoice_number.strip())
        else:
            return ToolResult(success=False, error="Veuillez fournir un 'invoice_id' ou un 'invoice_number'.")

        invoice = self._session.scalar(query)
        if invoice is None:
            return ToolResult(
                success=False,
                error="Facture introuvable ou vous n'avez pas l'autorisation d'y accéder.",
            )

        sanitized_notes = invoice.notes or ""
        if "</untrusted_document_data>" in sanitized_notes:
            sanitized_notes = sanitized_notes.replace("</untrusted_document_data>", "[TAG_NEUTRALIZED]")

        return ToolResult(
            success=True,
            data={
                "invoice_id": str(invoice.id),
                "invoice_number": invoice.invoice_number,
                "invoice_type": invoice.invoice_type,
                "party_name": invoice.party_name,
                "issue_date": invoice.issue_date.strftime("%Y-%m-%d") if invoice.issue_date else None,
                "due_date": invoice.due_date.strftime("%Y-%m-%d") if invoice.due_date else None,
                "total_amount": invoice.total_amount,
                "paid_amount": invoice.paid_amount,
                "remaining_amount": invoice.remaining_amount,
                "currency": invoice.currency,
                "status": invoice.status,
                "is_confirmed": invoice.is_confirmed,
                "notes": sanitized_notes,
            },
            source_refs=("accounting_invoices",),
        )


class GetInvoiceDownloadUrlTool(AccountingAITool):
    name = "get_invoice_download_url"
    description = (
        "Génère une URL de téléchargement PDF officielle et sécurisée (15 minutes) pour une facture de l'entreprise. "
        "Le jeton cryptographique HMAC est lié exclusivement à votre session et votre entreprise."
    )
    input_schema = GetInvoiceDownloadUrlArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session) -> None:
        self._session = session
        self._token_service = SecureDocumentTokenService()

    async def run(self, context: ToolExecutionContext, arguments: GetInvoiceDownloadUrlArgs) -> ToolResult:
        try:
            inv_uuid = UUID(arguments.invoice_id)
        except ValueError:
            return ToolResult(success=False, error="Format UUID de facture invalide")

        invoice = self._session.scalar(
            select(AccountingInvoice).where(
                AccountingInvoice.id == inv_uuid,
                AccountingInvoice.company_id == context.tenant.company_id,
            )
        )
        if invoice is None:
            return ToolResult(
                success=False,
                error="Facture introuvable ou vous n'avez pas l'autorisation d'y accéder.",
            )

        filename = f"facture_{invoice.invoice_number}.pdf"
        token = self._token_service.generate_download_token(
            company_id=context.tenant.company_id,
            user_id=context.tenant.user_id,
            doc_id=invoice.id,
            doc_type="invoice",
            filename=filename,
            expires_in_seconds=900,
        )

        download_url = f"/api/v1/secure-downloads/{token}"

        return ToolResult(
            success=True,
            data={
                "invoice_id": str(invoice.id),
                "invoice_number": invoice.invoice_number,
                "filename": filename,
                "download_url": download_url,
                "expires_in_seconds": 900,
                "message": (
                    f"Lien de téléchargement sécurisé généré pour la facture {invoice.invoice_number}. "
                    f"Ce lien est valable 15 minutes et accessible uniquement par votre compte."
                ),
            },
            source_refs=("accounting_invoices",),
        )

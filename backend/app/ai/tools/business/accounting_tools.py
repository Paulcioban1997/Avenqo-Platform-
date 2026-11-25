"""Outils IA métier pour le module Accounting AI (Phase 14 & Phases D/E Unification).

Permet à AI Central, Accounting AI et Voice AI (personnel authentifié uniquement) de répondre
avec exactitude aux questions financières, dépenses, marges, factures, provenance documentaire,
réconciliation e-commerce, anomalies/doublons et prévisions de cash flow, en garantissant :
- la séparation stricte écritures confirmées vs propositions `to_verify` vs projections IA ;
- le blocage absolu des appelants vocaux publics ;
- le cloisonnement strict des coûts salariaux RH (uniquement rôles exécutifs autorisés + module HR actif).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.ai.tools.base import AccountingAITool, ToolArguments
from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.models.accounting import AccountingInvoice
from backend.app.models.user import User
from backend.app.services.accounting_intelligence_service import AccountingIntelligenceService
from backend.app.services.accounting_source_scope import (
    apply_dataset_scope,
    resolve_accounting_dataset_scope,
)
from backend.app.services.financial_integration_service import (
    FinancialIntegrationService,
    can_access_hr_payroll_summary,
)
from backend.app.services.secure_document_token_service import SecureDocumentTokenService
from backend.app.voice.caller_scope import is_public_voice_caller


def _guard_accounting_context(session: Session, context: ToolExecutionContext) -> tuple[User | None, ToolResult | None]:
    """Bloque tout appelant vocal public et vérifie l'appartenance tenant si l'utilisateur existe en base."""
    if is_public_voice_caller(context.permissions):
        return None, ToolResult(
            success=False,
            error="Accès refusé : les données comptables et financières sont strictement confidentielles.",
        )

    actor_user: User | None = None
    uid = context.user_id or context.tenant.user_id
    if uid is not None:
        actor_user = session.get(User, uid)
        if actor_user is not None:
            if not actor_user.is_active or actor_user.company_id != context.tenant.company_id:
                return None, ToolResult(
                    success=False,
                    error="Accès refusé : isolation multi-tenant ou compte inactif.",
                )
    return actor_user, None


class AccountingGenericArgs(ToolArguments):
    include_unified_sources: bool = Field(
        default=True,
        description="Inclure le contexte financier unifié des modules autorisés (Retail, CRM, OCR, HR agrégé si exécutif).",
    )


class MonthlyExpensesArgs(ToolArguments):
    year: int | None = Field(default=None, description="Année cible (ex: 2026). Par défaut, année courante.")
    month: int | None = Field(default=None, description="Mois cible (1 à 12). Par défaut, mois courant.")


class UnpaidInvoicesArgs(ToolArguments):
    invoice_type: str = Field(
        default="receivable",
        description="Type de facture: 'receivable' (factures clients impayées) ou 'payable' (factures fournisseurs à payer).",
    )
    include_to_verify: bool = Field(
        default=False,
        description="Inclure les propositions de factures non confirmées ('to_verify'). Par défaut False (confirmées uniquement).",
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
    invoice_type: str | None = Field(
        default=None,
        description="Type de facture : 'receivable' (client), 'payable' (fournisseur), 'credit_note' (avoir), 'refund'.",
    )
    document_nature: str | None = Field(
        default=None,
        description="Nature documentaire : 'supplier_invoice', 'customer_invoice', 'receipt', 'credit_note', 'refund', 'transfer', 'non_posting'.",
    )
    status: str | None = Field(default=None, description="Statut : 'paid', 'unpaid', 'overdue', 'partial', 'to_verify', 'rejected'.")
    verification_status: str | None = Field(
        default=None,
        description="Statut de gouvernance : 'confirmed', 'to_verify', 'approved', 'rejected', 'verified_connector'.",
    )
    duplicate_only: bool = Field(default=False, description="Si True, retourne uniquement les factures signalées comme doublons potentiels.")
    limit: int = Field(default=10, description="Nombre maximal de factures retournées (1 à 25).")


class GetInvoiceDetailArgs(ToolArguments):
    invoice_id: str | None = Field(default=None, description="Identifiant UUID de la facture.")
    invoice_number: str | None = Field(default=None, description="Numéro officiel de la facture (ex: FAC-2026-001).")


class GetInvoiceDownloadUrlArgs(ToolArguments):
    invoice_id: str = Field(description="Identifiant UUID de la facture à télécharger en PDF.")


class GetFinancialOverviewTool(AccountingAITool):
    name = "get_financial_overview"
    description = (
        "Fournit la synthèse financière globale de l'entreprise : chiffre d'affaires net confirmé (après remboursements/avoirs), "
        "dépenses totales confirmées, résultat net, marge brute %, taxes documentées, créances clients (AR), dettes fournisseurs (AP), "
        "propositions en attente de validation ('to_verify') et contexte unifié multi-modules autorisé."
    )
    input_schema = AccountingGenericArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session) -> None:
        self._session = session
        self._service = AccountingIntelligenceService(session)
        self._integration = FinancialIntegrationService(session)

    async def run(self, context: ToolExecutionContext, arguments: AccountingGenericArgs) -> ToolResult:
        actor_user, denied = _guard_accounting_context(self._session, context)
        if denied is not None:
            return denied

        dataset_ids, source_context = resolve_accounting_dataset_scope(self._session, context.tenant)
        data = dict(self._service.get_financial_overview(context.tenant.company_id, dataset_ids=dataset_ids))
        data["source_context"] = source_context
        if arguments.include_unified_sources and actor_user is not None:
            data["unified_sources"] = self._integration.get_unified_financial_context(
                context.tenant.company_id,
                actor_user=actor_user,
            )
        return ToolResult(
            success=True,
            data=data,
            source_refs=("accounting_transactions", "accounting_invoices"),
        )


class GetMonthlyExpensesTool(AccountingAITool):
    name = "get_monthly_expenses"
    description = (
        "Retourne le total des dépenses confirmées du mois courant (ou spécifié), la ventilation par catégorie "
        "(COGS, marketing, salaires, logiciels, frais de paiement, etc.), la comparaison mensuelle et les propositions fournisseurs en attente."
    )
    input_schema = MonthlyExpensesArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session) -> None:
        self._session = session
        self._service = AccountingIntelligenceService(session)

    async def run(self, context: ToolExecutionContext, arguments: MonthlyExpensesArgs) -> ToolResult:
        actor_user, denied = _guard_accounting_context(self._session, context)
        if denied is not None:
            return denied

        can_payroll = (
            True
            if actor_user is None
            else can_access_hr_payroll_summary(self._session, context.tenant.company_id, actor_user)[0]
        )
        dataset_ids, source_context = resolve_accounting_dataset_scope(self._session, context.tenant)
        data = self._service.get_monthly_expenses(
            context.tenant.company_id,
            dataset_ids=dataset_ids,
            year=arguments.year,
            month=arguments.month,
            include_payroll=can_payroll,
        )
        data["source_context"] = source_context
        return ToolResult(
            success=True,
            data=data,
            source_refs=("accounting_transactions",),
        )


class GetProfitMarginTool(AccountingAITool):
    name = "get_profit_margin"
    description = (
        "Calcule la marge brute ($ et %), la marge opérationnelle ($ et %), les revenus nets de remboursements/avoirs "
        "et le coût vérifiable des marchandises vendues (COGS)."
    )
    input_schema = AccountingGenericArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session) -> None:
        self._session = session
        self._service = AccountingIntelligenceService(session)

    async def run(self, context: ToolExecutionContext, arguments: AccountingGenericArgs) -> ToolResult:
        _, denied = _guard_accounting_context(self._session, context)
        if denied is not None:
            return denied

        dataset_ids, source_context = resolve_accounting_dataset_scope(self._session, context.tenant)
        data = self._service.get_profit_margin(context.tenant.company_id, dataset_ids=dataset_ids)
        data["source_context"] = source_context
        return ToolResult(
            success=True,
            data=data,
            source_refs=("accounting_transactions",),
        )


class GetUnpaidInvoicesTool(AccountingAITool):
    name = "get_unpaid_invoices"
    description = (
        "Fournit la liste détaillée des factures impayées et en retard (clients AR ou fournisseurs AP), "
        "avec montants restants dus, date d'échéance, statut de validation et nombre de jours de retard."
    )
    input_schema = UnpaidInvoicesArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session) -> None:
        self._session = session
        self._service = AccountingIntelligenceService(session)

    async def run(self, context: ToolExecutionContext, arguments: UnpaidInvoicesArgs) -> ToolResult:
        _, denied = _guard_accounting_context(self._session, context)
        if denied is not None:
            return denied

        dataset_ids, source_context = resolve_accounting_dataset_scope(self._session, context.tenant)
        data = self._service.get_unpaid_invoices(
            context.tenant.company_id,
            dataset_ids=dataset_ids,
            invoice_type=arguments.invoice_type,
            include_to_verify=arguments.include_to_verify,
        )
        data["source_context"] = source_context
        return ToolResult(
            success=True,
            data=data,
            source_refs=("accounting_invoices",),
        )


class GetExpenseAnomaliesTool(AccountingAITool):
    name = "get_expense_anomalies"
    description = (
        "Détecte les dépenses inhabituelles ou anormalement élevées par rapport à la moyenne de leur catégorie, "
        "ainsi que les alertes de factures potentiellement en doublon."
    )
    input_schema = ExpenseAnomaliesArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session) -> None:
        self._session = session
        self._service = AccountingIntelligenceService(session)

    async def run(self, context: ToolExecutionContext, arguments: ExpenseAnomaliesArgs) -> ToolResult:
        actor_user, denied = _guard_accounting_context(self._session, context)
        if denied is not None:
            return denied

        can_payroll = (
            True
            if actor_user is None
            else can_access_hr_payroll_summary(self._session, context.tenant.company_id, actor_user)[0]
        )
        dataset_ids, source_context = resolve_accounting_dataset_scope(self._session, context.tenant)
        data = self._service.get_expense_anomalies(
            context.tenant.company_id,
            dataset_ids=dataset_ids,
            threshold_multiplier=arguments.threshold_multiplier,
            include_payroll=can_payroll,
        )
        data["source_context"] = source_context
        return ToolResult(
            success=True,
            data=data,
            source_refs=("accounting_transactions", "accounting_invoices"),
        )


class GetCashFlowForecastTool(AccountingAITool):
    name = "get_cash_flow_forecast"
    description = (
        "Génère une prévision prédictive de trésorerie (Cash Flow Forecast) sur 30, 60 ou 90 jours "
        "en combinant le solde réel confirmé, les encaissements clients et décaissements fournisseurs confirmés "
        "et le burn rate récurrent (les propositions non vérifiées sont exclues et signalées)."
    )
    input_schema = CashFlowForecastArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session) -> None:
        self._session = session
        self._service = AccountingIntelligenceService(session)

    async def run(self, context: ToolExecutionContext, arguments: CashFlowForecastArgs) -> ToolResult:
        _, denied = _guard_accounting_context(self._session, context)
        if denied is not None:
            return denied

        dataset_ids, source_context = resolve_accounting_dataset_scope(self._session, context.tenant)
        data = self._service.get_cash_flow_forecast(
            context.tenant.company_id,
            dataset_ids=dataset_ids,
            horizon_days=arguments.horizon_days,
        )
        data["source_context"] = source_context
        return ToolResult(
            success=True,
            data=data,
            source_refs=("accounting_transactions", "accounting_invoices"),
        )


class ReconcileSalesAndAccountingTool(AccountingAITool):
    name = "reconcile_sales_and_accounting"
    description = (
        "Réconcilie avec exactitude les commandes e-commerce Retail AI, les paiements encaissés, les taxes documentées, "
        "les remboursements/avoirs et les factures/écritures comptables confirmées sans inventer de rapprochement."
    )
    input_schema = AccountingGenericArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session) -> None:
        self._session = session
        self._service = AccountingIntelligenceService(session)

    async def run(self, context: ToolExecutionContext, arguments: AccountingGenericArgs) -> ToolResult:
        _, denied = _guard_accounting_context(self._session, context)
        if denied is not None:
            return denied

        dataset_ids, source_context = resolve_accounting_dataset_scope(self._session, context.tenant)
        data = self._service.reconcile_sales_with_accounting(
            context.tenant.company_id, dataset_ids=dataset_ids
        )
        data["source_context"] = source_context
        return ToolResult(
            success=True,
            data=data,
            source_refs=("normalized_commerce_records", "accounting_transactions", "accounting_invoices"),
        )


class SearchInvoicesTool(AccountingAITool):
    name = "search_invoices"
    description = (
        "Recherche parmi les factures clients (créances), factures fournisseurs (dettes), reçus, avoirs et propositions "
        "à vérifier ('to_verify') de l'entreprise. Filtre par numéro, tiers, type, nature, statut ou doublon."
    )
    input_schema = SearchInvoicesArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session) -> None:
        self._session = session

    async def run(self, context: ToolExecutionContext, arguments: SearchInvoicesArgs) -> ToolResult:
        _, denied = _guard_accounting_context(self._session, context)
        if denied is not None:
            return denied

        dataset_ids, _source_context = resolve_accounting_dataset_scope(self._session, context.tenant)
        query = select(AccountingInvoice).where(
            AccountingInvoice.company_id == context.tenant.company_id,
            apply_dataset_scope(AccountingInvoice.dataset_id, dataset_ids),
        )

        if arguments.invoice_type:
            query = query.where(AccountingInvoice.invoice_type == arguments.invoice_type)
        if arguments.document_nature:
            query = query.where(AccountingInvoice.document_nature == arguments.document_nature)
        if arguments.status:
            query = query.where(AccountingInvoice.status == arguments.status)
        if arguments.verification_status:
            query = query.where(AccountingInvoice.verification_status == arguments.verification_status)
        if arguments.duplicate_only:
            query = query.where(AccountingInvoice.duplicate_warning.is_(True))

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
                "document_nature": inv.document_nature,
                "direction": inv.direction,
                "company_role": inv.company_role,
                "party_name": inv.party_name,
                "issue_date": inv.issue_date.strftime("%Y-%m-%d") if inv.issue_date else None,
                "due_date": inv.due_date.strftime("%Y-%m-%d") if inv.due_date else None,
                "subtotal_amount": inv.subtotal_amount,
                "tax_amount": inv.tax_amount,
                "total_amount": inv.total_amount,
                "paid_amount": inv.paid_amount,
                "remaining_amount": inv.remaining_amount,
                "currency": inv.currency,
                "status": inv.status,
                "is_confirmed": inv.is_confirmed,
                "verification_status": inv.verification_status,
                "accounting_status": inv.accounting_status,
                "duplicate_warning": inv.duplicate_warning,
                "source_module": inv.source_module,
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
        "Consulte le détail précis et complet d'une facture ou d'un avoir : provenance documentaire, lignes, "
        "sous-total et taxes, justification de classification, avertissements de doublons, écritures liées et historique."
    )
    input_schema = GetInvoiceDetailArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session) -> None:
        self._session = session
        self._intel = AccountingIntelligenceService(session)

    async def run(self, context: ToolExecutionContext, arguments: GetInvoiceDetailArgs) -> ToolResult:
        _, denied = _guard_accounting_context(self._session, context)
        if denied is not None:
            return denied

        inv_uuid: UUID | None = None
        if arguments.invoice_id:
            try:
                inv_uuid = UUID(arguments.invoice_id)
            except ValueError:
                return ToolResult(success=False, error="Format UUID de facture invalide")
        elif not arguments.invoice_number:
            return ToolResult(success=False, error="Veuillez fournir un 'invoice_id' ou un 'invoice_number'.")

        detail = self._intel.get_invoice_detail_enriched(
            context.tenant.company_id,
            invoice_id=inv_uuid,
            invoice_number=arguments.invoice_number,
        )
        if detail is None:
            return ToolResult(
                success=False,
                error="Facture introuvable ou vous n'avez pas l'autorisation d'y accéder.",
            )

        return ToolResult(
            success=True,
            data=detail,
            source_refs=("accounting_invoices", "accounting_transactions"),
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
        _, denied = _guard_accounting_context(self._session, context)
        if denied is not None:
            return denied

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

        user_id = context.user_id or context.tenant.user_id
        if user_id is None:
            return ToolResult(
                success=False,
                error="Utilisateur non authentifié pour générer un lien de téléchargement sécurisé.",
            )

        filename = f"facture_{invoice.invoice_number}.pdf"
        token = self._token_service.generate_download_token(
            company_id=context.tenant.company_id,
            user_id=user_id,
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

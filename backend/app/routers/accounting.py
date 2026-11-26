"""Routes API pour le module Accounting AI (Phase 14 & Phases D/E Unification).

Fournit les écritures comptables confirmées, la synthèse unifiée multi-modules,
la classification automatique sensible au rôle de l'entreprise, la gouvernance des propositions
(`to_verify`), la révision manuelle auditée, la détection de doublons, la réconciliation
inter-modules et l'isolation stricte RBAC / multi-tenant.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.app.core.cache import tenant_cache
from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity, get_tenant_context
from backend.app.models.accounting import AccountingInvoice, AccountingTransaction
from backend.app.services.accounting_classification_service import (
    AccountingClassificationError,
    AccountingClassificationService,
    DuplicateConfirmationRequiredError,
)
from backend.app.services.accounting_intelligence_service import AccountingIntelligenceService
from backend.app.services.accounting_source_scope import (
    apply_dataset_scope,
    resolve_accounting_dataset_scope,
)
from backend.app.services.financial_integration_service import (
    FinancialIntegrationService,
    HRPayrollAccessDeniedError,
    PAYROLL_CATEGORIES,
    can_access_hr_payroll_summary,
)
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from shared.ai_engine.contracts import TenantContext


def require_accounting_module(
    request: Request,
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> None:
    from backend.app.core.permission_grants import effective_permissions

    held = set(effective_permissions(identity.user))
    writing = request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}
    needed = "accounting:write" if writing else "accounting:read"
    if needed not in held:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission insuffisante")
    tenant = TenantContext(company_id=identity.user.company_id, user_id=identity.user.id)
    if not ModuleEntitlementService(db).can_use_module(tenant, "accounting"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "module_inactive", "module": "accounting"},
        )


router = APIRouter(
    prefix="/accounting",
    tags=["accounting"],
    dependencies=[Depends(require_accounting_module)],
)


# --- Pydantic Schemas ---


class CreateTransactionRequest(BaseModel):
    transaction_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    transaction_type: str = Field(description="revenue, expense, refund, credit_note, payment, transfer")
    entry_kind: str = Field(default="journal_entry")
    category: str = Field(description="sales, cogs, marketing, payroll, software, utilities, tax, other")
    description: str
    amount: float
    subtotal_amount: float | None = None
    currency: str = "CAD"
    status: str = "confirmed"
    is_confirmed: bool = True
    tax_amount: float = 0.0
    reference_id: str | None = None
    source_module: str = "manual"
    external_id: str | None = None
    idempotency_key: str | None = None
    extra_data: dict[str, Any] = Field(default_factory=dict)


class CreateInvoiceRequest(BaseModel):
    invoice_number: str
    invoice_type: str = Field(description="receivable (client) ou payable (fournisseur)")
    document_nature: str = "invoice"
    party_name: str
    issuer_name: str | None = None
    recipient_name: str | None = None
    issue_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    due_date: datetime
    subtotal_amount: float | None = None
    tax_amount: float = 0.0
    tax_breakdown: dict[str, Any] = Field(default_factory=dict)
    total_amount: float
    paid_amount: float = 0.0
    currency: str = "CAD"
    status: str = "unpaid"
    is_confirmed: bool = True
    notes: str | None = None
    line_items: list[dict[str, Any]] = Field(default_factory=list)


class ClassifyDocumentRequest(BaseModel):
    document_id: UUID | None = None
    dataset_id: UUID | None = None
    invoice_number: str | None = None
    document_type: str | None = Field(
        default=None,
        description="Indice optionnel: invoice, supplier_invoice, customer_invoice, receipt, credit_note, avoir, refund, transfer, quote",
    )
    issuer: str | None = None
    issuer_tax_id: str | None = None
    issuer_email: str | None = None
    recipient: str | None = None
    recipient_tax_id: str | None = None
    recipient_email: str | None = None
    party_name: str | None = None
    issue_date: str | datetime | None = None
    due_date: str | datetime | None = None
    subtotal_amount: float | str | None = None
    tax_amount: float | str | None = None
    gst_amount: float | str | None = None
    qst_amount: float | str | None = None
    hst_amount: float | str | None = None
    tax_breakdown: dict[str, Any] = Field(default_factory=dict)
    total_amount: float | str | None = None
    paid_amount: float | str | None = None
    currency: str | None = None
    category: str | None = None
    line_items: list[dict[str, Any]] = Field(default_factory=list)
    extracted_text: str | None = None
    filename: str | None = None
    file_sha256: str | None = None
    external_id: str | None = None
    idempotency_key: str | None = None
    source_module: str | None = None
    page_refs: list[Any] = Field(default_factory=list)
    cell_refs: list[Any] = Field(default_factory=list)
    apply_configured_tax_rules: bool = False
    notes: str | None = None


class ReviewInvoiceProposalRequest(BaseModel):
    action: str = Field(description="approve, correct_and_approve, correct, ou reject")
    reason: str | None = None
    confirm_duplicate: bool = False
    classification: str | None = None
    document_nature: str | None = None
    invoice_type: str | None = None
    direction: str | None = None
    category: str | None = None
    party_name: str | None = None
    subtotal_amount: float | str | None = None
    tax_amount: float | str | None = None
    total_amount: float | str | None = None
    currency: str | None = None
    notes: str | None = None


class RetailSyncRequest(BaseModel):
    confirm_verified_settlements: bool | None = None
    include_demo: bool = False


class UpdateAccountingPolicyRequest(BaseModel):
    auto_confirm_verified_connector_settlements: bool | None = None
    confidence_threshold: float | None = Field(default=None, ge=0.5, le=0.99)
    configured_tax_rules: dict[str, Any] | None = None
    company_aliases: list[str] | None = None


class CreateClassificationRuleRequest(BaseModel):
    counterparty_pattern: str
    forced_classification: str
    default_category: str = "other"
    match_field: str = "counterparty"
    notes: str | None = None


# --- Endpoints ---


@router.get("/overview")
def get_financial_overview(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Vue d'ensemble financière consolidée du tenant (données confirmées vs propositions `to_verify`)."""
    dataset_ids, source_context = resolve_accounting_dataset_scope(db, tenant)
    service = AccountingIntelligenceService(db)
    payload = service.get_financial_overview(tenant.company_id, dataset_ids=dataset_ids)
    payload["source_context"] = source_context
    return payload


@router.get("/overview/unified")
def get_unified_financial_overview(
    identity: CurrentIdentity = Depends(get_current_identity),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Vue financière unifiée (Accounting + Retail + CRM + OCR + HR agrégé sous contrôle RBAC)."""
    dataset_ids, source_context = resolve_accounting_dataset_scope(db, tenant)
    intel = AccountingIntelligenceService(db)
    integration = FinancialIntegrationService(db)
    overview = intel.get_financial_overview(identity.company_id, dataset_ids=dataset_ids)
    unified = integration.get_unified_financial_context(identity.company_id, actor_user=identity.user)
    return {
        **overview,
        "unified_sources": unified,
        "source_context": source_context,
    }


@router.get("/expenses/monthly")
def get_monthly_expenses(
    year: int | None = Query(default=None),
    month: int | None = Query(default=None),
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Dépenses mensuelles ventilées par catégorie et comparaison mois précédent."""
    dataset_ids, source_context = resolve_accounting_dataset_scope(db, tenant)
    can_payroll, _ = can_access_hr_payroll_summary(db, tenant.company_id, identity.user)
    service = AccountingIntelligenceService(db)
    payload = service.get_monthly_expenses(
        tenant.company_id,
        dataset_ids=dataset_ids,
        year=year,
        month=month,
        include_payroll=can_payroll,
    )
    payload["source_context"] = source_context
    return payload


@router.get("/margins")
def get_margins(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Marges brutes et opérationnelles calculées sur les données confirmées."""
    dataset_ids, source_context = resolve_accounting_dataset_scope(db, tenant)
    service = AccountingIntelligenceService(db)
    payload = service.get_profit_margin(tenant.company_id, dataset_ids=dataset_ids)
    payload["source_context"] = source_context
    return payload


@router.get("/invoices/unpaid")
def get_unpaid_invoices(
    invoice_type: str = Query(default="receivable", pattern="^(receivable|payable)$"),
    include_to_verify: bool = Query(default=False),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Factures impayées ou en retard avec montants et ancienneté."""
    dataset_ids, source_context = resolve_accounting_dataset_scope(db, tenant)
    service = AccountingIntelligenceService(db)
    payload = service.get_unpaid_invoices(
        tenant.company_id,
        dataset_ids=dataset_ids,
        invoice_type=invoice_type,
        include_to_verify=include_to_verify,
    )
    payload["source_context"] = source_context
    return payload


@router.get("/anomalies")
def get_expense_anomalies(
    threshold: float = Query(default=2.0, ge=1.0),
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Détection IA d'anomalies de dépenses et alertes de doublons."""
    dataset_ids, source_context = resolve_accounting_dataset_scope(db, tenant)
    can_payroll, _ = can_access_hr_payroll_summary(db, tenant.company_id, identity.user)
    service = AccountingIntelligenceService(db)
    payload = service.get_expense_anomalies(
        tenant.company_id,
        dataset_ids=dataset_ids,
        threshold_multiplier=threshold,
        include_payroll=can_payroll,
    )
    payload["source_context"] = source_context
    return payload


@router.get("/forecast/cashflow")
def get_cash_flow_forecast(
    horizon_days: int = Query(default=30, ge=7, le=180),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Prévision prédictive de trésorerie (Cash Flow Forecast) IA."""
    dataset_ids, source_context = resolve_accounting_dataset_scope(db, tenant)
    service = AccountingIntelligenceService(db)
    payload = service.get_cash_flow_forecast(
        tenant.company_id, dataset_ids=dataset_ids, horizon_days=horizon_days
    )
    payload["source_context"] = source_context
    return payload


@router.get("/reconciliation")
def get_reconciliation(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Réconciliation inter-modules entre commandes e-commerce, paiements, factures et remboursements."""
    return FinancialIntegrationService(db).reconcile_ecommerce_and_accounting(tenant.company_id)


@router.get("/payroll-summary")
def get_payroll_summary(
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Masse salariale agrégée RH (strictement réservée aux rôles exécutifs/direction avec module HR actif)."""
    try:
        return FinancialIntegrationService(db).get_hr_payroll_summary(
            identity.company_id,
            actor_user=identity.user,
            strict_raise=True,
        )
    except HRPayrollAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get("/transactions")
def list_transactions(
    transaction_type: str | None = Query(default=None),
    entry_kind: str | None = Query(default=None),
    category: str | None = Query(default=None),
    verification_status: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Liste des écritures et transactions financières du tenant (avec protection RBAC des salaires RH)."""
    can_payroll, payroll_reason = can_access_hr_payroll_summary(db, tenant.company_id, identity.user)
    if category and category.strip().lower() in PAYROLL_CATEGORIES and not can_payroll:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Accès refusé aux coûts salariaux RH ({payroll_reason}). "
                "Nécessite le module HR AI actif et un rôle exécutif/direction autorisé."
            ),
        )
    dataset_ids, _source_context = resolve_accounting_dataset_scope(db, tenant)
    stmt = select(AccountingTransaction).where(
        AccountingTransaction.company_id == tenant.company_id,
        apply_dataset_scope(AccountingTransaction, dataset_ids),
    )
    if transaction_type:
        stmt = stmt.where(AccountingTransaction.transaction_type == transaction_type)
    if entry_kind:
        stmt = stmt.where(AccountingTransaction.entry_kind == entry_kind)
    if category:
        stmt = stmt.where(AccountingTransaction.category == category)
    if verification_status:
        stmt = stmt.where(AccountingTransaction.verification_status == verification_status)
    stmt = stmt.order_by(desc(AccountingTransaction.transaction_date)).limit(limit)

    txs = list(db.scalars(stmt).all())
    if not can_payroll:
        txs = [t for t in txs if (t.category or "").strip().lower() not in PAYROLL_CATEGORIES]
    return [
        {
            "id": str(t.id),
            "date": t.transaction_date.isoformat(),
            "transaction_date": t.transaction_date.isoformat(),
            "transaction_type": t.transaction_type,
            "entry_kind": t.entry_kind,
            "category": t.category,
            "description": t.description,
            "amount": t.amount,
            "subtotal_amount": t.subtotal_amount,
            "currency": t.currency,
            "status": t.status,
            "is_confirmed": t.is_confirmed,
            "verification_status": t.verification_status,
            "accounting_status": t.accounting_status,
            "tax_amount": t.tax_amount,
            "reference_id": t.reference_id,
            "source_module": t.source_module,
            "external_id": t.external_id,
            "dataset_id": str(t.dataset_id) if t.dataset_id else None,
            "invoice_id": str(t.invoice_id) if t.invoice_id else None,
            "extra_data": t.extra_data,
        }
        for t in txs
    ]


@router.post("/transactions", status_code=status.HTTP_201_CREATED)
def create_transaction(
    payload: CreateTransactionRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Crée une nouvelle écriture comptable pour le tenant."""
    tx = AccountingTransaction(
        company_id=tenant.company_id,
        transaction_date=payload.transaction_date,
        transaction_type=payload.transaction_type,
        entry_kind=payload.entry_kind,
        category=payload.category,
        description=payload.description,
        amount=payload.amount,
        subtotal_amount=payload.subtotal_amount,
        currency=payload.currency,
        status=payload.status,
        is_confirmed=payload.is_confirmed,
        verification_status="confirmed" if payload.is_confirmed else "to_verify",
        accounting_status="posted" if payload.is_confirmed else "proposed",
        tax_amount=payload.tax_amount,
        reference_id=payload.reference_id,
        source_module=payload.source_module,
        external_id=payload.external_id,
        idempotency_key=payload.idempotency_key,
        extra_data=payload.extra_data,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    tenant_cache.invalidate_tenant(tenant.company_id)
    return {
        "id": str(tx.id),
        "description": tx.description,
        "amount": tx.amount,
        "type": tx.transaction_type,
        "entry_kind": tx.entry_kind,
        "is_confirmed": tx.is_confirmed,
    }


@router.get("/invoices")
def list_invoices(
    document_scope: bool = Query(default=False),
    invoice_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    verification_status: str | None = Query(default=None),
    document_nature: str | None = Query(default=None),
    source_module: str | None = Query(default=None),
    duplicate_warning: bool | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Liste des factures et propositions documentaires du tenant."""
    dataset_ids, _source_context = resolve_accounting_dataset_scope(db, tenant)
    stmt = select(AccountingInvoice).where(
        AccountingInvoice.company_id == tenant.company_id,
        (
            (AccountingInvoice.source_module == "ocr") & AccountingInvoice.document_id.is_not(None)
            if document_scope
            else apply_dataset_scope(AccountingInvoice, dataset_ids)
        ),
    )
    if invoice_type:
        stmt = stmt.where(AccountingInvoice.invoice_type == invoice_type)
    if status_filter:
        stmt = stmt.where(AccountingInvoice.status == status_filter)
    if verification_status:
        stmt = stmt.where(AccountingInvoice.verification_status == verification_status)
    if document_nature:
        stmt = stmt.where(AccountingInvoice.document_nature == document_nature)
    if source_module:
        stmt = stmt.where(AccountingInvoice.source_module == source_module)
    if duplicate_warning is not None:
        stmt = stmt.where(AccountingInvoice.duplicate_warning.is_(duplicate_warning))
    stmt = stmt.order_by(desc(AccountingInvoice.due_date)).limit(limit)

    invs = list(db.scalars(stmt).all())
    return [
        {
            "id": str(i.id),
            "invoice_number": i.invoice_number,
            "invoice_type": i.invoice_type,
            "document_nature": i.document_nature,
            "direction": i.direction,
            "company_role": i.company_role,
            "party_name": i.party_name,
            "issue_date": i.issue_date.isoformat(),
            "due_date": i.due_date.isoformat(),
            "subtotal_amount": i.subtotal_amount,
            "tax_amount": i.tax_amount,
            "total_amount": i.total_amount,
            "paid_amount": i.paid_amount,
            "remaining_amount": i.remaining_amount,
            "currency": i.currency,
            "status": i.status,
            "is_confirmed": i.is_confirmed,
            "verification_status": i.verification_status,
            "accounting_status": i.accounting_status,
            "confidence_score": i.confidence_score,
            "classification_rationale": i.classification_rationale,
            "source_module": i.source_module,
            "document_id": str(i.document_id) if i.document_id else None,
            "duplicate_warning": i.duplicate_warning,
            "notes": i.notes,
        }
        for i in invs
    ]


@router.get("/invoices/{invoice_id}")
def get_invoice_detail(
    invoice_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Détail complet d'une facture (provenance documentaire, lignes, taxes, écritures liées, historique d'audit)."""
    detail = AccountingIntelligenceService(db).get_invoice_detail_enriched(
        tenant.company_id,
        invoice_id=invoice_id,
    )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Facture introuvable pour cette entreprise.",
        )
    return detail


@router.post("/invoices", status_code=status.HTTP_201_CREATED)
def create_invoice(
    payload: CreateInvoiceRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Crée une nouvelle facture pour le tenant."""
    inv = AccountingInvoice(
        company_id=tenant.company_id,
        invoice_number=payload.invoice_number,
        invoice_type=payload.invoice_type,
        document_nature=payload.document_nature,
        party_name=payload.party_name,
        issuer_name=payload.issuer_name,
        recipient_name=payload.recipient_name,
        issue_date=payload.issue_date,
        due_date=payload.due_date,
        subtotal_amount=payload.subtotal_amount,
        tax_amount=payload.tax_amount,
        tax_breakdown=payload.tax_breakdown,
        total_amount=payload.total_amount,
        paid_amount=payload.paid_amount,
        currency=payload.currency,
        status=payload.status,
        is_confirmed=payload.is_confirmed,
        verification_status="confirmed" if payload.is_confirmed else "to_verify",
        accounting_status="posted" if payload.is_confirmed else "proposed",
        line_items=payload.line_items,
        notes=payload.notes,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    tenant_cache.invalidate_tenant(tenant.company_id)
    return {
        "id": str(inv.id),
        "invoice_number": inv.invoice_number,
        "total_amount": inv.total_amount,
        "remaining_amount": inv.remaining_amount,
        "status": inv.status,
    }


@router.post("/documents/classify", status_code=status.HTTP_201_CREATED)
def classify_and_propose_document(
    payload: ClassifyDocumentRequest,
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Classe automatiquement un document financier selon le rôle vérifié de l'entreprise et crée une proposition `to_verify`."""
    service = AccountingClassificationService(db)
    try:
        _, summary = service.import_document_proposal(
            identity.company_id,
            payload.model_dump(exclude_none=True),
            actor_user_id=identity.user_id,
            document_id=payload.document_id,
            dataset_id=payload.dataset_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AccountingClassificationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    tenant_cache.invalidate_tenant(identity.company_id)
    return summary


@router.post("/invoices/{invoice_id}/review")
def review_invoice_proposal(
    invoice_id: UUID,
    payload: ReviewInvoiceProposalRequest,
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Corrige manuellement la classification, approuve ou rejette une proposition avec audit complet."""
    service = AccountingClassificationService(db)
    overrides = payload.model_dump(
        exclude={"action", "reason", "confirm_duplicate"},
        exclude_none=True,
    )
    try:
        result = service.review_invoice_proposal(
            identity.company_id,
            invoice_id,
            actor_user_id=identity.user_id,
            action=payload.action,
            reason=payload.reason,
            overrides=overrides,
            confirm_duplicate=payload.confirm_duplicate,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DuplicateConfirmationRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except AccountingClassificationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    tenant_cache.invalidate_tenant(identity.company_id)
    return result


@router.post("/integrations/retail/sync")
def sync_retail_commerce(
    payload: RetailSyncRequest,
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Synchronisation idempotente Retail AI -> Accounting AI (commandes, paiements, taxes, COGS, frais, remboursements)."""
    result = FinancialIntegrationService(db).sync_retail_commerce_to_accounting(
        identity.company_id,
        actor_user_id=identity.user_id,
        confirm_verified_settlements=payload.confirm_verified_settlements,
        include_demo=payload.include_demo,
    )
    tenant_cache.invalidate_tenant(identity.company_id)
    return result


@router.post("/integrations/crm/sync")
def sync_crm_billables(
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Synchronisation idempotente des rendez-vous facturables complétés CRM -> propositions `to_verify`."""
    result = FinancialIntegrationService(db).sync_crm_billables_to_accounting(
        identity.company_id,
        actor_user=identity.user,
    )
    tenant_cache.invalidate_tenant(identity.company_id)
    return result


@router.get("/policy")
def get_accounting_policy(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Retourne la politique de gouvernance comptable du tenant."""
    policy = AccountingClassificationService(db).get_or_create_policy(tenant.company_id)
    db.commit()
    return {
        "company_id": str(policy.company_id),
        "auto_confirm_verified_connector_settlements": policy.auto_confirm_verified_connector_settlements,
        "confidence_threshold": policy.confidence_threshold,
        "configured_tax_rules": policy.configured_tax_rules or {},
        "company_aliases": policy.company_aliases or [],
    }


@router.put("/policy")
def update_accounting_policy(
    payload: UpdateAccountingPolicyRequest,
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Met à jour la politique de gouvernance comptable du tenant."""
    policy = AccountingClassificationService(db).update_policy(
        identity.company_id,
        actor_user_id=identity.user_id,
        auto_confirm_verified_connector_settlements=payload.auto_confirm_verified_connector_settlements,
        confidence_threshold=payload.confidence_threshold,
        configured_tax_rules=payload.configured_tax_rules,
        company_aliases=payload.company_aliases,
    )
    return {
        "company_id": str(policy.company_id),
        "auto_confirm_verified_connector_settlements": policy.auto_confirm_verified_connector_settlements,
        "confidence_threshold": policy.confidence_threshold,
        "configured_tax_rules": policy.configured_tax_rules or {},
        "company_aliases": policy.company_aliases or [],
    }


@router.post("/classification-rules", status_code=status.HTTP_201_CREATED)
def create_classification_rule(
    payload: CreateClassificationRuleRequest,
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Crée une règle déterministe de classification comptable propre au tenant."""
    try:
        rule = AccountingClassificationService(db).add_classification_rule(
            identity.company_id,
            counterparty_pattern=payload.counterparty_pattern,
            forced_classification=payload.forced_classification,
            default_category=payload.default_category,
            match_field=payload.match_field,
            notes=payload.notes,
            actor_user_id=identity.user_id,
        )
    except AccountingClassificationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {
        "id": str(rule.id),
        "counterparty_pattern": rule.counterparty_pattern,
        "forced_classification": rule.forced_classification,
        "default_category": rule.default_category,
        "match_field": rule.match_field,
    }

"""Routes API pour le module Accounting AI (Phase 14).

Fournit les écritures comptables confirmées, les métriques financières consolidées,
la détection d'anomalies et les prévisions de cash flow avec isolation multi-tenant stricte.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.app.core.cache import tenant_cache
from backend.app.database import get_db
from backend.app.dependencies.auth import get_tenant_context
from backend.app.models.accounting import AccountingInvoice, AccountingTransaction
from backend.app.services.accounting_intelligence_service import AccountingIntelligenceService
from shared.ai_engine.contracts import TenantContext

router = APIRouter(prefix="/accounting", tags=["accounting"])


# --- Pydantic Schemas ---

class CreateTransactionRequest(BaseModel):
    transaction_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    transaction_type: str = Field(description="revenue ou expense")
    category: str = Field(description="sales, cogs, marketing, payroll, software, utilities, tax, other")
    description: str
    amount: float
    currency: str = "CAD"
    status: str = "confirmed"
    is_confirmed: bool = True
    tax_amount: float = 0.0
    reference_id: str | None = None
    extra_data: dict[str, Any] = Field(default_factory=dict)


class CreateInvoiceRequest(BaseModel):
    invoice_number: str
    invoice_type: str = Field(description="receivable (client) ou payable (fournisseur)")
    party_name: str
    issue_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    due_date: datetime
    total_amount: float
    paid_amount: float = 0.0
    currency: str = "CAD"
    status: str = "unpaid"
    is_confirmed: bool = True
    notes: str | None = None


# --- Endpoints ---

@router.get("/overview")
def get_financial_overview(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Vue d'ensemble financière consolidée du tenant (données réelles confirmées)."""
    service = AccountingIntelligenceService(db)
    return service.get_financial_overview(tenant.company_id)


@router.get("/expenses/monthly")
def get_monthly_expenses(
    year: int | None = Query(default=None),
    month: int | None = Query(default=None),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Dépenses mensuelles ventilées par catégorie et comparaison mois précédent."""
    service = AccountingIntelligenceService(db)
    return service.get_monthly_expenses(tenant.company_id, year=year, month=month)


@router.get("/margins")
def get_margins(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Marges brutes et opérationnelles calculées sur les données confirmées."""
    service = AccountingIntelligenceService(db)
    return service.get_profit_margin(tenant.company_id)


@router.get("/invoices/unpaid")
def get_unpaid_invoices(
    invoice_type: str = Query(default="receivable", pattern="^(receivable|payable)$"),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Factures impayées ou en retard avec montants et ancienneté."""
    service = AccountingIntelligenceService(db)
    return service.get_unpaid_invoices(tenant.company_id, invoice_type=invoice_type)


@router.get("/anomalies")
def get_expense_anomalies(
    threshold: float = Query(default=2.0, ge=1.0),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Détection IA d'anomalies et dépenses suspectes."""
    service = AccountingIntelligenceService(db)
    return service.get_expense_anomalies(tenant.company_id, threshold_multiplier=threshold)


@router.get("/forecast/cashflow")
def get_cash_flow_forecast(
    horizon_days: int = Query(default=30, ge=7, le=180),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Prévision prédictive de trésorerie (Cash Flow Forecast) IA."""
    service = AccountingIntelligenceService(db)
    return service.get_cash_flow_forecast(tenant.company_id, horizon_days=horizon_days)


@router.get("/transactions")
def list_transactions(
    transaction_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Liste des écritures et transactions financières du tenant."""
    stmt = select(AccountingTransaction).where(
        AccountingTransaction.company_id == tenant.company_id
    )
    if transaction_type:
        stmt = stmt.where(AccountingTransaction.transaction_type == transaction_type)
    if category:
        stmt = stmt.where(AccountingTransaction.category == category)
    stmt = stmt.order_by(desc(AccountingTransaction.transaction_date)).limit(limit)

    txs = list(db.scalars(stmt).all())
    return [
        {
            "id": str(t.id),
            "date": t.transaction_date.isoformat(),
            "transaction_type": t.transaction_type,
            "category": t.category,
            "description": t.description,
            "amount": t.amount,
            "currency": t.currency,
            "status": t.status,
            "is_confirmed": t.is_confirmed,
            "tax_amount": t.tax_amount,
            "reference_id": t.reference_id,
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
        category=payload.category,
        description=payload.description,
        amount=payload.amount,
        currency=payload.currency,
        status=payload.status,
        is_confirmed=payload.is_confirmed,
        tax_amount=payload.tax_amount,
        reference_id=payload.reference_id,
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
        "is_confirmed": tx.is_confirmed,
    }


@router.get("/invoices")
def list_invoices(
    invoice_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, le=200),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Liste des factures du tenant."""
    stmt = select(AccountingInvoice).where(
        AccountingInvoice.company_id == tenant.company_id
    )
    if invoice_type:
        stmt = stmt.where(AccountingInvoice.invoice_type == invoice_type)
    if status_filter:
        stmt = stmt.where(AccountingInvoice.status == status_filter)
    stmt = stmt.order_by(desc(AccountingInvoice.due_date)).limit(limit)

    invs = list(db.scalars(stmt).all())
    return [
        {
            "id": str(i.id),
            "invoice_number": i.invoice_number,
            "invoice_type": i.invoice_type,
            "party_name": i.party_name,
            "issue_date": i.issue_date.isoformat(),
            "due_date": i.due_date.isoformat(),
            "total_amount": i.total_amount,
            "paid_amount": i.paid_amount,
            "remaining_amount": i.remaining_amount,
            "currency": i.currency,
            "status": i.status,
            "is_confirmed": i.is_confirmed,
            "notes": i.notes,
        }
        for i in invs
    ]


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
        party_name=payload.party_name,
        issue_date=payload.issue_date,
        due_date=payload.due_date,
        total_amount=payload.total_amount,
        paid_amount=payload.paid_amount,
        currency=payload.currency,
        status=payload.status,
        is_confirmed=payload.is_confirmed,
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

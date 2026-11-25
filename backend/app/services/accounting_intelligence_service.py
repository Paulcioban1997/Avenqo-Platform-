"""Service d'intelligence analytique Accounting AI native (Phase 14 & Phases D/E Unification).

Fournit les métriques financières confirmées, la séparation stricte entre écritures postées
et propositions IA (`to_verify`), la distinction AR vs AP, le suivi des taxes documentées,
le détail enrichi des factures avec provenance documentaire, la détection d'anomalies/doublons
et les prévisions de trésorerie (cash flow) avec isolation multi-tenant stricte.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from backend.app.core.cache import cached_for_tenant
from backend.app.models.accounting import AccountingInvoice, AccountingTransaction
from backend.app.models.audit_log import AuditLogEntry
from backend.app.models.dataset import Dataset
from backend.app.models.workspace import TenantDocument
from backend.app.services.financial_integration_service import FinancialIntegrationService


def _is_revenue_reversal(tx: AccountingTransaction) -> bool:
    if tx.transaction_type not in {"refund", "credit_note"}:
        return False
    direction = (tx.extra_data or {}).get("direction")
    if direction == "expense_reversal" or tx.category in {"expense_credits", "expense_refunds"}:
        return False
    return True


def _is_expense_reversal(tx: AccountingTransaction) -> bool:
    if tx.transaction_type not in {"refund", "credit_note"}:
        return False
    direction = (tx.extra_data or {}).get("direction")
    return direction == "expense_reversal" or tx.category in {"expense_credits", "expense_refunds"}


def _ensure_aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


class AccountingIntelligenceService:
    """Service d'intelligence comptable et financière avec isolation multi-tenant stricte."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @cached_for_tenant("accounting_overview", ttl_seconds=30)
    def get_financial_overview(self, company_id: UUID) -> dict[str, Any]:
        """Vue d'ensemble financière consolidée du tenant (données réelles confirmées vs propositions en attente)."""
        all_txs = list(
            self._session.scalars(
                select(AccountingTransaction).where(AccountingTransaction.company_id == company_id)
            ).all()
        )
        txs = [t for t in all_txs if t.is_confirmed]
        proposed_txs = [t for t in all_txs if not t.is_confirmed and t.status != "rejected"]

        invoices = list(
            self._session.scalars(
                select(AccountingInvoice).where(AccountingInvoice.company_id == company_id)
            ).all()
        )
        confirmed_invoices = [inv for inv in invoices if inv.is_confirmed]
        pending_invoices = [
            inv for inv in invoices
            if not inv.is_confirmed and inv.verification_status == "to_verify" and inv.status != "rejected"
        ]

        gross_revenue = sum(t.amount for t in txs if t.transaction_type == "revenue")
        revenue_reversals = sum(t.amount for t in txs if _is_revenue_reversal(t))
        total_revenue = round(gross_revenue - revenue_reversals, 2)

        gross_expenses = sum(t.amount for t in txs if t.transaction_type == "expense")
        expense_reversals = sum(t.amount for t in txs if _is_expense_reversal(t))
        total_expenses = round(max(0.0, gross_expenses - expense_reversals), 2)

        cogs = sum(
            t.amount
            for t in txs
            if t.transaction_type == "expense"
            and t.category.lower() in {"cogs", "cost of goods", "cout des marchandises"}
        )
        processing_fees = sum(
            t.amount
            for t in txs
            if t.transaction_type == "expense" and t.category.lower() == "processing_fees"
        )
        payments_collected = sum(t.amount for t in txs if t.entry_kind == "payment_collected")

        collected_sales_tax = sum(t.tax_amount for t in txs if t.transaction_type == "revenue") - sum(
            t.tax_amount for t in txs if _is_revenue_reversal(t)
        )
        input_tax_credits = sum(t.tax_amount for t in txs if t.transaction_type == "expense") - sum(
            t.tax_amount for t in txs if _is_expense_reversal(t)
        )

        net_income = total_revenue - total_expenses
        gross_profit = total_revenue - cogs
        gross_margin_pct = round((gross_profit / total_revenue * 100), 2) if total_revenue > 0 else 0.0
        operating_margin_pct = round((net_income / total_revenue * 100), 2) if total_revenue > 0 else 0.0

        unpaid_receivables = [
            inv
            for inv in confirmed_invoices
            if inv.invoice_type == "receivable" and inv.status in {"unpaid", "overdue", "partial"}
        ]
        unpaid_payables = [
            inv
            for inv in confirmed_invoices
            if inv.invoice_type == "payable" and inv.status in {"unpaid", "overdue", "partial"}
        ]

        total_receivables_due = sum(inv.remaining_amount for inv in unpaid_receivables)
        total_payables_due = sum(inv.remaining_amount for inv in unpaid_payables)

        proposed_receivables = sum(
            inv.total_amount for inv in pending_invoices if inv.invoice_type == "receivable"
        )
        proposed_payables = sum(
            inv.total_amount for inv in pending_invoices if inv.invoice_type == "payable"
        )
        duplicate_warnings_count = sum(
            1 for inv in invoices if inv.duplicate_warning and inv.status != "rejected"
        )

        return {
            "data_type": "confirmed_actuals",
            "is_projection": False,
            "currency": txs[0].currency if txs else (invoices[0].currency if invoices else "CAD"),
            "gross_revenue": round(gross_revenue, 2),
            "refunds_and_credit_notes_total": round(revenue_reversals, 2),
            "total_revenue": round(total_revenue, 2),
            "total_expenses": round(total_expenses, 2),
            "cogs": round(cogs, 2),
            "processing_fees": round(processing_fees, 2),
            "net_income": round(net_income, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_margin_pct": gross_margin_pct,
            "operating_margin_pct": operating_margin_pct,
            "transactions_count": len([t for t in txs if t.entry_kind != "order"]),
            "payments_collected_total": round(payments_collected, 2),
            "taxes_summary": {
                "collected_sales_tax": round(collected_sales_tax, 2),
                "input_tax_credits": round(input_tax_credits, 2),
                "net_tax_remittance": round(collected_sales_tax - input_tax_credits, 2),
            },
            "receivables": {
                "unpaid_count": len(unpaid_receivables),
                "total_due": round(total_receivables_due, 2),
            },
            "payables": {
                "unpaid_count": len(unpaid_payables),
                "total_due": round(total_payables_due, 2),
            },
            "pending_verification": {
                "to_verify_invoices_count": len(pending_invoices),
                "proposed_receivables_total": round(proposed_receivables, 2),
                "proposed_payables_total": round(proposed_payables, 2),
                "proposed_transactions_count": len(proposed_txs),
                "duplicate_warnings_count": duplicate_warnings_count,
            },
        }

    @cached_for_tenant("accounting_expenses", ttl_seconds=30)
    def get_monthly_expenses(
        self,
        company_id: UUID,
        year: int | None = None,
        month: int | None = None,
    ) -> dict[str, Any]:
        """Dépenses ventilées par catégorie pour un mois donné (par défaut le mois en cours)."""
        now = datetime.now(timezone.utc)
        target_year = year or now.year
        target_month = month or now.month

        start_date = datetime(target_year, target_month, 1, tzinfo=timezone.utc)
        if target_month == 12:
            end_date = datetime(target_year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end_date = datetime(target_year, target_month + 1, 1, tzinfo=timezone.utc)

        if target_month == 1:
            prev_start = datetime(target_year - 1, 12, 1, tzinfo=timezone.utc)
            prev_end = start_date
        else:
            prev_start = datetime(target_year, target_month - 1, 1, tzinfo=timezone.utc)
            prev_end = start_date

        current_txs = list(
            self._session.scalars(
                select(AccountingTransaction)
                .where(
                    AccountingTransaction.company_id == company_id,
                    AccountingTransaction.transaction_type == "expense",
                    AccountingTransaction.is_confirmed.is_(True),
                    AccountingTransaction.transaction_date >= start_date,
                    AccountingTransaction.transaction_date < end_date,
                )
                .order_by(desc(AccountingTransaction.transaction_date))
            ).all()
        )

        prev_txs = list(
            self._session.scalars(
                select(AccountingTransaction).where(
                    AccountingTransaction.company_id == company_id,
                    AccountingTransaction.transaction_type == "expense",
                    AccountingTransaction.is_confirmed.is_(True),
                    AccountingTransaction.transaction_date >= prev_start,
                    AccountingTransaction.transaction_date < prev_end,
                )
            ).all()
        )

        pending_expense_proposals = list(
            self._session.scalars(
                select(AccountingInvoice).where(
                    AccountingInvoice.company_id == company_id,
                    AccountingInvoice.invoice_type == "payable",
                    AccountingInvoice.verification_status == "to_verify",
                    AccountingInvoice.status != "rejected",
                )
            ).all()
        )

        categories: dict[str, float] = defaultdict(float)
        for t in current_txs:
            categories[t.category] += t.amount

        total_current = sum(t.amount for t in current_txs)
        total_prev = sum(t.amount for t in prev_txs)
        diff = total_current - total_prev
        diff_pct = round((diff / total_prev * 100), 2) if total_prev > 0 else 0.0

        sorted_categories = sorted(
            [
                {
                    "category": cat,
                    "amount": round(amt, 2),
                    "percentage": round(amt / total_current * 100, 1) if total_current > 0 else 0.0,
                }
                for cat, amt in categories.items()
            ],
            key=lambda x: x["amount"],
            reverse=True,
        )

        return {
            "data_type": "confirmed_actuals",
            "is_projection": False,
            "period": f"{target_year}-{target_month:02d}",
            "total_expenses": round(total_current, 2),
            "expenses_count": len(current_txs),
            "categories_breakdown": sorted_categories,
            "previous_month_total": round(total_prev, 2),
            "difference": round(diff, 2),
            "change_pct": diff_pct,
            "currency": current_txs[0].currency if current_txs else "CAD",
            "pending_payable_proposals_count": len(pending_expense_proposals),
            "pending_payable_proposals_total": round(sum(p.total_amount for p in pending_expense_proposals), 2),
            "recent_expenses": [
                {
                    "id": str(t.id),
                    "date": t.transaction_date.isoformat(),
                    "category": t.category,
                    "description": t.description,
                    "amount": round(t.amount, 2),
                    "status": t.status,
                    "source_module": t.source_module,
                }
                for t in current_txs[:10]
            ],
        }

    @cached_for_tenant("accounting_margins", ttl_seconds=30)
    def get_profit_margin(self, company_id: UUID) -> dict[str, Any]:
        """Calcul de marge brute et opérationnelle sur les écritures comptables confirmées."""
        txs = list(
            self._session.scalars(
                select(AccountingTransaction).where(
                    AccountingTransaction.company_id == company_id,
                    AccountingTransaction.is_confirmed.is_(True),
                )
            ).all()
        )

        gross_revenue = sum(t.amount for t in txs if t.transaction_type == "revenue")
        refunds = sum(t.amount for t in txs if _is_revenue_reversal(t))
        revenue = max(0.0, gross_revenue - refunds)
        cogs = sum(
            t.amount
            for t in txs
            if t.transaction_type == "expense"
            and t.category.lower() in {"cogs", "cost of goods", "cout des marchandises", "inventory"}
        )
        operating_expenses = sum(
            t.amount
            for t in txs
            if t.transaction_type == "expense"
            and t.category.lower() not in {"cogs", "cost of goods", "cout des marchandises", "inventory"}
        )
        expense_credits = sum(t.amount for t in txs if _is_expense_reversal(t))
        operating_expenses = max(0.0, operating_expenses - expense_credits)
        total_expenses = cogs + operating_expenses

        gross_profit = revenue - cogs
        gross_margin_pct = round((gross_profit / revenue * 100), 2) if revenue > 0 else 0.0
        operating_profit = revenue - total_expenses
        operating_margin_pct = round((operating_profit / revenue * 100), 2) if revenue > 0 else 0.0

        return {
            "data_type": "confirmed_actuals",
            "is_projection": False,
            "gross_revenue": round(gross_revenue, 2),
            "refunds_deducted": round(refunds, 2),
            "total_revenue": round(revenue, 2),
            "cogs": round(cogs, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_margin_pct": gross_margin_pct,
            "operating_expenses": round(operating_expenses, 2),
            "operating_profit": round(operating_profit, 2),
            "operating_margin_pct": operating_margin_pct,
            "currency": txs[0].currency if txs else "CAD",
        }

    @cached_for_tenant("accounting_unpaid_invoices", ttl_seconds=30)
    def get_unpaid_invoices(
        self,
        company_id: UUID,
        invoice_type: str = "receivable",
        *,
        include_to_verify: bool = False,
    ) -> dict[str, Any]:
        """Liste des factures impayées ou en retard avec montants restants et ancienneté."""
        now = datetime.now(timezone.utc)
        allowed_statuses = ["unpaid", "overdue", "partial"]
        if include_to_verify:
            allowed_statuses.append("to_verify")

        stmt = select(AccountingInvoice).where(
            AccountingInvoice.company_id == company_id,
            AccountingInvoice.invoice_type == invoice_type,
            AccountingInvoice.status.in_(allowed_statuses),
        )
        if not include_to_verify:
            stmt = stmt.where(AccountingInvoice.is_confirmed.is_(True))

        invoices = list(self._session.scalars(stmt.order_by(AccountingInvoice.due_date.asc())).all())

        unpaid_list: list[dict[str, Any]] = []
        total_unpaid = 0.0
        total_overdue = 0.0

        for inv in invoices:
            rem = inv.remaining_amount
            total_unpaid += rem
            due_aware = _ensure_aware(inv.due_date)
            days_overdue = (now - due_aware).days if now > due_aware else 0
            is_overdue = days_overdue > 0 and inv.is_confirmed
            if is_overdue:
                total_overdue += rem

            unpaid_list.append({
                "id": str(inv.id),
                "invoice_number": inv.invoice_number,
                "party_name": inv.party_name,
                "issue_date": inv.issue_date.isoformat(),
                "due_date": inv.due_date.isoformat(),
                "total_amount": round(inv.total_amount, 2),
                "paid_amount": round(inv.paid_amount, 2),
                "remaining_amount": round(rem, 2),
                "status": "overdue" if is_overdue else inv.status,
                "verification_status": inv.verification_status,
                "is_confirmed": inv.is_confirmed,
                "is_overdue": is_overdue,
                "days_overdue": max(0, days_overdue) if inv.is_confirmed else 0,
                "currency": inv.currency,
            })

        return {
            "data_type": "confirmed_actuals" if not include_to_verify else "actuals_and_proposals",
            "invoice_type": invoice_type,
            "count": len(unpaid_list),
            "total_unpaid_amount": round(total_unpaid, 2),
            "total_overdue_amount": round(total_overdue, 2),
            "invoices": unpaid_list,
        }

    @cached_for_tenant("accounting_anomalies", ttl_seconds=30)
    def get_expense_anomalies(
        self,
        company_id: UUID,
        threshold_multiplier: float = 2.0,
    ) -> dict[str, Any]:
        """Détecte les dépenses inhabituelles ainsi que les doublons et écarts arithmétiques de factures."""
        txs = list(
            self._session.scalars(
                select(AccountingTransaction)
                .where(
                    AccountingTransaction.company_id == company_id,
                    AccountingTransaction.transaction_type == "expense",
                    AccountingTransaction.is_confirmed.is_(True),
                )
                .order_by(AccountingTransaction.transaction_date.desc())
            ).all()
        )

        duplicate_invoices = list(
            self._session.scalars(
                select(AccountingInvoice).where(
                    AccountingInvoice.company_id == company_id,
                    AccountingInvoice.duplicate_warning.is_(True),
                    AccountingInvoice.status != "rejected",
                )
            ).all()
        )
        duplicate_alerts = [
            {
                "invoice_id": str(inv.id),
                "invoice_number": inv.invoice_number,
                "party_name": inv.party_name,
                "total_amount": round(inv.total_amount, 2),
                "verification_status": inv.verification_status,
                "duplicate_candidates_count": len(inv.duplicate_candidates or []),
            }
            for inv in duplicate_invoices
        ]

        if not txs:
            return {
                "data_type": "ai_insights",
                "anomalies_count": 0,
                "anomalies": [],
                "duplicate_invoice_alerts_count": len(duplicate_alerts),
                "duplicate_invoice_alerts": duplicate_alerts,
                "summary": "Aucune transaction de dépense enregistrée pour ce tenant.",
            }

        cat_amounts: dict[str, list[float]] = defaultdict(list)
        for t in txs:
            cat_amounts[t.category].append(t.amount)

        cat_averages: dict[str, float] = {
            cat: (sum(amounts) / len(amounts)) for cat, amounts in cat_amounts.items()
        }

        anomalies: list[dict[str, Any]] = []
        for t in txs:
            avg = cat_averages[t.category]
            is_anomaly = (
                len(cat_amounts[t.category]) >= 2
                and t.amount > (avg * threshold_multiplier)
                and t.amount > 100.0
            ) or (t.extra_data or {}).get("is_anomaly") is True
            if is_anomaly:
                pct_above = round(((t.amount - avg) / avg * 100), 1) if avg > 0 else 100.0
                anomalies.append({
                    "id": str(t.id),
                    "date": t.transaction_date.isoformat(),
                    "category": t.category,
                    "description": t.description,
                    "amount": round(t.amount, 2),
                    "category_average": round(avg, 2),
                    "percentage_above_average": pct_above,
                    "reason": (
                        f"Dépense supérieure de {pct_above}% à la moyenne de la catégorie "
                        f"'{t.category}' ({round(avg, 2)} {t.currency})."
                    ),
                })

        return {
            "data_type": "ai_insights",
            "threshold_multiplier": threshold_multiplier,
            "anomalies_count": len(anomalies),
            "anomalies": anomalies,
            "duplicate_invoice_alerts_count": len(duplicate_alerts),
            "duplicate_invoice_alerts": duplicate_alerts,
        }

    @cached_for_tenant("accounting_cashflow", ttl_seconds=30)
    def get_cash_flow_forecast(
        self,
        company_id: UUID,
        horizon_days: int = 30,
    ) -> dict[str, Any]:
        """Prévision de trésorerie (Cash Flow Forecast) strictement identifiée comme projection IA."""
        now = datetime.now(timezone.utc)
        horizon_date = now + timedelta(days=horizon_days)

        txs = list(
            self._session.scalars(
                select(AccountingTransaction).where(
                    AccountingTransaction.company_id == company_id,
                    AccountingTransaction.is_confirmed.is_(True),
                )
            ).all()
        )
        current_balance = 0.0
        for t in txs:
            if t.transaction_type == "revenue":
                current_balance += t.amount
            elif t.transaction_type == "expense":
                current_balance -= t.amount
            elif _is_revenue_reversal(t):
                current_balance -= t.amount
            elif _is_expense_reversal(t):
                current_balance += t.amount

        incoming_invoices = list(
            self._session.scalars(
                select(AccountingInvoice).where(
                    AccountingInvoice.company_id == company_id,
                    AccountingInvoice.invoice_type == "receivable",
                    AccountingInvoice.is_confirmed.is_(True),
                    AccountingInvoice.status.in_(["unpaid", "overdue", "partial"]),
                    AccountingInvoice.due_date <= horizon_date,
                )
            ).all()
        )
        expected_incoming = sum(inv.remaining_amount for inv in incoming_invoices)

        outgoing_invoices = list(
            self._session.scalars(
                select(AccountingInvoice).where(
                    AccountingInvoice.company_id == company_id,
                    AccountingInvoice.invoice_type == "payable",
                    AccountingInvoice.is_confirmed.is_(True),
                    AccountingInvoice.status.in_(["unpaid", "overdue", "partial"]),
                    AccountingInvoice.due_date <= horizon_date,
                )
            ).all()
        )
        expected_outgoing = sum(inv.remaining_amount for inv in outgoing_invoices)

        unconfirmed_proposals_count = len(
            self._session.scalars(
                select(AccountingInvoice.id).where(
                    AccountingInvoice.company_id == company_id,
                    AccountingInvoice.is_confirmed.is_(False),
                    AccountingInvoice.status != "rejected",
                )
            ).all()
        )

        past_60d = now - timedelta(days=60)
        recent_expenses = [
            t.amount
            for t in txs
            if t.transaction_type == "expense" and _ensure_aware(t.transaction_date) >= past_60d
        ]
        daily_burn_rate = (sum(recent_expenses) / 60.0) if recent_expenses else 0.0
        estimated_recurring_expenses = round(daily_burn_rate * horizon_days, 2)

        projected_balance = current_balance + expected_incoming - expected_outgoing - estimated_recurring_expenses

        return {
            "data_type": "forecast",
            "is_projection": True,
            "confidence": "AI_ESTIMATED",
            "disclaimer": (
                "Cette prévision est une estimation prédictive basée sur les factures confirmées en attente "
                "et les tendances de dépenses. Elle ne constitue pas un arrêté comptable officiel."
            ),
            "horizon_days": horizon_days,
            "current_confirmed_balance": round(current_balance, 2),
            "expected_incoming_receivables": round(expected_incoming, 2),
            "expected_outgoing_payables": round(expected_outgoing, 2),
            "estimated_recurring_burn": estimated_recurring_expenses,
            "projected_net_cash_flow": round(
                expected_incoming - expected_outgoing - estimated_recurring_expenses, 2
            ),
            "projected_final_balance": round(projected_balance, 2),
            "unconfirmed_proposals_excluded_count": unconfirmed_proposals_count,
            "currency": txs[0].currency if txs else "CAD",
            "risk_assessment": "low" if projected_balance > 0 else "high_deficit_risk",
        }

    def reconcile_sales_with_accounting(self, company_id: UUID) -> dict[str, Any]:
        """Compare les ventes e-commerce, paiements, taxes et remboursements avec les écritures confirmées."""
        return FinancialIntegrationService(self._session).reconcile_ecommerce_and_accounting(company_id)

    def get_invoice_detail_enriched(
        self,
        company_id: UUID,
        *,
        invoice_id: UUID | None = None,
        invoice_number: str | None = None,
    ) -> dict[str, Any] | None:
        """Retourne le détail complet d'une facture avec provenance documentaire, lignes, maths, écritures liées et audit."""
        stmt = select(AccountingInvoice).where(AccountingInvoice.company_id == company_id)
        if invoice_id is not None:
            stmt = stmt.where(AccountingInvoice.id == invoice_id)
        elif invoice_number is not None:
            stmt = stmt.where(AccountingInvoice.invoice_number == invoice_number.strip())
        else:
            return None

        invoice = self._session.scalar(stmt)
        if invoice is None:
            return None

        doc_meta: dict[str, Any] | None = None
        if invoice.document_id is not None:
            doc = self._session.scalar(
                select(TenantDocument).where(
                    TenantDocument.id == invoice.document_id,
                    TenantDocument.company_id == company_id,
                )
            )
            if doc is not None:
                doc_meta = {
                    "document_id": str(doc.id),
                    "filename": doc.filename,
                    "kind": doc.kind,
                    "content_type": doc.content_type,
                    "byte_size": doc.byte_size,
                    "sha256": doc.sha256,
                    "classification": doc.classification,
                    "uploaded_at": doc.created_at.isoformat() if doc.created_at else None,
                }

        ds_meta: dict[str, Any] | None = None
        if invoice.dataset_id is not None:
            ds = self._session.scalar(
                select(Dataset).where(
                    Dataset.id == invoice.dataset_id,
                    Dataset.company_id == company_id,
                )
            )
            if ds is not None:
                ds_meta = {
                    "dataset_id": str(ds.id),
                    "name": ds.name,
                    "type": ds.type,
                    "source": ds.source,
                }

        linked_txs = list(
            self._session.scalars(
                select(AccountingTransaction)
                .where(
                    AccountingTransaction.company_id == company_id,
                    or_(
                        AccountingTransaction.invoice_id == invoice.id,
                        AccountingTransaction.reference_id == invoice.invoice_number,
                    ),
                )
                .order_by(AccountingTransaction.transaction_date.asc())
            ).all()
        )

        audit_entries = list(
            self._session.scalars(
                select(AuditLogEntry)
                .where(
                    AuditLogEntry.company_id == company_id,
                    AuditLogEntry.target_type == "AccountingInvoice",
                    AuditLogEntry.target_id == str(invoice.id),
                )
                .order_by(AuditLogEntry.created_at.asc())
            ).all()
        )

        sanitized_notes = invoice.notes or ""
        if "</untrusted_document_data>" in sanitized_notes:
            sanitized_notes = sanitized_notes.replace("</untrusted_document_data>", "[TAG_NEUTRALIZED]")

        extra = invoice.extra_data or {}
        subtotal = (
            round(invoice.subtotal_amount, 2)
            if invoice.subtotal_amount is not None
            else round(max(0.0, invoice.total_amount - invoice.tax_amount), 2)
        )

        return {
            "invoice_id": str(invoice.id),
            "id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "invoice_type": invoice.invoice_type,
            "document_nature": invoice.document_nature,
            "direction": invoice.direction,
            "company_role": invoice.company_role,
            "party_name": invoice.party_name,
            "issuer_name": invoice.issuer_name,
            "recipient_name": invoice.recipient_name,
            "issue_date": invoice.issue_date.strftime("%Y-%m-%d") if invoice.issue_date else None,
            "due_date": invoice.due_date.strftime("%Y-%m-%d") if invoice.due_date else None,
            "subtotal_amount": subtotal,
            "tax_amount": round(invoice.tax_amount, 2),
            "tax_breakdown": invoice.tax_breakdown or {},
            "total_amount": round(invoice.total_amount, 2),
            "paid_amount": round(invoice.paid_amount, 2),
            "remaining_amount": round(invoice.remaining_amount, 2),
            "currency": invoice.currency,
            "status": invoice.status,
            "is_confirmed": invoice.is_confirmed,
            "verification_status": invoice.verification_status,
            "accounting_status": invoice.accounting_status,
            "notes": sanitized_notes,
            "line_items": invoice.line_items or [],
            "math_summary": {
                "subtotal_amount": subtotal,
                "tax_amount": round(invoice.tax_amount, 2),
                "total_amount": round(invoice.total_amount, 2),
                "paid_amount": round(invoice.paid_amount, 2),
                "remaining_amount": round(invoice.remaining_amount, 2),
                "validation": extra.get("math_validation") or {"math_valid": abs((subtotal + invoice.tax_amount) - invoice.total_amount) <= 0.02},
            },
            "classification": {
                "document_nature": invoice.document_nature,
                "invoice_type": invoice.invoice_type,
                "direction": invoice.direction,
                "company_role": invoice.company_role,
                "category": extra.get("category"),
                "confidence_score": invoice.confidence_score,
                "rationale": invoice.classification_rationale,
            },
            "provenance": {
                "source_module": invoice.source_module,
                "external_id": invoice.external_id,
                "idempotency_key": invoice.idempotency_key,
                "document_id": str(invoice.document_id) if invoice.document_id else None,
                "dataset_id": str(invoice.dataset_id) if invoice.dataset_id else None,
                "file_sha256": invoice.file_sha256,
                "source_document": doc_meta,
                "source_dataset": ds_meta,
                "source_refs": extra.get("provenance") or {},
            },
            "duplicate_check": {
                "duplicate_warning": invoice.duplicate_warning,
                "duplicate_fingerprint": invoice.duplicate_fingerprint,
                "duplicate_candidates": invoice.duplicate_candidates or [],
            },
            "linked_entries": [
                {
                    "id": str(tx.id),
                    "transaction_date": tx.transaction_date.isoformat() if tx.transaction_date else None,
                    "transaction_type": tx.transaction_type,
                    "entry_kind": tx.entry_kind,
                    "category": tx.category,
                    "description": tx.description,
                    "amount": round(tx.amount, 2),
                    "tax_amount": round(tx.tax_amount, 2),
                    "currency": tx.currency,
                    "status": tx.status,
                    "is_confirmed": tx.is_confirmed,
                    "verification_status": tx.verification_status,
                    "accounting_status": tx.accounting_status,
                }
                for tx in linked_txs
            ],
            "revision_history": invoice.revision_history or [],
            "audit_trail": [
                {
                    "id": str(a.id),
                    "actor_user_id": str(a.actor_user_id) if a.actor_user_id else None,
                    "action": a.action,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                    "metadata": a.safe_metadata,
                }
                for a in audit_entries
            ],
        }

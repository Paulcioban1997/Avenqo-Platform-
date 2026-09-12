"""Service d'intelligence analytique Accounting AI native (Phase 14).

Fournit les métriques financières confirmées, l'analyse des dépenses, des marges,
des factures impayées, la détection d'anomalies de dépenses et les prévisions de trésorerie (cash flow)
avec séparation stricte entre écritures confirmées et projections IA.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from backend.app.core.cache import cached_for_tenant
from backend.app.models.accounting import AccountingInvoice, AccountingTransaction


class AccountingIntelligenceService:
    """Service d'intelligence comptable et financière avec isolation multi-tenant stricte."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @cached_for_tenant("accounting_overview", ttl_seconds=30)
    def get_financial_overview(self, company_id: UUID) -> dict[str, Any]:
        """Vue d'ensemble financière consolidée du tenant (données réelles confirmées vs créances)."""
        txs = list(
            self._session.scalars(
                select(AccountingTransaction).where(
                    AccountingTransaction.company_id == company_id,
                    AccountingTransaction.is_confirmed.is_(True),
                )
            ).all()
        )

        invoices = list(
            self._session.scalars(
                select(AccountingInvoice).where(
                    AccountingInvoice.company_id == company_id
                )
            ).all()
        )

        total_revenue = sum(t.amount for t in txs if t.transaction_type == "revenue")
        total_expenses = sum(t.amount for t in txs if t.transaction_type == "expense")
        cogs = sum(t.amount for t in txs if t.transaction_type == "expense" and t.category.lower() in {"cogs", "cost of goods", "cout des marchandises"})
        net_income = total_revenue - total_expenses
        gross_profit = total_revenue - cogs
        gross_margin_pct = round((gross_profit / total_revenue * 100), 2) if total_revenue > 0 else 0.0
        operating_margin_pct = round((net_income / total_revenue * 100), 2) if total_revenue > 0 else 0.0

        unpaid_receivables = [
            inv for inv in invoices
            if inv.invoice_type == "receivable" and inv.status in {"unpaid", "overdue", "partial"}
        ]
        unpaid_payables = [
            inv for inv in invoices
            if inv.invoice_type == "payable" and inv.status in {"unpaid", "overdue", "partial"}
        ]

        total_receivables_due = sum(inv.remaining_amount for inv in unpaid_receivables)
        total_payables_due = sum(inv.remaining_amount for inv in unpaid_payables)

        return {
            "data_type": "confirmed_actuals",
            "is_projection": False,
            "currency": txs[0].currency if txs else "CAD",
            "total_revenue": round(total_revenue, 2),
            "total_expenses": round(total_expenses, 2),
            "cogs": round(cogs, 2),
            "net_income": round(net_income, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_margin_pct": gross_margin_pct,
            "operating_margin_pct": operating_margin_pct,
            "transactions_count": len(txs),
            "receivables": {
                "unpaid_count": len(unpaid_receivables),
                "total_due": round(total_receivables_due, 2),
            },
            "payables": {
                "unpaid_count": len(unpaid_payables),
                "total_due": round(total_payables_due, 2),
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

        # Déterminer la période cible
        start_date = datetime(target_year, target_month, 1, tzinfo=timezone.utc)
        if target_month == 12:
            end_date = datetime(target_year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end_date = datetime(target_year, target_month + 1, 1, tzinfo=timezone.utc)

        # Période mois précédent pour comparaison
        if target_month == 1:
            prev_start = datetime(target_year - 1, 12, 1, tzinfo=timezone.utc)
            prev_end = start_date
        else:
            prev_start = datetime(target_year, target_month - 1, 1, tzinfo=timezone.utc)
            prev_end = start_date

        current_txs = list(
            self._session.scalars(
                select(AccountingTransaction).where(
                    AccountingTransaction.company_id == company_id,
                    AccountingTransaction.transaction_type == "expense",
                    AccountingTransaction.is_confirmed.is_(True),
                    AccountingTransaction.transaction_date >= start_date,
                    AccountingTransaction.transaction_date < end_date,
                ).order_by(desc(AccountingTransaction.transaction_date))
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

        categories: dict[str, float] = defaultdict(float)
        for t in current_txs:
            categories[t.category] += t.amount

        total_current = sum(t.amount for t in current_txs)
        total_prev = sum(t.amount for t in prev_txs)
        diff = total_current - total_prev
        diff_pct = round((diff / total_prev * 100), 2) if total_prev > 0 else 0.0

        sorted_categories = sorted(
            [
                {"category": cat, "amount": round(amt, 2), "percentage": round(amt / total_current * 100, 1) if total_current > 0 else 0.0}
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
            "recent_expenses": [
                {
                    "id": str(t.id),
                    "date": t.transaction_date.isoformat(),
                    "category": t.category,
                    "description": t.description,
                    "amount": round(t.amount, 2),
                    "status": t.status,
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

        revenue = sum(t.amount for t in txs if t.transaction_type == "revenue")
        cogs = sum(
            t.amount for t in txs
            if t.transaction_type == "expense" and t.category.lower() in {"cogs", "cost of goods", "cout des marchandises", "inventory"}
        )
        operating_expenses = sum(
            t.amount for t in txs
            if t.transaction_type == "expense" and t.category.lower() not in {"cogs", "cost of goods", "cout des marchandises", "inventory"}
        )
        total_expenses = cogs + operating_expenses

        gross_profit = revenue - cogs
        gross_margin_pct = round((gross_profit / revenue * 100), 2) if revenue > 0 else 0.0
        operating_profit = revenue - total_expenses
        operating_margin_pct = round((operating_profit / revenue * 100), 2) if revenue > 0 else 0.0

        return {
            "data_type": "confirmed_actuals",
            "is_projection": False,
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
    ) -> dict[str, Any]:
        """Liste des factures impayées ou en retard avec montants restants et ancienneté."""
        now = datetime.now(timezone.utc)
        invoices = list(
            self._session.scalars(
                select(AccountingInvoice).where(
                    AccountingInvoice.company_id == company_id,
                    AccountingInvoice.invoice_type == invoice_type,
                    AccountingInvoice.status.in_(["unpaid", "overdue", "partial"]),
                ).order_by(AccountingInvoice.due_date.asc())
            ).all()
        )

        unpaid_list: list[dict[str, Any]] = []
        total_unpaid = 0.0
        total_overdue = 0.0

        for inv in invoices:
            rem = inv.remaining_amount
            total_unpaid += rem
            days_overdue = (now - inv.due_date).days if now > inv.due_date else 0
            is_overdue = days_overdue > 0
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
                "is_overdue": is_overdue,
                "days_overdue": max(0, days_overdue),
                "currency": inv.currency,
            })

        return {
            "data_type": "confirmed_actuals",
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
        """Détecte les dépenses inhabituelles ou anormalement élevées par rapport à la moyenne par catégorie."""
        txs = list(
            self._session.scalars(
                select(AccountingTransaction).where(
                    AccountingTransaction.company_id == company_id,
                    AccountingTransaction.transaction_type == "expense",
                    AccountingTransaction.is_confirmed.is_(True),
                ).order_by(AccountingTransaction.transaction_date.desc())
            ).all()
        )

        if not txs:
            return {
                "data_type": "ai_insights",
                "anomalies_count": 0,
                "anomalies": [],
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
            # Anomalie si le montant dépasse threshold_multiplier * moyenne (et > 100$)
            # ou si expressément marqué 'anomaly' dans extra_data
            is_anomaly = (len(cat_amounts[t.category]) >= 2 and t.amount > (avg * threshold_multiplier) and t.amount > 100.0) or t.extra_data.get("is_anomaly") is True
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
                    "reason": f"Dépense supérieure de {pct_above}% à la moyenne de la catégorie '{t.category}' ({round(avg, 2)} {t.currency}).",
                })

        return {
            "data_type": "ai_insights",
            "threshold_multiplier": threshold_multiplier,
            "anomalies_count": len(anomalies),
            "anomalies": anomalies,
        }

    @cached_for_tenant("accounting_cashflow", ttl_seconds=30)
    def get_cash_flow_forecast(
        self,
        company_id: UUID,
        horizon_days: int = 30,
    ) -> dict[str, Any]:
        """Prévision de trésorerie (Cash Flow Forecast) strictement identifiée comme projection IA.

        Combine l'historique de trésorerie confirmé, les échéances de factures clients (receivables)
        et fournisseurs (payables) à venir, ainsi que le taux de combustion (burn rate) récurrent.
        """
        now = datetime.now(timezone.utc)
        horizon_date = now + timedelta(days=horizon_days)

        # 1. Solde actuel confirmé
        txs = list(
            self._session.scalars(
                select(AccountingTransaction).where(
                    AccountingTransaction.company_id == company_id,
                    AccountingTransaction.is_confirmed.is_(True),
                )
            ).all()
        )
        current_balance = sum(t.amount if t.transaction_type == "revenue" else -t.amount for t in txs)

        # 2. Factures à encaisser (créances) d'ici l'horizon
        incoming_invoices = list(
            self._session.scalars(
                select(AccountingInvoice).where(
                    AccountingInvoice.company_id == company_id,
                    AccountingInvoice.invoice_type == "receivable",
                    AccountingInvoice.status.in_(["unpaid", "overdue", "partial"]),
                    AccountingInvoice.due_date <= horizon_date,
                )
            ).all()
        )
        expected_incoming = sum(inv.remaining_amount for inv in incoming_invoices)

        # 3. Factures à payer (dettes) d'ici l'horizon
        outgoing_invoices = list(
            self._session.scalars(
                select(AccountingInvoice).where(
                    AccountingInvoice.company_id == company_id,
                    AccountingInvoice.invoice_type == "payable",
                    AccountingInvoice.status.in_(["unpaid", "overdue", "partial"]),
                    AccountingInvoice.due_date <= horizon_date,
                )
            ).all()
        )
        expected_outgoing = sum(inv.remaining_amount for inv in outgoing_invoices)

        # 4. Burn rate quotidien estimé sur les 60 derniers jours
        past_60d = now - timedelta(days=60)
        recent_expenses = [
            t.amount for t in txs
            if t.transaction_type == "expense" and t.transaction_date >= past_60d
        ]
        daily_burn_rate = (sum(recent_expenses) / 60.0) if recent_expenses else 0.0
        estimated_recurring_expenses = round(daily_burn_rate * horizon_days, 2)

        # Projection nette
        projected_balance = current_balance + expected_incoming - expected_outgoing - estimated_recurring_expenses

        return {
            "data_type": "forecast",
            "is_projection": True,
            "confidence": "AI_ESTIMATED",
            "disclaimer": "Cette prévision est une estimation prédictive basée sur les factures en attente et les tendances de dépenses. Elle ne constitue pas un arrêté comptable officiel.",
            "horizon_days": horizon_days,
            "current_confirmed_balance": round(current_balance, 2),
            "expected_incoming_receivables": round(expected_incoming, 2),
            "expected_outgoing_payables": round(expected_outgoing, 2),
            "estimated_recurring_burn": estimated_recurring_expenses,
            "projected_net_cash_flow": round(expected_incoming - expected_outgoing - estimated_recurring_expenses, 2),
            "projected_final_balance": round(projected_balance, 2),
            "currency": txs[0].currency if txs else "CAD",
            "risk_assessment": "low" if projected_balance > 0 else "high_deficit_risk",
        }

"""Service d'intelligence cross-agent Retail ↔ CRM ↔ Accounting (Phase 15).

Permet à AI Central d'orchestrer et de corréler les données des 3 domaines validés :
- Retail Intelligence (ventes e-commerce, catalogue, inventaire, commandes)
- CRM AI (prospects, opportunités, scoring, risque d'attrition)
- Accounting AI (recettes/dépenses confirmées, marges, factures impayées, prévision cash flow)

Garantit l'isolation multi-tenant stricte et la séparation absolue entre données
financières/commerciales confirmées et projections prédictives IA.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.app.core.cache import cached_for_tenant
from backend.app.models.commerce_connection import NormalizedCommerceRecord
from backend.app.services.accounting_intelligence_service import AccountingIntelligenceService
from backend.app.services.crm_intelligence_service import CRMIntelligenceService


class CrossAgentIntelligenceService:
    """Service d'orchestration cross-agent multi-tenant."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._crm = CRMIntelligenceService(session)
        self._accounting = AccountingIntelligenceService(session)

    @cached_for_tenant("cross_agent_synthesis", ttl_seconds=30)
    def get_cross_domain_synthesis(self, company_id: UUID) -> dict[str, Any]:
        """Synthèse 360° unifiée combinant Retail, CRM et Accounting."""

        # 1. Pilier Retail (Projection optimisée sur normalized_data uniquement)
        order_records = list(
            self._session.scalars(
                select(NormalizedCommerceRecord.normalized_data).where(
                    NormalizedCommerceRecord.company_id == company_id,
                    NormalizedCommerceRecord.entity_type == "order",
                    NormalizedCommerceRecord.deleted.is_(False),
                )
            ).all()
        )
        product_records = list(
            self._session.scalars(
                select(NormalizedCommerceRecord.normalized_data).where(
                    NormalizedCommerceRecord.company_id == company_id,
                    NormalizedCommerceRecord.entity_type == "product",
                    NormalizedCommerceRecord.deleted.is_(False),
                )
            ).all()
        )

        retail_orders_count = len(order_records)
        retail_orders_total = 0.0
        for data in order_records:
            data = data or {}
            val = data.get("total_amount") or data.get("total") or 0.0
            try:
                retail_orders_total += float(val)
            except (ValueError, TypeError):
                pass

        low_stock_products = []
        for data in product_records:
            data = data or {}
            stock_qty = data.get("stock_quantity") or data.get("stock")
            try:
                if stock_qty is not None and float(stock_qty) <= 10.0:
                    low_stock_products.append({
                        "product_name": data.get("product_name") or data.get("name") or "Produit",
                        "stock": float(stock_qty),
                    })
            except (ValueError, TypeError):
                pass

        retail_summary = {
            "orders_count": retail_orders_count,
            "orders_revenue": round(retail_orders_total, 2),
            "products_count": len(product_records),
            "low_stock_alerts_count": len(low_stock_products),
            "low_stock_samples": low_stock_products[:3],
        }

        # 2. Pilier CRM
        crm_summary = self._crm.get_crm_summary(company_id)
        leads_to_contact = self._crm.get_leads_to_contact_today(company_id, limit=3)
        high_risk_customers = self._crm.get_high_risk_customers(company_id, limit=5)

        # 3. Pilier Accounting
        accounting_overview = self._accounting.get_financial_overview(company_id)
        unpaid_invoices = self._accounting.get_unpaid_invoices(company_id, invoice_type="receivable")
        cash_flow_forecast = self._accounting.get_cash_flow_forecast(company_id, horizon_days=30)

        # 4. Corrélations & Synergies Cross-Agent
        # 4a. Risque Churn croisé avec Factures Impayées (Financial Exposure)
        churn_names = {c["name"].lower(): c for c in high_risk_customers}
        cross_risk_exposure = []
        total_risk_exposure_amount = 0.0

        for inv in unpaid_invoices.get("invoices", []):
            debtor = inv["party_name"].lower()
            matched_churn = None
            for c_name, c_data in churn_names.items():
                # Correspondance partielle nom/entreprise
                if any(part in debtor for part in c_name.split()) or any(part in c_name for part in debtor.split()):
                    matched_churn = c_data
                    break

            if matched_churn:
                cross_risk_exposure.append({
                    "client_name": inv["party_name"],
                    "invoice_number": inv["invoice_number"],
                    "remaining_amount": inv["remaining_amount"],
                    "days_overdue": inv["days_overdue"],
                    "churn_risk": matched_churn.get("churn_risk_score"),
                    "churn_reason": matched_churn.get("churn_reason"),
                })
                total_risk_exposure_amount += inv["remaining_amount"]

        # 4b. Santé Runway & Couverture Commerciale
        projected_balance = cash_flow_forecast.get("projected_final_balance", 0.0)
        weighted_pipeline = crm_summary.get("weighted_pipeline_value", 0.0)
        confirmed_burn = accounting_overview.get("total_expenses", 0.0)

        strategic_insights = []
        if unpaid_invoices.get("total_overdue_amount", 0.0) > 5000:
            strategic_insights.append(
                f"Urgence Recouvrement : {unpaid_invoices.get('total_overdue_amount')} CAD de factures sont déjà en retard, ce qui pèse sur la trésorerie nette."
            )
        if crm_summary.get("weighted_pipeline_value", 0.0) > 20000:
            strategic_insights.append(
                f"Dynamique Commerciale : Pipeline pondéré solide de {round(weighted_pipeline, 2)} CAD à convertir à court terme."
            )
        if low_stock_products:
            strategic_insights.append(
                f"Alerte Stocks Retail : {len(low_stock_products)} produit(s) en stock critique pouvant freiner les ventes futures."
            )

        return {
            "data_type": "cross_agent_synthesis",
            "company_id": str(company_id),
            "pillars": {
                "retail": {
                    "data_type": "confirmed_actuals",
                    **retail_summary,
                },
                "crm": {
                    "confirmed_leads_count": crm_summary.get("total_leads", 0),
                    "pipeline_value": crm_summary.get("total_pipeline_value", 0.0),
                    "weighted_pipeline_projection": crm_summary.get("weighted_pipeline_value", 0.0),
                    "conversion_rate_percent": crm_summary.get("conversion_rate_percent", 0.0),
                    "high_risk_customers_count": crm_summary.get("high_risk_customers", 0),
                    "top_leads_to_contact": leads_to_contact,
                },
                "accounting": {
                    "confirmed_actuals": {
                        "total_revenue": accounting_overview.get("total_revenue", 0.0),
                        "total_expenses": accounting_overview.get("total_expenses", 0.0),
                        "net_income": accounting_overview.get("net_income", 0.0),
                        "gross_margin_pct": accounting_overview.get("gross_margin_pct", 0.0),
                        "operating_margin_pct": accounting_overview.get("operating_margin_pct", 0.0),
                        "total_unpaid_receivables": unpaid_invoices.get("total_unpaid_amount", 0.0),
                        "total_overdue_receivables": unpaid_invoices.get("total_overdue_amount", 0.0),
                    },
                    "forecast_projection": {
                        "data_type": "forecast",
                        "is_projection": True,
                        "confidence": cash_flow_forecast.get("confidence"),
                        "projected_final_balance": projected_balance,
                        "disclaimer": cash_flow_forecast.get("disclaimer"),
                    },
                },
            },
            "cross_domain_correlations": {
                "financial_churn_exposure": {
                    "matched_at_risk_invoices_count": len(cross_risk_exposure),
                    "total_exposed_amount": round(total_risk_exposure_amount, 2),
                    "exposed_invoices": cross_risk_exposure,
                },
                "strategic_balance": {
                    "net_confirmed_income": accounting_overview.get("net_income", 0.0),
                    "pipeline_potential_revenue": crm_summary.get("total_pipeline_value", 0.0),
                    "projected_cash_flow_30d": projected_balance,
                    "overall_business_health": "strong" if (accounting_overview.get("net_income", 0.0) > 0 and weighted_pipeline > 15000) else "monitoring_required",
                },
            },
            "strategic_insights": strategic_insights,
        }

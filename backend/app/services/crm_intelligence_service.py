"""Service d'intelligence analytique CRM AI native (Phase 13).

Fournit les métriques, le scoring de leads, la détection du risque d'attrition (churn)
et les recommandations de suivi pour l'Assistant et l'UI.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from backend.app.core.cache import cached_for_tenant
from backend.app.models.crm import CRMActivity, CRMContact, CRMLead, CRMOpportunity


class CRMIntelligenceService:
    """Service d'analyse CRM avec isolation stricte par tenant (company_id)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @cached_for_tenant("crm_summary", ttl_seconds=30)
    def get_crm_summary(self, company_id: UUID) -> dict[str, Any]:
        """Retourne les métriques clés de performance CRM du tenant."""
        leads = list(
            self._session.scalars(
                select(CRMLead).where(CRMLead.company_id == company_id)
            ).all()
        )
        opportunities = list(
            self._session.scalars(
                select(CRMOpportunity).where(CRMOpportunity.company_id == company_id)
            ).all()
        )
        contacts = list(
            self._session.scalars(
                select(CRMContact).where(CRMContact.company_id == company_id)
            ).all()
        )
        pending_activities = list(
            self._session.scalars(
                select(CRMActivity).where(
                    CRMActivity.company_id == company_id,
                    CRMActivity.status == "pending",
                )
            ).all()
        )

        total_leads = len(leads)
        qualified_leads = sum(1 for l in leads if l.status in {"qualified", "converted"})
        conversion_rate = (qualified_leads / total_leads * 100) if total_leads > 0 else 0.0

        total_pipeline_value = sum(o.amount for o in opportunities if o.stage not in {"closed_lost"})
        weighted_pipeline_value = sum(o.amount * o.probability for o in opportunities if o.stage not in {"closed_lost"})

        high_risk_customers = sum(1 for c in contacts if c.churn_risk == "high")

        return {
            "total_leads": total_leads,
            "qualified_leads": qualified_leads,
            "conversion_rate_percent": round(conversion_rate, 1),
            "total_pipeline_value": round(total_pipeline_value, 2),
            "weighted_pipeline_value": round(weighted_pipeline_value, 2),
            "total_opportunities": len(opportunities),
            "total_contacts": len(contacts),
            "high_risk_customers": high_risk_customers,
            "pending_follow_ups": len(pending_activities),
        }

    @cached_for_tenant("crm_leads_to_contact", ttl_seconds=30)
    def get_leads_to_contact_today(
        self, company_id: UUID, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Identifie les prospects prioritaires à contacter aujourd'hui avec motif IA."""
        # 1. Prospects avec tâches en attente
        query = (
            select(CRMLead)
            .where(CRMLead.company_id == company_id, CRMLead.status != "unqualified")
            .order_by(desc(CRMLead.score), desc(CRMLead.estimated_value))
            .limit(limit)
        )
        leads = list(self._session.scalars(query).all())

        results = []
        for lead in leads:
            reason = (
                f"Score élevé ({lead.score}/100) - Potentiel estimé à {lead.estimated_value:,.2f}"
                if lead.score >= 70
                else f"Étape suivante requise : {lead.next_step or 'Prise de contact'}"
            )
            results.append({
                "lead_id": str(lead.id),
                "name": lead.full_name,
                "company": lead.company_name or "—",
                "email": lead.email,
                "phone": lead.phone or "—",
                "status": lead.status,
                "score": lead.score,
                "estimated_value": lead.estimated_value,
                "conversion_probability": lead.conversion_probability,
                "next_step": lead.next_step or "Planifier un appel de qualification",
                "priority_reason": reason,
            })
        return results

    @cached_for_tenant("crm_leads_ranked", ttl_seconds=30)
    def get_leads_ranked_by_conversion(
        self, company_id: UUID, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Classe les prospects par probabilité de conversion et score IA."""
        query = (
            select(CRMLead)
            .where(CRMLead.company_id == company_id)
            .order_by(desc(CRMLead.conversion_probability), desc(CRMLead.score))
            .limit(limit)
        )
        leads = list(self._session.scalars(query).all())
        return [
            {
                "lead_id": str(l.id),
                "name": l.full_name,
                "company": l.company_name or "—",
                "status": l.status,
                "score": l.score,
                "conversion_probability": round(l.conversion_probability, 2),
                "estimated_value": l.estimated_value,
                "next_step": l.next_step,
            }
            for l in leads
        ]

    @cached_for_tenant("crm_high_risk_customers", ttl_seconds=30)
    def get_high_risk_customers(
        self, company_id: UUID, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Identifie les clients à fort risque d'attrition (churn) avec diagnostic."""
        query = (
            select(CRMContact)
            .where(CRMContact.company_id == company_id)
            .order_by(desc(CRMContact.churn_risk_score), desc(CRMContact.customer_lifetime_value))
            .limit(limit)
        )
        contacts = list(self._session.scalars(query).all())
        return [
            {
                "contact_id": str(c.id),
                "name": c.name,
                "company": c.company_name or "—",
                "email": c.email,
                "customer_lifetime_value": c.customer_lifetime_value,
                "churn_risk": c.churn_risk,
                "churn_risk_score": round(c.churn_risk_score, 2),
                "churn_reason": c.churn_reason or "Baisse d'engagement récente",
            }
            for c in contacts
        ]

    def get_top_potential_revenue(
        self, company_id: UUID, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Identifie les opportunités et comptes représentant la plus grande valeur financière."""
        query = (
            select(CRMOpportunity)
            .where(CRMOpportunity.company_id == company_id, CRMOpportunity.stage != "closed_lost")
            .order_by(desc(CRMOpportunity.amount))
            .limit(limit)
        )
        opps = list(self._session.scalars(query).all())
        return [
            {
                "opportunity_id": str(o.id),
                "title": o.title,
                "company": o.company_name,
                "amount": o.amount,
                "currency": o.currency,
                "stage": o.stage,
                "probability": o.probability,
                "weighted_value": round(o.amount * o.probability, 2),
            }
            for o in opps
        ]

    def generate_follow_up_recommendation(
        self, company_id: UUID, query: str
    ) -> dict[str, Any]:
        """Génère une recommandation de suivi contextualisée."""
        # Recherche par nom de lead ou de contact
        lead = self._session.scalars(
            select(CRMLead)
            .where(
                CRMLead.company_id == company_id,
                (func.lower(CRMLead.first_name).contains(query.lower()))
                | (func.lower(CRMLead.last_name).contains(query.lower()))
                | (func.lower(CRMLead.company_name).contains(query.lower())),
            )
            .limit(1)
        ).first()

        if lead:
            return {
                "target": lead.full_name,
                "company": lead.company_name,
                "status": lead.status,
                "score": lead.score,
                "recommendation": (
                    f"Envoyer un e-mail de relance ciblé sur sa valeur estimée ({lead.estimated_value:,.2f}) "
                    f"avec la proposition de valeur suivante : {lead.next_step or 'Démonstration produit'}"
                ),
                "recommended_channel": "Email" if lead.email else "Téléphone",
                "urgency": "Haute" if lead.score >= 75 else "Moyenne",
            }

        return {
            "target": query,
            "recommendation": "Effectuer une prise de contact téléphonique pour qualifier le besoin.",
            "recommended_channel": "Téléphone",
            "urgency": "Normale",
        }

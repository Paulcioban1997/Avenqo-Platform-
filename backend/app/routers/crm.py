"""Routes API pour le module CRM AI (Phase 13)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.cache import tenant_cache
from backend.app.database import get_db
from backend.app.dependencies.auth import get_tenant_context
from backend.app.models.crm import CRMActivity, CRMContact, CRMLead, CRMOpportunity
from backend.app.services.crm_intelligence_service import CRMIntelligenceService
from shared.ai_engine.contracts import TenantContext

router = APIRouter(prefix="/crm", tags=["crm"])


# --- Schemas ---

class CreateLeadRequest(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: str | None = None
    company_name: str | None = None
    job_title: str | None = None
    source: str = "website"
    status: str = "new"
    score: int = 50
    estimated_value: float = 0.0
    conversion_probability: float = 0.2
    next_step: str | None = None
    notes: str | None = None


class LeadResponse(BaseModel):
    id: UUID
    full_name: str
    email: str
    phone: str | None
    company_name: str | None
    job_title: str | None
    source: str
    status: str
    score: int
    estimated_value: float
    conversion_probability: float
    next_step: str | None
    notes: str | None
    created_at: datetime


class CreateOpportunityRequest(BaseModel):
    title: str
    company_name: str
    amount: float
    currency: str = "CAD"
    stage: str = "discovery"
    probability: float = 0.2
    lead_id: UUID | None = None
    expected_close_date: datetime | None = None
    notes: str | None = None


class OpportunityResponse(BaseModel):
    id: UUID
    title: str
    company_name: str
    amount: float
    currency: str
    stage: str
    probability: float
    weighted_value: float
    expected_close_date: datetime | None
    created_at: datetime


# --- Endpoints ---

@router.get("/summary")
def get_crm_summary(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Retourne les métriques clés de performance CRM du tenant."""
    service = CRMIntelligenceService(db)
    return service.get_crm_summary(tenant.company_id)


@router.get("/leads")
def list_leads(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, le=100),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Liste les prospects du tenant avec filtres optionnels."""
    stmt = select(CRMLead).where(CRMLead.company_id == tenant.company_id)
    if status_filter:
        stmt = stmt.where(CRMLead.status == status_filter)
    stmt = stmt.order_by(CRMLead.created_at.desc()).limit(limit)
    leads = list(db.scalars(stmt).all())
    return [
        {
            "id": str(l.id),
            "full_name": l.full_name,
            "first_name": l.first_name,
            "last_name": l.last_name,
            "email": l.email,
            "phone": l.phone,
            "company_name": l.company_name,
            "job_title": l.job_title,
            "source": l.source,
            "status": l.status,
            "score": l.score,
            "estimated_value": l.estimated_value,
            "conversion_probability": l.conversion_probability,
            "next_step": l.next_step,
            "notes": l.notes,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in leads
    ]


@router.post("/leads", status_code=status.HTTP_201_CREATED)
def create_lead(
    payload: CreateLeadRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Crée un nouveau prospect dans le CRM du tenant."""
    lead = CRMLead(
        company_id=tenant.company_id,
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        phone=payload.phone,
        company_name=payload.company_name,
        job_title=payload.job_title,
        source=payload.source,
        status=payload.status,
        score=payload.score,
        estimated_value=payload.estimated_value,
        conversion_probability=payload.conversion_probability,
        next_step=payload.next_step,
        notes=payload.notes,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    tenant_cache.invalidate_tenant(tenant.company_id)
    return {
        "id": str(lead.id),
        "full_name": lead.full_name,
        "email": lead.email,
        "score": lead.score,
        "status": lead.status,
    }


@router.get("/leads/to-contact")
def leads_to_contact(
    limit: int = Query(default=5, le=50),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Prospects prioritaires à contacter aujourd'hui avec recommandations IA."""
    service = CRMIntelligenceService(db)
    return service.get_leads_to_contact_today(tenant.company_id, limit=limit)


@router.get("/leads/ranked")
def ranked_leads(
    limit: int = Query(default=10, le=50),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Prospects classés par probabilité de conversion et score prédictif."""
    service = CRMIntelligenceService(db)
    return service.get_leads_ranked_by_conversion(tenant.company_id, limit=limit)


@router.get("/opportunities")
def list_opportunities(
    stage: str | None = Query(default=None),
    limit: int = Query(default=50, le=100),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Liste les opportunités commerciales du pipeline."""
    stmt = select(CRMOpportunity).where(CRMOpportunity.company_id == tenant.company_id)
    if stage:
        stmt = stmt.where(CRMOpportunity.stage == stage)
    stmt = stmt.order_by(CRMOpportunity.amount.desc()).limit(limit)
    opps = list(db.scalars(stmt).all())
    return [
        {
            "id": str(o.id),
            "title": o.title,
            "company_name": o.company_name,
            "amount": o.amount,
            "currency": o.currency,
            "stage": o.stage,
            "probability": o.probability,
            "weighted_value": round(o.amount * o.probability, 2),
            "expected_close_date": o.expected_close_date.isoformat() if o.expected_close_date else None,
        }
        for o in opps
    ]


@router.post("/opportunities", status_code=status.HTTP_201_CREATED)
def create_opportunity(
    payload: CreateOpportunityRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Crée une opportunité dans le pipeline CRM."""
    opp = CRMOpportunity(
        company_id=tenant.company_id,
        title=payload.title,
        company_name=payload.company_name,
        amount=payload.amount,
        currency=payload.currency,
        stage=payload.stage,
        probability=payload.probability,
        lead_id=payload.lead_id,
        expected_close_date=payload.expected_close_date,
        notes=payload.notes,
    )
    db.add(opp)
    db.commit()
    db.refresh(opp)
    tenant_cache.invalidate_tenant(tenant.company_id)
    return {
        "id": str(opp.id),
        "title": opp.title,
        "amount": opp.amount,
        "stage": opp.stage,
    }


@router.get("/contacts/high-risk")
def high_risk_contacts(
    limit: int = Query(default=5, le=50),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Clients à risque de départ (churn) avec diagnostic IA."""
    service = CRMIntelligenceService(db)
    return service.get_high_risk_customers(tenant.company_id, limit=limit)


@router.get("/recommendations")
def get_recommendations(
    target: str = Query(default=""),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Recommandation de suivi personnalisée par l'IA."""
    service = CRMIntelligenceService(db)
    return service.generate_follow_up_recommendation(tenant.company_id, query=target)

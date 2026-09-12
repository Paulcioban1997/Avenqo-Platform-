"""Phase 13 — Tests de non-régression et d'isolation multi-tenant pour CRM AI."""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.ai.tools.business.crm_tools import (
    CRMGenericArgs,
    GetCRMOverviewTool,
    GetHighRiskCustomersTool,
    GetLeadsToContactTool,
    GetRankedLeadsTool,
)
from backend.app.ai.tools.contracts import ToolExecutionContext
from backend.app.models.base import Base
from backend.app.models.company import Company
from backend.app.models.crm import CRMContact, CRMLead, CRMOpportunity
from shared.ai_engine.contracts import TenantContext


@pytest.fixture
def db_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'crm_test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session


def _create_company(session, slug: str) -> Company:
    co = Company(
        id=uuid4(),
        name=f"Company {slug}",
        slug=slug,
        email=f"{slug}@example.com",
        country="CA",
        timezone="America/Toronto",
        industry="Technology",
        subscription_plan="professional",
    )
    session.add(co)
    session.flush()
    return co


def test_crm_multi_tenant_isolation(db_session):
    """Vérifie que le Tenant B ne peut jamais voir les leads ou opportunités du Tenant A."""
    company_a = _create_company(db_session, "tenant-a")
    company_b = _create_company(db_session, "tenant-b")

    # Seed Tenant A
    lead_a = CRMLead(
        company_id=company_a.id,
        first_name="LeadA",
        last_name="Dupont",
        email="a@test.com",
        status="qualified",
        score=90,
        estimated_value=50000.0,
        conversion_probability=0.8,
    )
    contact_a = CRMContact(
        company_id=company_a.id,
        name="Client A",
        email="client.a@test.com",
        churn_risk="high",
        churn_risk_score=0.9,
    )
    db_session.add_all([lead_a, contact_a])

    # Seed Tenant B
    lead_b = CRMLead(
        company_id=company_b.id,
        first_name="LeadB",
        last_name="Martin",
        email="b@test.com",
        status="new",
        score=40,
        estimated_value=10000.0,
        conversion_probability=0.2,
    )
    db_session.add(lead_b)
    db_session.commit()

    # Tool Execution Context for Tenant B
    ctx_b = ToolExecutionContext(
        tenant=TenantContext(company_id=company_b.id),
        user_id=uuid4(),
        permissions=frozenset(["ai:use"]),
        request_id="test-req-b",
    )

    overview_tool = GetCRMOverviewTool(db_session)
    overview_b = asyncio.run(overview_tool.run(ctx_b, CRMGenericArgs()))
    assert overview_b.success is True
    # Tenant B has 1 lead, 0 qualified, 0 high risk
    assert overview_b.data["total_leads"] == 1
    assert overview_b.data["qualified_leads"] == 0
    assert overview_b.data["high_risk_customers"] == 0

    # Leads to contact for Tenant B
    leads_tool = GetLeadsToContactTool(db_session)
    leads_res_b = asyncio.run(leads_tool.run(ctx_b, CRMGenericArgs()))
    assert leads_res_b.success is True
    assert leads_res_b.data["count"] == 1
    assert leads_res_b.data["leads_to_contact"][0]["name"] == "LeadB Martin"

    # Churn risk for Tenant B (should be 0, contact_a belongs to Tenant A)
    churn_tool = GetHighRiskCustomersTool(db_session)
    churn_b = asyncio.run(churn_tool.run(ctx_b, CRMGenericArgs()))
    assert churn_b.success is True
    assert churn_b.data["count"] == 0

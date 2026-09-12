"""Phase 15 — Tests de synergie cross-agent (Retail ↔ CRM ↔ Accounting)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.ai.tools.business.cross_agent_tools import (
    CrossAgentGenericArgs,
    GetCrossAgentBusinessHealthTool,
)
from backend.app.ai.tools.contracts import ToolExecutionContext
from backend.app.models.accounting import AccountingInvoice, AccountingTransaction
from backend.app.models.base import Base
from backend.app.models.commerce_connection import CommerceConnection, NormalizedCommerceRecord
from backend.app.models.company import Company
from backend.app.models.crm import CRMContact, CRMLead, CRMOpportunity
from backend.app.services.cross_agent_intelligence_service import CrossAgentIntelligenceService
from shared.ai_engine.contracts import TenantContext


@pytest.fixture
def db_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'cross_agent_test.db'}")
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


def test_cross_agent_synthesis_and_tenant_isolation(db_session):
    """Vérifie la synergie Retail ↔ CRM ↔ Accounting et l'étanchéité multi-tenant."""
    company_a = _create_company(db_session, "tenant-a")
    company_b = _create_company(db_session, "tenant-b")
    now = datetime.now(timezone.utc)

    # 1. Seed Tenant A : Retail + CRM + Accounting
    # Retail
    conn_a = CommerceConnection(
        company_id=company_a.id,
        provider="woocommerce",
        external_account_id="acc-a",
        display_name="Store A",
        status="connected",
    )
    db_session.add(conn_a)
    db_session.flush()

    order_a = NormalizedCommerceRecord(
        company_id=company_a.id,
        connection_id=conn_a.id,
        provider="woocommerce",
        entity_type="order",
        source_record_id="order-1",
        normalized_data={"total_amount": 250.0, "currency": "CAD"},
        deleted=False,
    )
    product_a = NormalizedCommerceRecord(
        company_id=company_a.id,
        connection_id=conn_a.id,
        provider="woocommerce",
        entity_type="product",
        source_record_id="prod-1",
        normalized_data={"name": "Casque Audio Pro", "stock_quantity": 4.0},
        deleted=False,
    )
    # CRM
    lead_a = CRMLead(
        company_id=company_a.id,
        first_name="Alice",
        last_name="Martin",
        email="alice@corp.com",
        status="qualified",
        score=85,
        estimated_value=15000.0,
        conversion_probability=0.7,
    )
    opp_a = CRMOpportunity(
        company_id=company_a.id,
        title="Deal Cloud Alice",
        company_name="Corp Alice",
        amount=15000.0,
        currency="CAD",
        stage="negotiation",
        probability=0.7,
    )
    contact_a = CRMContact(
        company_id=company_a.id,
        name="Bob Churner",
        email="bob@risk.com",
        churn_risk="high",
        churn_risk_score=0.9,
    )
    # Accounting
    tx_a_rev = AccountingTransaction(
        company_id=company_a.id,
        transaction_date=now - timedelta(days=2),
        transaction_type="revenue",
        category="sales",
        description="Ventes confirmées",
        amount=50000.0,
        currency="CAD",
        status="confirmed",
        is_confirmed=True,
    )
    tx_a_cogs = AccountingTransaction(
        company_id=company_a.id,
        transaction_date=now - timedelta(days=2),
        transaction_type="expense",
        category="cogs",
        description="Achats stock",
        amount=20000.0,
        currency="CAD",
        status="confirmed",
        is_confirmed=True,
    )
    inv_a_overdue = AccountingInvoice(
        company_id=company_a.id,
        invoice_number="INV-BOB-01",
        invoice_type="receivable",
        party_name="Bob Churner",  # Correspond au contact à risque
        issue_date=now - timedelta(days=40),
        due_date=now - timedelta(days=10),
        total_amount=3500.0,
        paid_amount=0.0,
        currency="CAD",
        status="overdue",
        is_confirmed=True,
    )

    db_session.add_all([order_a, product_a, lead_a, opp_a, contact_a, tx_a_rev, tx_a_cogs, inv_a_overdue])
    db_session.commit()

    service = CrossAgentIntelligenceService(db_session)

    # 2. Test Tenant A : Synthèse complète
    synthesis_a = service.get_cross_domain_synthesis(company_a.id)
    assert synthesis_a["data_type"] == "cross_agent_synthesis"

    # Vérification Pilier Retail
    retail_a = synthesis_a["pillars"]["retail"]
    assert retail_a["orders_count"] == 1
    assert retail_a["orders_revenue"] == 250.0
    assert retail_a["low_stock_alerts_count"] == 1

    # Vérification Pilier CRM
    crm_a = synthesis_a["pillars"]["crm"]
    assert crm_a["confirmed_leads_count"] == 1
    assert crm_a["pipeline_value"] == 15000.0
    assert crm_a["weighted_pipeline_projection"] == 10500.0
    assert crm_a["high_risk_customers_count"] == 1

    # Vérification Pilier Accounting
    acc_a = synthesis_a["pillars"]["accounting"]
    assert acc_a["confirmed_actuals"]["total_revenue"] == 50000.0
    assert acc_a["confirmed_actuals"]["gross_margin_pct"] == 60.0
    assert acc_a["confirmed_actuals"]["total_overdue_receivables"] == 3500.0
    assert acc_a["forecast_projection"]["is_projection"] is True
    assert acc_a["forecast_projection"]["data_type"] == "forecast"

    # Vérification Corrélations Cross-Agent (Facture Bob Churner croisée)
    correlations_a = synthesis_a["cross_domain_correlations"]
    financial_exposure = correlations_a["financial_churn_exposure"]
    assert financial_exposure["matched_at_risk_invoices_count"] == 1
    assert financial_exposure["total_exposed_amount"] == 3500.0
    assert financial_exposure["exposed_invoices"][0]["client_name"] == "Bob Churner"

    # 3. Test Tenant B : Isolation stricte
    synthesis_b = service.get_cross_domain_synthesis(company_b.id)
    assert synthesis_b["pillars"]["retail"]["orders_count"] == 0
    assert synthesis_b["pillars"]["retail"]["orders_revenue"] == 0.0
    assert synthesis_b["pillars"]["crm"]["confirmed_leads_count"] == 0
    assert synthesis_b["pillars"]["crm"]["pipeline_value"] == 0.0
    assert synthesis_b["pillars"]["accounting"]["confirmed_actuals"]["total_revenue"] == 0.0
    assert synthesis_b["cross_domain_correlations"]["financial_churn_exposure"]["matched_at_risk_invoices_count"] == 0

    # 4. Test Direct Tool Execution
    ctx_a = ToolExecutionContext(
        tenant=TenantContext(company_id=company_a.id),
        user_id=uuid4(),
        permissions=frozenset(["ai:use"]),
        request_id="req-cross-tool",
    )
    tool = GetCrossAgentBusinessHealthTool(db_session)
    res = asyncio.run(tool.run(ctx_a, CrossAgentGenericArgs()))
    assert res.success is True
    assert res.data["pillars"]["retail"]["orders_count"] == 1
    assert res.data["pillars"]["accounting"]["confirmed_actuals"]["total_revenue"] == 50000.0

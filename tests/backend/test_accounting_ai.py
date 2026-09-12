"""Phase 14 — Tests de non-régression et d'isolation multi-tenant pour Accounting AI."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.ai.tools.business.accounting_tools import (
    AccountingGenericArgs,
    CashFlowForecastArgs,
    GetCashFlowForecastTool,
    GetExpenseAnomaliesTool,
    GetFinancialOverviewTool,
    GetMonthlyExpensesTool,
    GetProfitMarginTool,
    GetUnpaidInvoicesTool,
    MonthlyExpensesArgs,
    UnpaidInvoicesArgs,
)
from backend.app.ai.tools.contracts import ToolExecutionContext
from backend.app.models.accounting import AccountingInvoice, AccountingTransaction
from backend.app.models.base import Base
from backend.app.models.company import Company
from shared.ai_engine.contracts import TenantContext


@pytest.fixture
def db_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'accounting_test.db'}")
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


def test_accounting_multi_tenant_isolation_and_forecast_distinction(db_session):
    """Vérifie que le Tenant B ne voit jamais les finances du Tenant A et que les prédictions sont taguées."""
    company_a = _create_company(db_session, "tenant-a")
    company_b = _create_company(db_session, "tenant-b")
    now = datetime.now(timezone.utc)

    # Seed Tenant A
    tx_a_rev = AccountingTransaction(
        company_id=company_a.id,
        transaction_date=now - timedelta(days=2),
        transaction_type="revenue",
        category="sales",
        description="Revenus Tenant A",
        amount=10000.0,
        currency="CAD",
        status="confirmed",
        is_confirmed=True,
    )
    tx_a_cogs = AccountingTransaction(
        company_id=company_a.id,
        transaction_date=now - timedelta(days=2),
        transaction_type="expense",
        category="cogs",
        description="COGS Tenant A",
        amount=4000.0,
        currency="CAD",
        status="confirmed",
        is_confirmed=True,
    )
    inv_a = AccountingInvoice(
        company_id=company_a.id,
        invoice_number="INV-A-1",
        invoice_type="receivable",
        party_name="Client Tenant A",
        issue_date=now - timedelta(days=30),
        due_date=now - timedelta(days=5),
        total_amount=5000.0,
        paid_amount=0.0,
        currency="CAD",
        status="overdue",
        is_confirmed=True,
    )
    db_session.add_all([tx_a_rev, tx_a_cogs, inv_a])

    # Seed Tenant B
    tx_b_rev = AccountingTransaction(
        company_id=company_b.id,
        transaction_date=now - timedelta(days=1),
        transaction_type="revenue",
        category="sales",
        description="Revenus Tenant B",
        amount=2500.0,
        currency="CAD",
        status="confirmed",
        is_confirmed=True,
    )
    tx_b_exp = AccountingTransaction(
        company_id=company_b.id,
        transaction_date=now - timedelta(days=1),
        transaction_type="expense",
        category="software",
        description="Logiciels Tenant B",
        amount=500.0,
        currency="CAD",
        status="confirmed",
        is_confirmed=True,
    )
    db_session.add_all([tx_b_rev, tx_b_exp])
    db_session.commit()

    # Tool Execution Context for Tenant B
    ctx_b = ToolExecutionContext(
        tenant=TenantContext(company_id=company_b.id),
        user_id=uuid4(),
        permissions=frozenset(["ai:use"]),
        request_id="test-accounting-b",
    )

    overview_tool = GetFinancialOverviewTool(db_session)
    overview_b = asyncio.run(overview_tool.run(ctx_b, AccountingGenericArgs()))
    assert overview_b.success is True
    # Tenant B has 2500 revenue and 500 expenses, 0 unpaid receivables
    assert overview_b.data["total_revenue"] == 2500.0
    assert overview_b.data["total_expenses"] == 500.0
    assert overview_b.data["net_income"] == 2000.0
    assert overview_b.data["is_projection"] is False
    assert overview_b.data["receivables"]["unpaid_count"] == 0

    # Unpaid Invoices for Tenant B (should be 0, INV-A belongs to Tenant A)
    invoices_tool = GetUnpaidInvoicesTool(db_session)
    inv_b = asyncio.run(invoices_tool.run(ctx_b, UnpaidInvoicesArgs(invoice_type="receivable")))
    assert inv_b.success is True
    assert inv_b.data["count"] == 0

    # Cash Flow Forecast for Tenant B: must be strictly tagged as forecast
    forecast_tool = GetCashFlowForecastTool(db_session)
    fc_b = asyncio.run(forecast_tool.run(ctx_b, CashFlowForecastArgs(horizon_days=30)))
    assert fc_b.success is True
    assert fc_b.data["is_projection"] is True
    assert fc_b.data["data_type"] == "forecast"
    assert fc_b.data["confidence"] == "AI_ESTIMATED"
    assert "disclaimer" in fc_b.data

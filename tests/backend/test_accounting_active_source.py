"""Accounting must follow the same tenant-scoped active source as Data Hub / Retail."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.models.accounting import AccountingInvoice, AccountingTransaction
from backend.app.models.base import Base, DatasetStatus, UserRole
from backend.app.models.company import Company
from backend.app.models.dataset import Dataset
from backend.app.models.mapping import Mapping
from backend.app.models.user import User
from backend.app.services.accounting_intelligence_service import AccountingIntelligenceService
from backend.app.services.accounting_source_scope import resolve_accounting_dataset_scope
from backend.app.services.retail_source_service import RetailSourceService
from shared.ai_engine.contracts import TenantContext


@pytest.fixture
def db_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'accounting_source.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session


def _company(session, slug: str) -> Company:
    company = Company(
        id=uuid4(),
        name=f"Company {slug}",
        slug=slug,
        email=f"{slug}@example.com",
        country="CA",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="professional",
    )
    session.add(company)
    session.flush()
    return company


def _user(session, company: Company) -> User:
    user = User(
        id=uuid4(),
        company_id=company.id,
        email=f"owner-{company.slug}@example.com",
        password_hash="x",
        first_name="Owner",
        last_name="Test",
        role=UserRole.OWNER,
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    session.add(user)
    session.flush()
    return user


def _dataset(session, company: Company, name: str) -> Dataset:
    dataset = Dataset(
        id=uuid4(),
        company_id=company.id,
        name=name,
        type="csv",
        source=name,
        status=DatasetStatus.READY,
        rows_count=10,
        columns_count=3,
        uploaded_at=datetime.now(timezone.utc),
    )
    dataset.mapping = Mapping(mapping_json={"accepted": {}}, confidence=1, approved=True)
    session.add(dataset)
    session.flush()
    return dataset


def test_accounting_filters_to_selected_dataset_and_never_crosses_tenants(db_session):
    company_a = _company(db_session, "tenant-a")
    company_b = _company(db_session, "tenant-b")
    user_a = _user(db_session, company_a)
    dataset_sales = _dataset(db_session, company_a, "sales-a.csv")
    dataset_other = _dataset(db_session, company_a, "other-a.csv")
    dataset_b = _dataset(db_session, company_b, "sales-b.csv")
    now = datetime.now(timezone.utc)

    db_session.add_all(
        [
            AccountingTransaction(
                company_id=company_a.id,
                dataset_id=dataset_sales.id,
                transaction_date=now,
                transaction_type="revenue",
                category="sales",
                description="Ventes fichier A",
                amount=1000.0,
                currency="CAD",
                status="confirmed",
                is_confirmed=True,
            ),
            AccountingTransaction(
                company_id=company_a.id,
                dataset_id=dataset_other.id,
                transaction_date=now,
                transaction_type="revenue",
                category="sales",
                description="Ventes autre fichier",
                amount=5000.0,
                currency="CAD",
                status="confirmed",
                is_confirmed=True,
            ),
            AccountingTransaction(
                company_id=company_b.id,
                dataset_id=dataset_b.id,
                transaction_date=now,
                transaction_type="revenue",
                category="sales",
                description="Ventes tenant B",
                amount=99999.0,
                currency="CAD",
                status="confirmed",
                is_confirmed=True,
            ),
            AccountingInvoice(
                company_id=company_a.id,
                dataset_id=dataset_other.id,
                invoice_number="INV-OTHER",
                invoice_type="receivable",
                party_name="Client autre",
                issue_date=now - timedelta(days=10),
                due_date=now + timedelta(days=5),
                total_amount=2500.0,
                paid_amount=0.0,
                currency="CAD",
                status="unpaid",
                is_confirmed=True,
            ),
            AccountingInvoice(
                company_id=company_a.id,
                dataset_id=dataset_sales.id,
                invoice_number="INV-SALES",
                invoice_type="receivable",
                party_name="Client sales",
                issue_date=now - timedelta(days=3),
                due_date=now + timedelta(days=10),
                total_amount=400.0,
                paid_amount=0.0,
                currency="CAD",
                status="unpaid",
                is_confirmed=True,
            ),
        ]
    )
    db_session.commit()

    tenant_a = TenantContext(company_id=company_a.id, user_id=user_a.id)
    RetailSourceService(db_session).select_source(
        tenant_a, source_type="dataset", source_id=dataset_sales.id
    )
    dataset_ids, source_context = resolve_accounting_dataset_scope(db_session, tenant_a)
    assert dataset_ids == frozenset({dataset_sales.id})
    assert source_context["dataset_id"] == str(dataset_sales.id)
    assert source_context["selection"] == "dataset"

    overview = AccountingIntelligenceService(db_session).get_financial_overview(
        company_a.id, dataset_ids=dataset_ids
    )
    assert overview["total_revenue"] == 1000.0
    assert overview["receivables"]["unpaid_count"] == 1
    assert overview["receivables"]["total_due"] == 400.0

    # Tenant B remains isolated even if we mistakenly ask with company A ids.
    overview_b = AccountingIntelligenceService(db_session).get_financial_overview(
        company_b.id, dataset_ids=frozenset({dataset_b.id})
    )
    assert overview_b["total_revenue"] == 99999.0
    assert overview_b["receivables"]["unpaid_count"] == 0


def test_accounting_empty_when_selected_source_has_no_ledger_rows(db_session):
    company = _company(db_session, "empty-source")
    user = _user(db_session, company)
    dataset = _dataset(db_session, company, "clean-only.csv")
    other = _dataset(db_session, company, "with-ledger.csv")
    now = datetime.now(timezone.utc)
    db_session.add(
        AccountingTransaction(
            company_id=company.id,
            dataset_id=other.id,
            transaction_date=now,
            transaction_type="expense",
            category="software",
            description="Licence autre source",
            amount=120.0,
            currency="CAD",
            status="confirmed",
            is_confirmed=True,
        )
    )
    db_session.commit()

    tenant = TenantContext(company_id=company.id, user_id=user.id)
    RetailSourceService(db_session).select_source(tenant, source_type="dataset", source_id=dataset.id)
    dataset_ids, _ = resolve_accounting_dataset_scope(db_session, tenant)
    overview = AccountingIntelligenceService(db_session).get_financial_overview(
        company.id, dataset_ids=dataset_ids
    )
    assert overview["total_revenue"] == 0.0
    assert overview["total_expenses"] == 0.0
    assert overview["transactions_count"] == 0

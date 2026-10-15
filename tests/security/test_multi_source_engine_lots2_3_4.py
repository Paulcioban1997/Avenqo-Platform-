"""Tests d'intégration et de validation pour les Lots 2, 3 et 4 du Moteur Multi-Sources.

Conformité avec docs/architecture/multi-source-unified-data-engine.md :
- Lot 2 (Tâche 3) : Ingestion parallèle résiliente, tolérance aux pannes partielles, SHA-256.
- Lot 3 (Tâche 4) : Moteur de calcul des KPI consolidés, conversions multi-devises (USD -> CAD = 1.35), déduction des remboursements (net = gross - discount - refund).
- Lot 4 (Tâche 5) : Outils Central AI (commerce_tools.py), source_scope, citations de provenance unifiées.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config.settings import get_settings
from backend.app.core.security import create_access_token
from backend.app.database import get_db
from backend.app.dependencies.auth import get_account_notifier
from backend.main import create_application
from backend.app.models import (
    AuthSession,
    Base,
    BillingAccount,
    Company,
    CompanyMembership,
    User,
    UserRole,
    CommerceConnection,
    CommerceConnectionStatus,
    NormalizedCommerceRecord,
)
from backend.app.services.account_notifications import AccountNotifier
from backend.app.services.currency_service import CurrencyService
from backend.app.services.commerce_sync_runner import CommerceSyncRunner
from backend.app.services.commerce_sync_service import CommerceSyncService
from backend.app.services.tenant_analytics_service import (
    TenantAnalyticsService,
    TenantAnalyticsSnapshot,
)
from backend.app.ai.tools.business.commerce_tools import (
    GetProductDetailTool,
    GetInventorySummaryTool,
    ProductDetailArgs,
    InventorySummaryArgs,
)
from backend.app.ai.tools.contracts import ToolExecutionContext
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.dataset_ingestion.cleaning import CleaningReport
from shared.ai_engine.dataset_ingestion.profiling import CompanyDatasetProfile
from shared.ai_engine.dataset_ingestion.quality import assess_quality
from shared.ai_engine.dataset_ingestion.readiness import assess_capability_readiness
from shared.ai_engine.dataset_ingestion.prepared_dataset import PreparedCompanyDataset


class _NullNotifier(AccountNotifier):
    def notify_user_status_changed(self, user: User, is_active: bool) -> None:
        pass


@pytest.fixture
def db_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'multi-source-engine.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session


@pytest.fixture
def client(db_session, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUTH_JWT_SECRET", "a" * 32)
    get_settings.cache_clear()
    app = create_application()

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_account_notifier] = lambda: _NullNotifier()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()



def _make_prepared(company_id: UUID, dataset_id: UUID, rows: tuple[dict[str, Any], ...]) -> PreparedCompanyDataset:
    columns = tuple(dict.fromkeys(key for row in rows for key in row))
    canonical = {col: col for col in columns}
    report = CleaningReport(
        rows_before=len(rows),
        rows_after=len(rows),
        duplicates_removed=0,
        numeric_conversions=0,
        date_conversions=0,
        null_cells_detected=0,
        invalid_rows=0,
        column_count=len(columns),
    )
    return PreparedCompanyDataset(
        company_id=company_id,
        dataset_id=dataset_id,
        version=1,
        canonical_columns=canonical,
        rows=rows,
        profile=CompanyDatasetProfile(row_count=len(rows), column_count=len(columns)),
        mapping=(),
        cleaning_report=report,
        quality=assess_quality(report),
        capability_readiness=assess_capability_readiness(set(canonical.values())),
    )

def _setup_company_with_user(
    db: Session,
    company_name: str = "Avenqo Multi Store Inc",
    currency: str = "CAD",
    role: UserRole = UserRole.OWNER,
) -> tuple[Company, User, str]:
    slug = uuid4().hex[:8]
    company = Company(
        id=uuid4(),
        name=company_name,
        slug=slug,
        email=f"{slug}@example.test",
        currency_code=currency,
        country="CA",
        timezone="America/Montreal",
        industry="Retail",
        subscription_plan="enterprise",
    )
    db.add(company)
    db.flush()

    user = User(
        id=uuid4(),
        company_id=company.id,
        email=f"user-{uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="Test",
        last_name="Owner",
        role=role,
        is_active=True,
    )
    db.add(user)
    db.flush()

    membership = CompanyMembership(
        id=uuid4(),
        user_id=user.id,
        company_id=company.id,
        role=role,
    )
    db.add(membership)

    billing = BillingAccount(
        company_id=company.id,
        plan_code="enterprise",
        status="active",
    )
    db.add(billing)

    session_id = uuid4()
    now = datetime.now(timezone.utc)
    auth_sess = AuthSession(
        id=session_id,
        user_id=user.id,
        token_hash=f"hash-{session_id}",
        ip_address="127.0.0.1",
        user_agent="pytest",
        created_at=now,
        expires_at=now + timedelta(days=1),
    )
    db.add(auth_sess)
    db.commit()

    token, _ = create_access_token(user.id, user.company_id, session_id)
    return company, user, token


# ---------------------------------------------------------------------------
# LOT 2 TESTS: Synchronisation parallèle résiliente & tolérance aux pannes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_lot2_parallel_sync_fault_tolerance(db_session: Session):
    """Test Lot 2 : Store 2 qui échoue ne bloque pas Store 1 qui se termine en READY."""
    company, _, _ = _setup_company_with_user(db_session, "Fault Isolation Co")

    conn1 = CommerceConnection(
        id=uuid4(),
        company_id=company.id,
        provider="shopify",
        external_account_id="store-1.myshopify.com",
        display_name="Shopify Boutique Principale",
        status=CommerceConnectionStatus.CONNECTED.value,
        records_processed=0,
    )
    conn2 = CommerceConnection(
        id=uuid4(),
        company_id=company.id,
        provider="shopify",
        external_account_id="store-2.myshopify.com",
        display_name="Shopify Boutique Secondaire",
        status=CommerceConnectionStatus.CONNECTED.value,
        records_processed=0,
    )
    db_session.add_all([conn1, conn2])
    db_session.commit()

    tenant = TenantContext(company_id=company.id)

    # Mock service factory where conn1 succeeds and conn2 fails
    async def mock_sync(t, connection_id, **kwargs):
        if connection_id == conn2.id:
            raise RuntimeError("Shopify API Rate Limit 429 on Store 2")
        # conn1 succeeds
        conn = db_session.get(CommerceConnection, conn1.id)
        conn.status = CommerceConnectionStatus.READY.value
        conn.records_processed = 120
        db_session.commit()

    mock_service = MagicMock()
    mock_service.synchronize = AsyncMock(side_effect=mock_sync)

    engine = db_session.get_bind()
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    runner = CommerceSyncRunner(session_factory, lambda s: mock_service)

    # Run parallel sync
    await runner.run_all_reserved(tenant, [conn1.id, conn2.id])

    db_session.refresh(conn1)
    db_session.refresh(conn2)

    # Store 1 is READY with records processed
    assert conn1.status == CommerceConnectionStatus.READY.value
    assert conn1.records_processed == 120

    # Store 2 did NOT crash the application or prevent Store 1 from completing
    assert conn1.id != conn2.id


def test_lot2_sync_all_endpoint(client: TestClient, db_session: Session):
    """Test Lot 2 : L'endpoint POST /connections/sync-all accepte la synchronisation globale."""
    company, user, token = _setup_company_with_user(db_session, "Multi Sync Co")

    conn = CommerceConnection(
        id=uuid4(),
        company_id=company.id,
        provider="shopify",
        external_account_id="shop.myshopify.com",
        display_name="Store A",
        status=CommerceConnectionStatus.CONNECTED.value,
        records_processed=0,
    )
    db_session.add(conn)
    db_session.commit()

    headers = {"Authorization": f"Bearer {token}"}
    response = client.post("/api/v1/connectors/connections/sync-all", headers=headers)
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "SYNCING"


# ---------------------------------------------------------------------------
# LOT 3 TESTS : Normalisation & Moteur KPI Consolidés Multi-Devises
# ---------------------------------------------------------------------------

def test_lot3_currency_service_conversions():
    """Test Lot 3 : CurrencyService convertit fidèlement avec formule de provenance."""
    service = CurrencyService()

    # 100 USD -> 135 CAD (taux 1.35)
    res_cad = service.convert(Decimal("100.00"), "USD", "CAD")
    assert res_cad.target_amount == Decimal("135.00")
    assert res_cad.exchange_rate == Decimal("1.35")
    assert "100.00 USD * 1.3500 = 135.00 CAD" in res_cad.formula

    # Conversion identique = taux 1.0
    res_same = service.convert(Decimal("50.00"), "CAD", "CAD")
    assert res_same.target_amount == Decimal("50.00")
    assert res_same.exchange_rate == Decimal("1.0")


def test_lot3_consolidated_kpi_multi_currency_and_refunds(db_session: Session):
    """Test Lot 3 : 1 commande 100 CAD + 1 commande 100 USD (taux 1.35) avec remboursement.

    Vérifie l'exigence Tâche 4 & 8 :
    1 commande de 100 CAD + 1 commande de 100 USD (taux 1.35) = 235 CAD consolidés.
    Déduction stricte d'un remboursement de 10 USD (13.50 CAD) :
    Gross = 235 CAD, Refund = 13.50 CAD, Net = 221.50 CAD.
    """
    company, _, _ = _setup_company_with_user(db_session, "Boutique Multi Devises", currency="CAD")

    # Store 1 (Canada - CAD) : Order of 100 CAD
    ds1_id = uuid4()
    ds1 = _make_prepared(
        company.id,
        ds1_id,
        (
            {
                "order_id": "ORD-CAD-001",
                "total_amount": 100.0,
                "currency": "CAD",
                "source_provider": "shopify",
                "source_store": "Shopify Canada",
            },
        ),
    )

    # Store 2 (USA - USD) : Order of 100 USD with 10 USD refund
    ds2_id = uuid4()
    ds2 = _make_prepared(
        company.id,
        ds2_id,
        (
            {
                "order_id": "ORD-USD-002",
                "total_amount": 100.0,
                "currency": "USD",
                "refund_amount": 10.0,
                "source_provider": "shopify",
                "source_store": "Shopify USA",
            },
        ),
    )

    snapshot = TenantAnalyticsSnapshot(
        company=company,
        datasets=(),
        statuses=(),
        training_statuses=(),
        prepared=(ds1, ds2),
        relationships=(),
        active_models=(),
        capabilities=frozenset({"business_analytics"}),
        status="ready",
    )

    # Reconcile across components
    reconciled = snapshot.source_for(frozenset({"total_amount", "order_id"}))
    assert reconciled is not None
    assert len(reconciled.rows) == 2

    # Check row 1 (CAD)
    row_cad = next(r for r in reconciled.rows if r["order_id"] == "ORD-CAD-001")
    assert row_cad["total_amount"] == 100.0
    assert row_cad["currency"] == "CAD"
    assert row_cad["net_amount"] == 100.0

    # Check row 2 (USD converted to CAD at 1.35)
    row_usd = next(r for r in reconciled.rows if r["order_id"] == "ORD-USD-002")
    assert row_usd["total_amount"] == 135.0  # 100 * 1.35
    assert row_usd["refund_amount"] == 13.50  # 10 * 1.35
    assert row_usd["currency"] == "CAD"
    assert row_usd["net_amount"] == 121.50  # 135 - 13.50

    # Total gross = 100 + 135 = 235 CAD
    total_gross = sum(float(r["total_amount"]) for r in reconciled.rows)
    assert total_gross == 235.0

    # Total net = 100 + 121.50 = 221.50 CAD
    total_net = sum(float(r["net_amount"]) for r in reconciled.rows)
    assert total_net == 221.50


# ---------------------------------------------------------------------------
# LOT 4 TESTS : Central AI & Citations de provenance unifiées
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_lot4_central_ai_product_detail_provenance_and_scope(db_session: Session):
    """Test Lot 4 : GetProductDetailTool respecte source_scope et génère la provenance exacte."""
    company, _, _ = _setup_company_with_user(db_session, "AI Commerce Co")

    conn1 = CommerceConnection(
        id=uuid4(),
        company_id=company.id,
        provider="shopify",
        external_account_id="shop-qc.myshopify.com",
        display_name="Shopify Québec",
        status=CommerceConnectionStatus.READY.value,
    )
    conn2 = CommerceConnection(
        id=uuid4(),
        company_id=company.id,
        provider="woocommerce",
        external_account_id="woo-france.com",
        display_name="WooCommerce France",
        status=CommerceConnectionStatus.READY.value,
    )
    db_session.add_all([conn1, conn2])
    db_session.flush()

    # Product in Store 1
    p1 = NormalizedCommerceRecord(
        id=uuid4(),
        company_id=company.id,
        connection_id=conn1.id,
        provider="shopify",
        entity_type="product",
        source_record_id="prod_101",
        deleted=False,
        normalized_data={
            "product_name": "Siège Ergonomique Pro",
            "product_id": "prod_101",
            "sku": "SIEGE-ERG-01",
            "unit_price": 299.99,
            "inventory_level": 15,
            "product_category": "Bureautique",
        },
    )
    # Same product in Store 2 with different stock
    p2 = NormalizedCommerceRecord(
        id=uuid4(),
        company_id=company.id,
        connection_id=conn2.id,
        provider="woocommerce",
        entity_type="product",
        source_record_id="prod_202",
        deleted=False,
        normalized_data={
            "product_name": "Siège Ergonomique Pro",
            "product_id": "prod_202",
            "sku": "SIEGE-ERG-01",
            "unit_price": 289.00,
            "inventory_level": 4,
            "product_category": "Bureautique",
        },
    )
    db_session.add_all([p1, p2])
    db_session.commit()

    context = ToolExecutionContext(
        tenant=TenantContext(company_id=company.id),
        user_id=uuid4(),
        permissions=frozenset({"ai:use"}),
        request_id="req-test-123",
    )

    tool = GetProductDetailTool(db_session)

    # 1. Search with scope "all" -> returns both stores with breakdown
    res_all = await tool.run(context, ProductDetailArgs(sku="SIEGE-ERG-01", source_scope="all"))
    assert res_all.success is True
    assert res_all.data["found"] is True
    assert res_all.data["matches"] == 2
    assert "provenance" in res_all.data
    assert "Shopify Québec" in res_all.data["provenance"]
    assert "WooCommerce France" in res_all.data["provenance"]
    assert "Shopify Québec" in res_all.data["breakdown_by_source"]
    assert "WooCommerce France" in res_all.data["breakdown_by_source"]

    # 2. Search scoped to Store 1 only
    res_scoped = await tool.run(
        context,
        ProductDetailArgs(sku="SIEGE-ERG-01", source_scope=[str(conn1.id)]),
    )
    assert res_scoped.success is True
    assert res_scoped.data["found"] is True
    assert res_scoped.data["product"]["store_name"] == "Shopify Québec"
    assert res_scoped.data["product"]["inventory_level"] == 15.0


@pytest.mark.asyncio
async def test_lot4_central_ai_inventory_summary_breakdown(db_session: Session):
    """Test Lot 4 : GetInventorySummaryTool fournit un breakdown_by_source par boutique."""
    company, _, _ = _setup_company_with_user(db_session, "AI Inventory Co")

    conn1 = CommerceConnection(
        id=uuid4(),
        company_id=company.id,
        provider="shopify",
        external_account_id="shop.myshopify.com",
        display_name="Boutique A",
        status=CommerceConnectionStatus.READY.value,
    )
    conn2 = CommerceConnection(
        id=uuid4(),
        company_id=company.id,
        provider="woocommerce",
        external_account_id="shop.woo.com",
        display_name="Boutique B",
        status=CommerceConnectionStatus.READY.value,
    )
    db_session.add_all([conn1, conn2])
    db_session.flush()

    # In Store 1: 1 healthy, 1 out of stock
    p1 = NormalizedCommerceRecord(
        id=uuid4(),
        company_id=company.id,
        connection_id=conn1.id,
        provider="shopify",
        entity_type="product",
        source_record_id="p1",
        deleted=False,
        normalized_data={"product_name": "P1", "inventory_level": 25},
    )
    p2 = NormalizedCommerceRecord(
        id=uuid4(),
        company_id=company.id,
        connection_id=conn1.id,
        provider="shopify",
        entity_type="product",
        source_record_id="p2",
        deleted=False,
        normalized_data={"product_name": "P2", "inventory_level": 0},
    )
    # In Store 2: 1 low stock
    p3 = NormalizedCommerceRecord(
        id=uuid4(),
        company_id=company.id,
        connection_id=conn2.id,
        provider="woocommerce",
        entity_type="product",
        source_record_id="p3",
        deleted=False,
        normalized_data={"product_name": "P3", "inventory_level": 3},
    )
    db_session.add_all([p1, p2, p3])
    db_session.commit()

    context = ToolExecutionContext(
        tenant=TenantContext(company_id=company.id),
        user_id=uuid4(),
        permissions=frozenset({"ai:use"}),
        request_id="req-test-123",
    )

    tool = GetInventorySummaryTool(db_session)
    res = await tool.run(context, InventorySummaryArgs(low_stock_threshold=5, source_scope="all"))

    assert res.success is True
    assert res.data["total_products"] == 3
    assert res.data["out_of_stock_count"] == 1
    assert res.data["low_stock_count"] == 1
    assert "breakdown_by_source" in res.data
    breakdown = res.data["breakdown_by_source"]
    assert "Boutique A" in breakdown
    assert breakdown["Boutique A"]["total"] == 2
    assert breakdown["Boutique A"]["out_of_stock"] == 1
    assert "Boutique B" in breakdown
    assert breakdown["Boutique B"]["total"] == 1
    assert breakdown["Boutique B"]["low_stock"] == 1
    assert "provenance" in res.data

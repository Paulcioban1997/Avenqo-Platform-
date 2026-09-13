from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.ai.tools.business.commerce_tools import (
    GetInventorySummaryTool,
    GetProductDetailTool,
    InventorySummaryArgs,
    ProductDetailArgs,
)
from backend.app.ai.tools.contracts import ToolExecutionContext
from backend.app.models import (
    Base,
    CommerceConnection,
    CommerceConnectionStatus,
    Company,
    Dataset,
    DatasetStatus,
    Mapping,
    NormalizedCommerceRecord,
    User,
    UserRole,
)
from backend.app.services.retail_source_service import RetailSourceService
from shared.ai_engine.contracts import TenantContext


def _company(session, name: str) -> tuple[Company, User]:
    company = Company(
        id=uuid4(),
        name=name,
        slug=f"{name.lower()}-{uuid4().hex[:6]}",
        email=f"{uuid4().hex}@example.com",
        country="Canada",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="professional",
        currency_code="CAD",
    )
    session.add(company)
    session.flush()
    user = User(
        id=uuid4(),
        company_id=company.id,
        first_name="Admin",
        last_name="User",
        email=f"{uuid4().hex}@example.com",
        password_hash="hash",
        role=UserRole.OWNER,
        email_verified_at=datetime.now(timezone.utc),
    )
    session.add(user)
    session.commit()
    return company, user


def _dataset(session, company, name: str) -> Dataset:
    dataset = Dataset(
        id=uuid4(),
        company_id=company.id,
        name=name,
        type="csv",
        source=str(Path(name)),
        rows_count=1,
        columns_count=7,
        status=DatasetStatus.READY,
        uploaded_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
    )
    dataset.mapping = Mapping(mapping_json={"accepted": {}}, confidence=1, approved=True)
    session.add(dataset)
    session.commit()
    return dataset


@pytest.fixture
def woo_stock_env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'woo-stock.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        company_a, user_a = _company(session, "WooRetail")
        company_b, user_b = _company(session, "OtherRetail")

        dataset = _dataset(session, company_a, "woocommerce-retail.csv")
        connection = CommerceConnection(
            id=uuid4(),
            company_id=company_a.id,
            provider="woocommerce",
            external_account_id="https://mystore.example",
            display_name="WooCommerce Store",
            status=CommerceConnectionStatus.READY.value,
            encrypted_credentials="enc",
            dataset_ids={"retail": str(dataset.id)},
            last_successful_sync=datetime(2026, 9, 8, 14, 0, tzinfo=timezone.utc),
        )
        session.add(connection)
        session.commit()

        # Initial stock: 19
        record = NormalizedCommerceRecord(
            id=uuid4(),
            company_id=company_a.id,
            connection_id=connection.id,
            provider="woocommerce",
            entity_type="product",
            source_record_id="woo-prod-101",
            source_updated_at=datetime(2026, 9, 8, 14, 0, tzinfo=timezone.utc),
            normalized_data={
                "product_name": "Wireless Headphones",
                "product_id": "101",
                "sku": "WH-1000",
                "regular_price": 99.0,
                "price": 99.0,
                "unit_price": 99.0,
                "stock_quantity": 19,
                "inventory_level": 19,
                "in_stock": True,
                "product_category": "Audio",
            },
            deleted=False,
        )
        session.add(record)
        session.commit()

        yield SimpleNamespace(
            session=session,
            company_a=company_a,
            user_a=user_a,
            company_b=company_b,
            user_b=user_b,
            connection=connection,
            product_record=record,
        )


@pytest.mark.asyncio
async def test_woocommerce_stock_update_19_to_25_live_reflection(woo_stock_env):
    """Vérifie la mise à jour de stock 19 -> 25 sans cache rassis et avec isolation."""
    env = woo_stock_env
    tenant_a = TenantContext(env.company_a.id)
    tenant_b = TenantContext(env.company_b.id)

    # 1. Sélectionner WooCommerce comme source active
    RetailSourceService(env.session).select_source(
        tenant_a,
        source_type="connector",
        source_id=env.connection.id,
    )

    tool = GetProductDetailTool(env.session)
    inventory_tool = GetInventorySummaryTool(env.session)
    ctx_a = ToolExecutionContext(
        tenant=tenant_a,
        user_id=env.user_a.id,
        permissions=frozenset({"ai:use"}),
        request_id="req-1",
    )

    # 2. Avant mise à jour : stock doit être 19
    res_before = await tool.run(ctx_a, ProductDetailArgs(product_name="Wireless Headphones"))
    assert res_before.success is True
    assert res_before.data["found"] is True
    assert res_before.data["product"]["stock_quantity"] == 19
    assert res_before.data["product"]["product_name"] == "Wireless Headphones"

    # 3. Simuler la mise à jour du stock WooCommerce 19 -> 25
    env.product_record.normalized_data = {
        **env.product_record.normalized_data,
        "stock_quantity": 25,
        "inventory_level": 25,
    }
    env.product_record.source_updated_at = datetime(2026, 9, 8, 14, 30, tzinfo=timezone.utc)
    env.session.commit()

    # 4. Après mise à jour : l'outil AI DOIT retourner immédiatement 25 sans cache
    res_after = await tool.run(ctx_a, ProductDetailArgs(product_name="Wireless Headphones"))
    assert res_after.success is True
    assert res_after.data["found"] is True
    assert res_after.data["product"]["stock_quantity"] == 25
    assert res_after.data["product"]["inventory_level"] == 25

    # 5. Inventory summary tool doit également refléter le stock mis à jour
    inv_res = await inventory_tool.run(ctx_a, InventorySummaryArgs(low_stock_threshold=10))
    assert inv_res.success is True
    assert inv_res.data["total_products"] == 1
    assert inv_res.data["healthy_stock_count"] == 1
    assert inv_res.data["low_stock_count"] == 0

    # 6. Étanchéité multi-tenant : Tenant B ne voit pas le produit de Tenant A
    ctx_b = ToolExecutionContext(
        tenant=tenant_b,
        user_id=env.user_b.id,
        permissions=frozenset({"ai:use"}),
        request_id="req-2",
    )
    res_tenant_b = await tool.run(ctx_b, ProductDetailArgs(product_name="Wireless Headphones"))
    assert res_tenant_b.data.get("found") is False

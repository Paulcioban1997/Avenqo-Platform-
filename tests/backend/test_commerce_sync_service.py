import csv
import base64
import hashlib
import hmac
import io
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.models import (
    Base,
    CommerceConnection,
    CommerceConnectionStatus,
    CommerceWebhookReceipt,
    Company,
    NormalizedCommerceRecord,
)
from backend.app.services.commerce_sync_service import CommerceSyncService
from backend.app.connectors.shopify import ShopifyConnector
from shared.ai_engine.connectors.catalog import COMMERCE_CONNECTOR_CATALOG
from shared.ai_engine.connectors.commerce import ConnectorPage, ConnectorSyncContext
from shared.ai_engine.connectors.registry import CommerceConnectorRegistry
from shared.ai_engine.contracts import TenantContext


class _PagedShopifyConnector:
    definition = next(
        item for item in COMMERCE_CONNECTOR_CATALOG if item.provider == "shopify"
    )

    def __init__(self) -> None:
        self.updated_since: list[str | None] = []
        self.replay_incremental = False
        self.fail_second_page_once = False
        self.cursors: list[str | None] = []

    async def sync_orders(self, context: ConnectorSyncContext) -> ConnectorPage:
        self.updated_since.append(context.updated_since)
        self.cursors.append(context.cursor)
        if context.updated_since is not None:
            if self.replay_incremental:
                return ConnectorPage((self._order("2026-01-02T00:00:00Z", 2),))
            return ConnectorPage(())
        if context.cursor is None:
            return ConnectorPage((self._order("2026-01-01T00:00:00Z", 1),), "page-2")
        if self.fail_second_page_once:
            self.fail_second_page_once = False
            raise RuntimeError("temporary page failure")
        return ConnectorPage((self._order("2026-01-02T00:00:00Z", 2),))

    @staticmethod
    def _order(updated_at: str, line_count: int) -> dict:
        lines = [
            {
                "id": "gid://shopify/LineItem/1",
                "quantity": 2,
                "originalUnitPriceSet": {
                    "shopMoney": {"amount": "40.00", "currencyCode": "CAD"}
                },
                "discountedTotalSet": {
                    "shopMoney": {"amount": "80.00", "currencyCode": "CAD"}
                },
                "product": {
                    "id": "gid://shopify/Product/1",
                    "title": "Jacket",
                    "productType": "Outerwear",
                },
                "variant": {
                    "id": "gid://shopify/ProductVariant/1",
                    "sku": "JACKET-BLACK",
                    "inventoryQuantity": 8,
                },
                "discountAllocations": [],
            }
        ]
        if line_count == 2:
            lines.append(
                {
                    "id": "gid://shopify/LineItem/2",
                    "quantity": 1,
                    "originalUnitPriceSet": {
                        "shopMoney": {"amount": "40.00", "currencyCode": "CAD"}
                    },
                    "discountedTotalSet": {
                        "shopMoney": {"amount": "40.00", "currencyCode": "CAD"}
                    },
                    "product": {
                        "id": "gid://shopify/Product/2",
                        "title": "Hat",
                        "productType": "Accessories",
                    },
                    "variant": {
                        "id": "gid://shopify/ProductVariant/2",
                        "sku": "HAT-BLACK",
                        "inventoryQuantity": 4,
                    },
                    "discountAllocations": [],
                }
            )
        return {
            "id": "gid://shopify/Order/1",
            "name": "#1001",
            "createdAt": "2026-01-01T00:00:00Z",
            "updatedAt": updated_at,
            "currencyCode": "CAD",
            "email": "owner@example.com",
            "sourceName": "web",
            "displayFulfillmentStatus": "FULFILLED",
            "customer": {"id": "gid://shopify/Customer/1"},
            "shippingAddress": {"countryCodeV2": "CA"},
            "currentSubtotalPriceSet": {
                "shopMoney": {"amount": "120.00", "currencyCode": "CAD"}
            },
            "currentTotalPriceSet": {
                "shopMoney": {"amount": "120.00", "currencyCode": "CAD"}
            },
            "currentTotalTaxSet": {
                "shopMoney": {"amount": "0.00", "currencyCode": "CAD"}
            },
            "totalDiscountsSet": {
                "shopMoney": {"amount": "0.00", "currencyCode": "CAD"}
            },
            "lineItems": {"nodes": lines},
            "refunds": [],
        }


class _ConnectionLifecycle:
    def __init__(self, connection: CommerceConnection) -> None:
        self.connection = connection

    def get_connection(self, tenant, connection_id):
        assert tenant.company_id == self.connection.company_id
        assert connection_id == self.connection.id
        return self.connection

    async def sync_context(self, tenant, connection_id):
        return ConnectorSyncContext(
            tenant_id=tenant.company_id,
            connection_id=connection_id,
            access_token="backend-only",
            external_account_id=self.connection.external_account_id,
        )


class _RecordingIngestion:
    def __init__(self) -> None:
        self.uploads: list[tuple[str, bytes]] = []
        self.deletions = []
        self.dataset_id = uuid4()

    def upload(self, tenant, module_code, filename, content):
        assert module_code == "retail"
        self.uploads.append((filename, content))
        return SimpleNamespace(id=self.dataset_id)

    def delete_if_exists(self, tenant, dataset_id):
        self.deletions.append((tenant.company_id, dataset_id))


class _PermissionFailureOnceIngestion(_RecordingIngestion):
    def __init__(self) -> None:
        super().__init__()
        self.attempts = 0

    def upload(self, tenant, module_code, filename, content):
        self.attempts += 1
        if self.attempts == 1:
            raise PermissionError("artifact root is not writable")
        return super().upload(tenant, module_code, filename, content)


def test_snapshot_uses_discounted_shopify_refund_amount_and_processed_time() -> None:
    service = CommerceSyncService(None, None, None, None)
    order = _PagedShopifyConnector._order("2026-01-02T00:00:00Z", 1)
    normalized_order = service._normalize_order(order)
    normalized_refund = service._normalize_refund(
        {
            "id": "gid://shopify/Refund/1",
            "orderId": "gid://shopify/Order/1",
            "createdAt": "2026-01-03T00:00:00Z",
            "processedAt": "2026-01-04T00:00:00Z",
            "updatedAt": "2026-01-04T00:00:00Z",
            "totalRefundedSet": {
                "shopMoney": {"amount": "32.00", "currencyCode": "CAD"}
            },
            "refundLineItems": {
                "nodes": [
                    {
                        "quantity": 1,
                        "subtotalSet": {
                            "shopMoney": {
                                "amount": "32.00",
                                "currencyCode": "CAD",
                            }
                        },
                        "lineItem": {"id": "gid://shopify/LineItem/1"},
                    }
                ]
            },
        }
    )
    connection = SimpleNamespace(
        id=uuid4(),
        provider="shopify",
        external_account_id="alpha.myshopify.com",
    )

    rows = service._snapshot_rows(
        connection,
        [
            SimpleNamespace(entity_type="orders", normalized_data=normalized_order),
            SimpleNamespace(entity_type="refunds", normalized_data=normalized_refund),
        ],
    )

    assert normalized_refund["refund_timestamp"] == "2026-01-04T00:00:00Z"
    assert rows[0]["refund_amount"] == "32"


def test_snapshot_keeps_shopify_products_customers_and_inventory_without_orders() -> None:
    service = CommerceSyncService(None, None, None, None)
    connection = SimpleNamespace(
        id=uuid4(),
        provider="shopify",
        external_account_id="avenqo-retail-test.myshopify.com",
    )
    records = [
        SimpleNamespace(
            entity_type="customers",
            normalized_data={
                "customer_id": "gid://shopify/Customer/1",
                "email": "customer@example.com",
                "country": "CA",
                "updated_at": "2026-09-08T17:00:00Z",
            },
        ),
        SimpleNamespace(
            entity_type="products",
            normalized_data={
                "product_id": "gid://shopify/Product/1",
                "product_name": "Coffee",
                "product_category": "Drinks",
                "updated_at": "2026-09-08T17:00:00Z",
                "variants": [
                    {
                        "variant_id": "gid://shopify/ProductVariant/1",
                        "sku": "COFFEE-1",
                        "unit_price": "12.00",
                        "inventory_item_id": "gid://shopify/InventoryItem/1",
                    }
                ],
            },
        ),
        SimpleNamespace(
            entity_type="inventory",
            normalized_data={
                "inventory_item_id": "gid://shopify/InventoryItem/1",
                "sku": "COFFEE-1",
                "inventory_level": 9,
            },
        ),
    ]

    rows = service._snapshot_rows(connection, records)

    assert len(rows) == 2
    customer = next(row for row in rows if row.get("customer_id"))
    product = next(row for row in rows if row.get("product_id"))
    assert customer["customer_email"] == "customer@example.com"
    assert customer.get("order_id") is None
    assert customer.get("total_amount") is None
    assert product["product_id"] == "COFFEE-1"
    assert product["product_name"] == "Coffee"
    assert product["inventory_level"] == 9
    assert product.get("order_id") is None
    assert product.get("total_amount") is None


@pytest.mark.asyncio
async def test_sync_upserts_pages_and_reuses_stable_retail_snapshot(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'commerce-sync.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        company = Company(
            name="Alpha",
            slug="alpha",
            email="alpha@example.com",
            country="Canada",
            timezone="America/Toronto",
            industry="Retail",
            subscription_plan="professional",
        )
        session.add(company)
        session.flush()
        connection = CommerceConnection(
            company_id=company.id,
            provider="shopify",
            external_account_id="alpha.myshopify.com",
            encrypted_credentials="unused-by-test",
            status=CommerceConnectionStatus.CONNECTED.value,
            capabilities=["orders"],
        )
        session.add(connection)
        session.commit()

        connector = _PagedShopifyConnector()
        registry = CommerceConnectorRegistry()
        registry.register(connector)
        ingestion = _RecordingIngestion()
        service = CommerceSyncService(
            session,
            registry,
            _ConnectionLifecycle(connection),
            ingestion,
        )
        tenant = TenantContext(company_id=company.id)

        initial = await service.synchronize(tenant, connection.id)
        incremental = await service.synchronize(tenant, connection.id)

        records = session.scalars(select(NormalizedCommerceRecord)).all()
        assert len(records) == 1
        assert len(records[0].normalized_data["line_items"]) == 2
        assert initial.initial_sync is True
        assert incremental.initial_sync is False
        assert initial.dataset_id == ingestion.dataset_id
        assert incremental.dataset_id == ingestion.dataset_id
        assert len(ingestion.uploads) == 1
        assert ingestion.uploads[0][0] == f"shopify-{connection.id}-retail.csv"
        rows = list(
            csv.DictReader(io.StringIO(ingestion.uploads[0][1].decode("utf-8")))
        )
        assert len(rows) == 2
        assert sum(float(row["total_amount"]) for row in rows) == 120.0
        assert connection.status == CommerceConnectionStatus.READY.value
        assert connection.records_processed == 0
        assert connection.last_successful_sync is not None
        assert "_run" not in connection.sync_cursor
        assert connector.updated_since[-1] is not None
        assert connection.last_successful_sync <= datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_materialization_permission_failure_is_truthful_and_retryable(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'commerce-permission.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        company = Company(
            name="Storage Retry",
            slug="storage-retry",
            email="storage@example.com",
            country="Canada",
            timezone="America/Toronto",
            industry="Retail",
            subscription_plan="professional",
        )
        session.add(company)
        session.flush()
        connection = CommerceConnection(
            company_id=company.id,
            provider="shopify",
            external_account_id="storage.myshopify.com",
            encrypted_credentials="unused-by-test",
            status=CommerceConnectionStatus.CONNECTED.value,
            capabilities=["orders"],
            dataset_ids={"retail": str(uuid4())},
        )
        session.add(connection)
        session.commit()
        connector = _PagedShopifyConnector()
        registry = CommerceConnectorRegistry()
        registry.register(connector)
        ingestion = _PermissionFailureOnceIngestion()
        service = CommerceSyncService(
            session,
            registry,
            _ConnectionLifecycle(connection),
            ingestion,
        )
        tenant = TenantContext(company_id=company.id)

        with pytest.raises(Exception, match="Commerce synchronization failed"):
            await service.synchronize(tenant, connection.id)

        assert connection.status == CommerceConnectionStatus.ERROR.value
        assert connection.error_category == "storage_unavailable"
        assert connection.last_successful_sync is None
        previous_dataset_id = connection.dataset_ids["retail"]
        assert previous_dataset_id != str(ingestion.dataset_id)
        assert session.scalar(select(NormalizedCommerceRecord)) is not None

        result = await service.synchronize(tenant, connection.id)

        assert result.dataset_id == ingestion.dataset_id
        assert connection.status == CommerceConnectionStatus.READY.value
        assert connection.error_category is None
        assert connection.last_successful_sync is not None
        assert connection.dataset_ids["retail"] == str(ingestion.dataset_id)
        assert connection.dataset_ids["retail"] != previous_dataset_id
        assert ingestion.attempts == 2


def test_legacy_failed_snapshot_is_marked_for_materialization() -> None:
    connection = CommerceConnection(
        company_id=uuid4(),
        provider="shopify",
        external_account_id="legacy.myshopify.com",
        encrypted_credentials="unused-by-test",
        status=CommerceConnectionStatus.ERROR.value,
        current_entity="retail_snapshot",
        sync_cursor={"orders": {"completed": True}},
    )
    service = CommerceSyncService(
        SimpleNamespace(commit=lambda: None),
        None,
        None,
        None,
    )

    run = service._begin_or_resume(connection)

    assert run.state["_snapshot_pending"] is True


@pytest.mark.asyncio
async def test_sync_resumes_cursor_and_skips_unchanged_replay(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'commerce-resume.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        company = Company(
            name="Resume",
            slug="resume",
            email="resume@example.com",
            country="Canada",
            timezone="America/Toronto",
            industry="Retail",
            subscription_plan="professional",
        )
        session.add(company)
        session.flush()
        connection = CommerceConnection(
            company_id=company.id,
            provider="shopify",
            external_account_id="resume.myshopify.com",
            encrypted_credentials="unused-by-test",
            status=CommerceConnectionStatus.CONNECTED.value,
            capabilities=["orders"],
        )
        session.add(connection)
        session.commit()
        connector = _PagedShopifyConnector()
        connector.fail_second_page_once = True
        registry = CommerceConnectorRegistry()
        registry.register(connector)
        ingestion = _RecordingIngestion()
        service = CommerceSyncService(
            session,
            registry,
            _ConnectionLifecycle(connection),
            ingestion,
        )
        tenant = TenantContext(company_id=company.id)

        with pytest.raises(Exception, match="Commerce synchronization failed"):
            await service.synchronize(tenant, connection.id)
        assert connection.status == CommerceConnectionStatus.ERROR.value
        assert connection.sync_started_at is None
        assert connection.sync_cursor["orders"]["next_cursor"] == "page-2"

        await service.synchronize(tenant, connection.id)
        connector.replay_incremental = True
        await service.synchronize(tenant, connection.id)

        assert connector.cursors[:3] == [None, "page-2", "page-2"]
        assert len(ingestion.uploads) == 1


@pytest.mark.asyncio
async def test_shopify_webhook_is_verified_and_deduplicated(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'commerce-webhook.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        company = Company(
            name="Webhook",
            slug="webhook",
            email="webhook@example.com",
            country="Canada",
            timezone="America/Toronto",
            industry="Retail",
            subscription_plan="professional",
        )
        session.add(company)
        session.flush()
        connection = CommerceConnection(
            company_id=company.id,
            provider="shopify",
            external_account_id="hooks.myshopify.com",
            encrypted_credentials="unused-by-test",
            status=CommerceConnectionStatus.READY.value,
            capabilities=["orders"],
        )
        session.add(connection)
        session.commit()
        registry = CommerceConnectorRegistry()
        registry.register(
            ShopifyConnector(
                client_id="client-id",
                client_secret="webhook-secret",
                redirect_uri="https://api.test/callback",
                api_version="2026-07",
                scopes=("read_orders",),
                webhook_uri="https://api.test/webhook",
            )
        )
        service = CommerceSyncService(
            session,
            registry,
            _ConnectionLifecycle(connection),
            _RecordingIngestion(),
        )
        body = b'{"id": 123}'
        signature = base64.b64encode(
            hmac.new(b"webhook-secret", body, hashlib.sha256).digest()
        ).decode("ascii")
        headers = {
            "X-Shopify-Hmac-Sha256": signature,
            "X-Shopify-Webhook-Id": "delivery-1",
            "X-Shopify-Topic": "orders/create",
            "X-Shopify-Shop-Domain": "hooks.myshopify.com",
        }

        accepted = await service.accept_shopify_webhook(headers=headers, body=body)
        duplicate = await service.accept_shopify_webhook(headers=headers, body=body)

        deleted_body = b'{"id": 456}'
        deleted_headers = {
            "X-Shopify-Hmac-Sha256": base64.b64encode(
                hmac.new(
                    b"webhook-secret",
                    deleted_body,
                    hashlib.sha256,
                ).digest()
            ).decode("ascii"),
            "X-Shopify-Webhook-Id": "delivery-2",
            "X-Shopify-Topic": "orders/delete",
            "X-Shopify-Shop-Domain": "hooks.myshopify.com",
        }
        deleted = await service.accept_shopify_webhook(
            headers=deleted_headers,
            body=deleted_body,
        )

        receipts = session.scalars(select(CommerceWebhookReceipt)).all()
        assert len(receipts) == 2
        assert accepted.should_process is True
        assert duplicate.duplicate is True
        assert duplicate.should_process is False
        assert deleted.should_process is True
        receipts_by_id = {receipt.webhook_id: receipt for receipt in receipts}
        assert receipts_by_id["delivery-1"].payload_hash == hashlib.sha256(body).hexdigest()
        assert (
            receipts_by_id["delivery-2"].source_record_id
            == "gid://shopify/Order/456"
        )


@pytest.mark.asyncio
async def test_sync_tombstones_deleted_orders_before_rebuilding_snapshot(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'commerce-tombstone.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        company = Company(
            name="Tombstone",
            slug="tombstone",
            email="tombstone@example.com",
            country="Canada",
            timezone="America/Toronto",
            industry="Retail",
            subscription_plan="professional",
        )
        session.add(company)
        session.flush()
        connection = CommerceConnection(
            company_id=company.id,
            provider="shopify",
            external_account_id="tombstone.myshopify.com",
            encrypted_credentials="unused-by-test",
            status=CommerceConnectionStatus.READY.value,
            capabilities=["orders"],
            last_successful_sync=datetime.now(timezone.utc),
        )
        session.add(connection)
        session.flush()
        for number in (1, 2):
            source_id = f"gid://shopify/Order/{number}"
            session.add(
                NormalizedCommerceRecord(
                    company_id=company.id,
                    connection_id=connection.id,
                    provider="shopify",
                    entity_type="orders",
                    source_record_id=source_id,
                    normalized_data={
                        "shopify_order_gid": source_id,
                        "order_id": f"#{number}",
                        "order_timestamp": "2026-01-01T00:00:00Z",
                        "total_amount": "10.00",
                        "line_items": [
                            {
                                "shopify_line_item_gid": (
                                    f"gid://shopify/LineItem/{number}"
                                ),
                                "quantity": 1,
                                "unit_price": "10.00",
                            }
                        ],
                    },
                )
            )
        session.add(
            CommerceWebhookReceipt(
                company_id=company.id,
                connection_id=connection.id,
                provider="shopify",
                webhook_id="delete-order-1",
                topic="orders/delete",
                payload_hash="delete-order-1-hash",
                source_record_id="gid://shopify/Order/1",
                status="PROCESSING",
            )
        )
        session.commit()

        connector = _PagedShopifyConnector()
        registry = CommerceConnectorRegistry()
        registry.register(connector)
        ingestion = _RecordingIngestion()
        service = CommerceSyncService(
            session,
            registry,
            _ConnectionLifecycle(connection),
            ingestion,
        )

        await service.synchronize(TenantContext(company_id=company.id), connection.id)

        records = session.scalars(
            select(NormalizedCommerceRecord).order_by(
                NormalizedCommerceRecord.source_record_id
            )
        ).all()
        rows = list(
            csv.DictReader(io.StringIO(ingestion.uploads[0][1].decode("utf-8")))
        )
        assert records[0].deleted is True
        assert records[1].deleted is False
        assert [row["shopify_order_gid"] for row in rows] == [
            "gid://shopify/Order/2"
        ]


@pytest.mark.asyncio
async def test_last_deleted_order_removes_obsolete_retail_dataset(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'commerce-empty.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        company = Company(
            name="Empty",
            slug="empty",
            email="empty@example.com",
            country="Canada",
            timezone="America/Toronto",
            industry="Retail",
            subscription_plan="professional",
        )
        session.add(company)
        session.flush()
        ingestion = _RecordingIngestion()
        connection = CommerceConnection(
            company_id=company.id,
            provider="shopify",
            external_account_id="empty.myshopify.com",
            encrypted_credentials="unused-by-test",
            status=CommerceConnectionStatus.READY.value,
            capabilities=["orders"],
            last_successful_sync=datetime.now(timezone.utc),
            dataset_ids={"retail": str(ingestion.dataset_id)},
        )
        session.add(connection)
        session.flush()
        source_id = "gid://shopify/Order/1"
        session.add(
            NormalizedCommerceRecord(
                company_id=company.id,
                connection_id=connection.id,
                provider="shopify",
                entity_type="orders",
                source_record_id=source_id,
                normalized_data={
                    "shopify_order_gid": source_id,
                    "order_id": "#1",
                    "line_items": [{"quantity": 1, "unit_price": "10.00"}],
                },
            )
        )
        session.add(
            CommerceWebhookReceipt(
                company_id=company.id,
                connection_id=connection.id,
                provider="shopify",
                webhook_id="delete-last-order",
                topic="orders/delete",
                payload_hash="delete-last-order-hash",
                source_record_id=source_id,
                status="PROCESSING",
            )
        )
        session.commit()

        connector = _PagedShopifyConnector()
        registry = CommerceConnectorRegistry()
        registry.register(connector)
        service = CommerceSyncService(
            session,
            registry,
            _ConnectionLifecycle(connection),
            ingestion,
        )

        result = await service.synchronize(
            TenantContext(company_id=company.id),
            connection.id,
        )

        assert ingestion.uploads == []
        assert ingestion.deletions == [(company.id, ingestion.dataset_id)]
        assert "retail" not in connection.dataset_ids
        assert result.dataset_id is None
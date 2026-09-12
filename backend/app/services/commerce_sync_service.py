"""Commerce synchronization into the existing tenant data pipeline."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.connectors.shopify import (
    ShopifyAuthenticationError,
    ShopifyConnectorError,
    ShopifyTemporaryError,
)
from backend.app.connectors.woocommerce import (
    WooCommerceAuthenticationError,
    WooCommerceConnectorError,
    WooCommercePermissionError,
    WooCommerceRateLimitError,
    WooCommerceTemporaryError,
)
from backend.app.models import (
    CommerceConnection,
    CommerceConnectionStatus,
    CommerceRawSnapshot,
    CommerceWebhookReceipt,
    ConnectorDatasetEvaluation,
    Dataset,
    DatasetEvaluationStatus,
    DatasetVersion,
    NormalizedCommerceRecord,
)
from shared.ai_engine.connectors.commerce import (
    ConnectorCapability,
    ConnectorSyncContext,
)
from shared.ai_engine.connectors.registry import CommerceConnectorRegistry
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.dataset_ingestion.canonical_retail import (
    CanonicalRetailContext,
    project_canonical_retail,
)


class CommerceSyncError(RuntimeError):
    pass


class CommerceSyncDataError(CommerceSyncError):
    pass


class CommerceSyncAlreadyRunning(CommerceSyncError):
    pass


class _ConnectionLifecycle(Protocol):
    def get_connection(
        self, tenant: TenantContext, connection_id: UUID
    ) -> CommerceConnection: ...

    async def sync_context(
        self, tenant: TenantContext, connection_id: UUID
    ) -> ConnectorSyncContext: ...

    def mark_setup_complete(
        self, tenant: TenantContext, connection_id: UUID
    ) -> CommerceConnection: ...

    def mark_setup_degraded(
        self,
        tenant: TenantContext,
        connection_id: UUID,
        *,
        error_category: str,
    ) -> CommerceConnection: ...

    def mark_woocommerce_setup_failed(
        self,
        tenant: TenantContext,
        connection_id: UUID,
        *,
        error_category: str,
        reauth_required: bool = False,
    ) -> CommerceConnection: ...


class _DatasetIngestion(Protocol):
    def upload(
        self,
        tenant: TenantContext,
        module_code: str,
        filename: str,
        content: bytes,
    ) -> Dataset: ...

    def delete_if_exists(
        self,
        tenant: TenantContext,
        dataset_id: UUID,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class CommerceSyncResult:
    connection_id: UUID
    status: str
    records_processed: int
    dataset_id: UUID | None
    initial_sync: bool


@dataclass(frozen=True, slots=True)
class CommerceWebhookAcceptance:
    receipt_id: UUID | None
    connection_id: UUID | None
    tenant_id: UUID | None
    topic: str
    duplicate: bool
    should_process: bool


@dataclass(frozen=True, slots=True)
class _UpsertStats:
    processed: int
    changed: int


@dataclass(frozen=True, slots=True)
class _SyncRun:
    started_at: datetime
    updated_since: str | None
    state: dict[str, Any]


class CommerceSyncService:
    """Persist provider pages and hand one stable snapshot to Retail ingestion."""

    _ACTIVE_SYNC_TIMEOUT = timedelta(minutes=3)
    _SHOPIFY_DELETION_RESOURCES = {
        "orders/delete": ("orders", "Order"),
        "products/delete": ("products", "Product"),
        "customers/delete": ("customers", "Customer"),
        "inventory_items/delete": ("inventory", "InventoryItem"),
    }
    _WOOCOMMERCE_DELETION_RESOURCES = {
        "order.deleted": "orders",
        "product.deleted": "products",
        "customer.deleted": "customers",
    }
    _ENTITY_SPECS = (
        ("orders", ConnectorCapability.ORDERS, "sync_orders"),
        ("customers", ConnectorCapability.CUSTOMERS, "sync_customers"),
        ("products", ConnectorCapability.PRODUCTS, "sync_products"),
        ("inventory", ConnectorCapability.INVENTORY, "sync_inventory"),
        ("refunds", ConnectorCapability.REFUNDS, "sync_refunds"),
    )
    _SNAPSHOT_FIELDS = (
        "product_name",
        "product_id",
        "sku",
        "unit_price",
        "inventory_level",
        "product_category",
        "order_id",
        "order_timestamp",
        "quantity",
        "total_amount",
        "currency",
        "fulfillment_status",
        "customer_id",
        "customer_email",
        "customer_country",
        "discount_amount",
        "refund_amount",
        "sales_channel",
        "source_updated_at",
        "source_provider",
        "source_store",
        "source_connection_id",
        "source_order_id",
        "source_line_item_id",
        "shopify_order_gid",
        "shopify_line_item_gid",
    )

    def __init__(
        self,
        db: Session,
        registry: CommerceConnectorRegistry,
        connections: _ConnectionLifecycle,
        ingestion: _DatasetIngestion,
        evaluation_debounce_seconds: int = 300,
    ) -> None:
        self._db = db
        self._registry = registry
        self._connections = connections
        self._ingestion = ingestion
        self._evaluation_debounce_seconds = evaluation_debounce_seconds

    async def initialize_woocommerce(
        self,
        tenant: TenantContext,
        connection_id: UUID,
    ) -> CommerceSyncResult:
        connection = self._connections.get_connection(tenant, connection_id)
        if connection.provider != "woocommerce":
            raise CommerceSyncDataError("Connection is not a WooCommerce connection")
        context = await self._connections.sync_context(tenant, connection_id)
        connector = self._registry.get("woocommerce")
        try:
            if not await connector.test_connection(context):
                raise WooCommerceAuthenticationError(
                    "WooCommerce connection validation failed"
                )
        except WooCommerceAuthenticationError as exc:
            self._connections.mark_woocommerce_setup_failed(
                tenant,
                connection_id,
                error_category="authorization_failed",
                reauth_required=True,
            )
            raise CommerceSyncError("WooCommerce credential validation failed") from exc
        except WooCommerceConnectorError as exc:
            self._connections.mark_woocommerce_setup_failed(
                tenant,
                connection_id,
                error_category=(
                    "insufficient_permissions"
                    if isinstance(exc, WooCommercePermissionError)
                    else "connection_validation_failed"
                ),
            )
            raise CommerceSyncError("WooCommerce credential validation failed") from exc
        try:
            await connector.register_webhooks(context)
        except Exception as exc:
            self._connections.mark_setup_degraded(
                tenant,
                connection_id,
                error_category="webhook_registration_failed",
            )
            raise CommerceSyncError("WooCommerce webhook initialization failed") from exc
        self._connections.mark_setup_complete(tenant, connection_id)
        self.reserve(tenant, connection_id)
        return await self.synchronize(tenant, connection_id, reserved=True)

    async def synchronize(
        self,
        tenant: TenantContext,
        connection_id: UUID,
        *,
        reserved: bool = False,
    ) -> CommerceSyncResult:
        connection = self._connections.get_connection(tenant, connection_id)
        if self._is_active_sync(connection) and not reserved:
            raise CommerceSyncAlreadyRunning("Commerce synchronization is already running")
        connector = self._registry.get(connection.provider)
        run = self._begin_or_resume(connection)
        changed = 0

        try:
            base_context = await self._connections.sync_context(tenant, connection_id)
            configured_capabilities = set(
                connection.capabilities
                or (capability.value for capability in connector.definition.capabilities)
            )
            for entity_type, capability, method_name in self._ENTITY_SPECS:
                if capability.value not in configured_capabilities:
                    continue
                entity_state = dict(run.state.get(entity_type) or {})
                if entity_state.get("completed") is True:
                    continue
                connection.current_entity = entity_type
                self._db.commit()
                cursor = self._optional_text(entity_state.get("next_cursor"))
                method = getattr(connector, method_name)
                while True:
                    page = await method(
                        replace(
                            base_context,
                            cursor=cursor,
                            updated_since=run.updated_since,
                        )
                    )
                    stats = self._upsert_records(
                        tenant,
                        connection,
                        entity_type,
                        page.records,
                    )
                    next_cursor = page.next_cursor
                    if next_cursor is not None and next_cursor == cursor:
                        raise CommerceSyncDataError(
                            f"Provider repeated the {entity_type} cursor"
                        )
                    entity_state = {
                        "next_cursor": next_cursor,
                        "completed": next_cursor is None,
                    }
                    run.state[entity_type] = entity_state
                    conn_mods = list((connection.sync_cursor or {}).get("modifications") or [])
                    if conn_mods:
                        run.state["modifications"] = conn_mods
                    connection.sync_cursor = dict(run.state)
                    connection.records_processed += stats.processed
                    connection.records_created = (connection.records_created or 0) + stats.changed
                    connection.last_heartbeat = self._now()
                    changed += stats.changed
                    self._db.commit()
                    if next_cursor is None:
                        break
                    cursor = next_cursor

            changed += self._apply_pending_tombstones(tenant, connection)
            connection.status = CommerceConnectionStatus.PROCESSING.value
            connection.current_entity = "retail_snapshot"
            connection.last_heartbeat = self._now()
            existing_dataset_id = self._dataset_id(connection)
            snapshot_pending = bool(run.state.get("_snapshot_pending"))
            should_materialize = changed > 0 or existing_dataset_id is None or snapshot_pending
            if should_materialize:
                existing_mods = list(
                    (connection.sync_cursor or {}).get("modifications") or []
                )
                run.state["_snapshot_pending"] = True
                if existing_mods:
                    run.state["modifications"] = existing_mods
                connection.sync_cursor = dict(run.state)
            self._db.commit()

            dataset = None
            if should_materialize:
                dataset = self._materialize_retail_snapshot(
                    tenant,
                    connection,
                    changed_records=changed,
                )
                if dataset is not None:
                    connection.dataset_ids = {
                        **dict(connection.dataset_ids or {}),
                        "retail": str(dataset.id),
                    }

            now_completed = self._now()
            connection.status = CommerceConnectionStatus.READY.value
            connection.current_entity = None
            connection.error_category = None
            connection.last_successful_sync = run.started_at
            connection.sync_started_at = None
            connection.sync_completed_at = now_completed
            connection.last_heartbeat = now_completed
            connection.sync_error_code = None
            connection.sync_error_message = None
            final_mods = list((connection.sync_cursor or {}).get("modifications") or [])
            connection.sync_cursor = {
                "checkpoint": {"updated_since": self._isoformat(run.started_at)},
                "modifications": final_mods,
            }
            self._db.commit()
            return CommerceSyncResult(
                connection_id=connection.id,
                status=connection.status,
                records_processed=connection.records_processed,
                dataset_id=(
                    dataset.id if dataset is not None else self._dataset_id(connection)
                ),
                initial_sync=run.updated_since is None,
            )
        except Exception as exc:
            self._db.rollback()
            connection = self._connections.get_connection(tenant, connection_id)
            error_category = self._error_category(exc)
            now_failed = self._now()
            connection.status = (
                CommerceConnectionStatus.REAUTH_REQUIRED.value
                if error_category == "reauthorization_required"
                else CommerceConnectionStatus.FAILED.value
            )
            connection.error_category = error_category
            connection.sync_started_at = None
            connection.sync_failed_at = now_failed
            connection.last_heartbeat = now_failed
            connection.sync_error_code = getattr(exc, "code", type(exc).__name__)
            connection.sync_error_message = str(exc)
            self._db.commit()
            if isinstance(exc, CommerceSyncError):
                raise
            raise CommerceSyncError("Commerce synchronization failed") from exc

    def reserve(
        self,
        tenant: TenantContext,
        connection_id: UUID,
    ) -> None:
        connection = self._db.scalar(
            select(CommerceConnection)
            .where(
                CommerceConnection.id == connection_id,
                CommerceConnection.company_id == tenant.company_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if connection is None:
            self._connections.get_connection(tenant, connection_id)
            raise CommerceSyncDataError("Commerce connection not found")
        if self._is_active_sync(connection):
            raise CommerceSyncAlreadyRunning("Commerce synchronization is already running")
        self._begin_or_resume(connection)

    def is_active(
        self,
        tenant: TenantContext,
        connection_id: UUID,
    ) -> bool:
        return self._is_active_sync(
            self._connections.get_connection(tenant, connection_id)
        )

    async def accept_shopify_webhook(
        self,
        *,
        headers: Mapping[str, str],
        body: bytes,
    ) -> CommerceWebhookAcceptance:
        normalized_headers = {str(key).lower(): str(value) for key, value in headers.items()}
        webhook_id = self._required_header(normalized_headers, "x-shopify-webhook-id")
        topic = self._required_header(normalized_headers, "x-shopify-topic")
        shop = self._required_header(normalized_headers, "x-shopify-shop-domain")
        if len(webhook_id) > 255 or len(topic) > 120:
            raise CommerceSyncDataError("Shopify webhook metadata is invalid")

        connector = self._registry.get("shopify")
        normalized_shop = shop.strip().lower()
        connection = self._db.scalar(
            select(CommerceConnection).where(
                CommerceConnection.provider == "shopify",
                CommerceConnection.external_account_id == normalized_shop,
            )
        )
        tenant_id = connection.company_id if connection is not None else UUID(int=0)
        payload = await connector.handle_webhook(
            tenant_id=tenant_id,
            headers=normalized_headers,
            body=body,
        )
        if connection is None:
            return CommerceWebhookAcceptance(
                receipt_id=None,
                connection_id=None,
                tenant_id=None,
                topic=topic,
                duplicate=False,
                should_process=False,
            )

        payload_hash = hashlib.sha256(body).hexdigest()
        source_record_id = self._shopify_deleted_record_id(topic, payload)
        existing = self._db.scalar(
            select(CommerceWebhookReceipt).where(
                CommerceWebhookReceipt.provider == "shopify",
                CommerceWebhookReceipt.webhook_id == webhook_id,
            )
        )
        if existing is not None:
            if existing.payload_hash != payload_hash:
                raise CommerceSyncDataError("Shopify webhook identifier was reused")
            return CommerceWebhookAcceptance(
                receipt_id=existing.id,
                connection_id=existing.connection_id,
                tenant_id=existing.company_id,
                topic=existing.topic,
                duplicate=True,
                should_process=existing.status == "ERROR",
            )

        receipt = CommerceWebhookReceipt(
            company_id=connection.company_id,
            connection_id=connection.id,
            provider="shopify",
            webhook_id=webhook_id,
            topic=topic,
            payload_hash=payload_hash,
            source_record_id=source_record_id,
        )
        self._db.add(receipt)
        try:
            self._db.commit()
        except IntegrityError:
            self._db.rollback()
            existing = self._db.scalar(
                select(CommerceWebhookReceipt).where(
                    CommerceWebhookReceipt.provider == "shopify",
                    CommerceWebhookReceipt.webhook_id == webhook_id,
                )
            )
            if existing is None or existing.payload_hash != payload_hash:
                raise CommerceSyncDataError("Shopify webhook could not be recorded")
            return CommerceWebhookAcceptance(
                receipt_id=existing.id,
                connection_id=existing.connection_id,
                tenant_id=existing.company_id,
                topic=existing.topic,
                duplicate=True,
                should_process=existing.status == "ERROR",
            )
        return CommerceWebhookAcceptance(
            receipt_id=receipt.id,
            connection_id=connection.id,
            tenant_id=connection.company_id,
            topic=topic,
            duplicate=False,
            should_process=True,
        )

    async def accept_woocommerce_webhook(
        self,
        *,
        connection_id: UUID,
        headers: Mapping[str, str],
        body: bytes,
    ) -> CommerceWebhookAcceptance:
        normalized_headers = {
            str(key).lower(): str(value) for key, value in headers.items()
        }
        delivery_id = self._required_header(
            normalized_headers,
            "x-wc-webhook-delivery-id",
            provider="WooCommerce",
        )
        topic = self._required_header(
            normalized_headers,
            "x-wc-webhook-topic",
            provider="WooCommerce",
        )
        if len(delivery_id) > 255 or len(topic) > 120:
            raise CommerceSyncDataError("WooCommerce webhook metadata is invalid")
        connection = self._db.scalar(
            select(CommerceConnection).where(
                CommerceConnection.id == connection_id,
                CommerceConnection.provider == "woocommerce",
                CommerceConnection.status
                != CommerceConnectionStatus.DISCONNECTED.value,
            )
        )
        if connection is None:
            return CommerceWebhookAcceptance(
                receipt_id=None,
                connection_id=None,
                tenant_id=None,
                topic=topic,
                duplicate=False,
                should_process=False,
            )
        tenant = TenantContext(company_id=connection.company_id)
        context = await self._connections.sync_context(tenant, connection.id)
        connector = self._registry.get("woocommerce")
        payload = await connector.handle_webhook(
            tenant_id=tenant.company_id,
            headers=normalized_headers,
            body=body,
            credentials=context.credentials,
        )
        payload_hash = hashlib.sha256(body).hexdigest()
        source_record_id = self._woocommerce_deleted_record_id(topic, payload)
        existing = self._db.scalar(
            select(CommerceWebhookReceipt).where(
                CommerceWebhookReceipt.provider == "woocommerce",
                CommerceWebhookReceipt.webhook_id == delivery_id,
            )
        )
        if existing is not None:
            if existing.payload_hash != payload_hash:
                raise CommerceSyncDataError(
                    "WooCommerce webhook identifier was reused"
                )
            return CommerceWebhookAcceptance(
                receipt_id=existing.id,
                connection_id=existing.connection_id,
                tenant_id=existing.company_id,
                topic=existing.topic,
                duplicate=True,
                should_process=existing.status == "ERROR",
            )
        receipt = CommerceWebhookReceipt(
            company_id=connection.company_id,
            connection_id=connection.id,
            provider="woocommerce",
            webhook_id=delivery_id,
            topic=topic,
            payload_hash=payload_hash,
            source_record_id=source_record_id,
        )
        self._db.add(receipt)
        try:
            self._db.commit()
        except IntegrityError:
            self._db.rollback()
            existing = self._db.scalar(
                select(CommerceWebhookReceipt).where(
                    CommerceWebhookReceipt.provider == "woocommerce",
                    CommerceWebhookReceipt.webhook_id == delivery_id,
                )
            )
            if existing is None or existing.payload_hash != payload_hash:
                raise CommerceSyncDataError(
                    "WooCommerce webhook could not be recorded"
                )
            return CommerceWebhookAcceptance(
                receipt_id=existing.id,
                connection_id=existing.connection_id,
                tenant_id=existing.company_id,
                topic=existing.topic,
                duplicate=True,
                should_process=existing.status == "ERROR",
            )
        return CommerceWebhookAcceptance(
            receipt_id=receipt.id,
            connection_id=connection.id,
            tenant_id=connection.company_id,
            topic=topic,
            duplicate=False,
            should_process=True,
        )

    @classmethod
    def _woocommerce_deleted_record_id(
        cls,
        topic: str,
        payload: Mapping[str, Any],
    ) -> str | None:
        if topic.strip().lower() not in cls._WOOCOMMERCE_DELETION_RESOURCES:
            return None
        value = str(payload.get("id") or "").strip()
        if not value or len(value) > 255:
            raise CommerceSyncDataError(
                "WooCommerce deletion webhook resource is invalid"
            )
        return value

    @classmethod
    def _shopify_deleted_record_id(
        cls,
        topic: str,
        payload: Mapping[str, Any],
    ) -> str | None:
        resource = cls._SHOPIFY_DELETION_RESOURCES.get(topic.strip().lower())
        if resource is None:
            return None
        _, resource_type = resource
        raw_id = payload.get("admin_graphql_api_id") or payload.get("id")
        value = str(raw_id or "").strip()
        expected_prefix = f"gid://shopify/{resource_type}/"
        if value.isdigit():
            value = f"{expected_prefix}{value}"
        if not value.startswith(expected_prefix) or len(value) > 255:
            raise CommerceSyncDataError("Shopify deletion webhook resource is invalid")
        return value

    def _apply_pending_tombstones(
        self,
        tenant: TenantContext,
        connection: CommerceConnection,
    ) -> int:
        receipts = self._db.scalars(
            select(CommerceWebhookReceipt).where(
                CommerceWebhookReceipt.company_id == tenant.company_id,
                CommerceWebhookReceipt.connection_id == connection.id,
                CommerceWebhookReceipt.status.in_(("RECEIVED", "PROCESSING")),
                CommerceWebhookReceipt.source_record_id.is_not(None),
            )
        ).all()
        targets: set[tuple[str, str]] = set()
        for receipt in receipts:
            if receipt.provider == "shopify":
                resource = self._SHOPIFY_DELETION_RESOURCES.get(
                    receipt.topic.strip().lower()
                )
                if resource is not None:
                    targets.add((resource[0], str(receipt.source_record_id)))
            elif receipt.provider == "woocommerce":
                entity_type = self._WOOCOMMERCE_DELETION_RESOURCES.get(
                    receipt.topic.strip().lower()
                )
                if entity_type is not None:
                    targets.add((entity_type, str(receipt.source_record_id)))
        if not targets:
            return 0
        records = self._db.scalars(
            select(NormalizedCommerceRecord).where(
                NormalizedCommerceRecord.company_id == tenant.company_id,
                NormalizedCommerceRecord.connection_id == connection.id,
                NormalizedCommerceRecord.source_record_id.in_(
                    {source_record_id for _, source_record_id in targets}
                ),
            )
        ).all()
        changed = 0
        for record in records:
            if (
                (record.entity_type, record.source_record_id) in targets
                and not record.deleted
            ):
                record.deleted = True
                changed += 1
        self._db.flush()
        return changed

    def _begin_or_resume(self, connection: CommerceConnection) -> _SyncRun:
        state = dict(connection.sync_cursor or {})
        legacy_snapshot_pending = (
            connection.status == CommerceConnectionStatus.ERROR.value
            and connection.current_entity == "retail_snapshot"
        )
        active = state.get("_run")
        if isinstance(active, dict):
            started_at = self._parse_datetime(active.get("started_at")) or self._now()
            updated_since = self._optional_text(active.get("updated_since"))
        else:
            started_at = self._now()
            updated_since = (
                self._isoformat(connection.last_successful_sync)
                if connection.last_successful_sync is not None
                else None
            )
            prior_mods = list((connection.sync_cursor or {}).get("modifications") or [])
            state = {
                "_run": {
                    "started_at": self._isoformat(started_at),
                    "updated_since": updated_since,
                }
            }
            if prior_mods:
                state["modifications"] = prior_mods
            connection.records_processed = 0
            connection.records_created = 0
            connection.records_updated = 0
            connection.records_failed = 0
        if legacy_snapshot_pending:
            state["_snapshot_pending"] = True
        sync_run_id = uuid4().hex
        connection.sync_run_id = sync_run_id
        connection.status = CommerceConnectionStatus.SYNCING.value
        connection.sync_started_at = started_at
        connection.last_heartbeat = started_at
        connection.sync_completed_at = None
        connection.sync_failed_at = None
        connection.sync_error_code = None
        connection.sync_error_message = None
        connection.current_entity = "connecting"
        connection.error_category = None
        connection.sync_cursor = dict(state)
        self._db.commit()
        return _SyncRun(started_at, updated_since, state)

    def _upsert_records(
        self,
        tenant: TenantContext,
        connection: CommerceConnection,
        entity_type: str,
        records: tuple[Mapping[str, Any], ...],
    ) -> _UpsertStats:
        if connection.company_id != tenant.company_id:
            raise CommerceSyncDataError("Commerce connection tenant mismatch")
        normalized_by_id: dict[
            str, tuple[dict[str, Any], datetime | None, dict[str, Any], str]
        ] = {}
        for raw_record in records:
            source_record_id = self._optional_text(raw_record.get("id"))
            if source_record_id is None:
                raise CommerceSyncDataError(
                    f"Provider returned {entity_type} data without an id"
                )
            raw_payload = dict(raw_record)
            payload_hash = hashlib.sha256(
                json.dumps(raw_payload, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()
            normalized_by_id[source_record_id] = (
                self._normalize_provider(connection.provider, entity_type, raw_record),
                self._source_updated_at(raw_record),
                raw_payload,
                payload_hash,
            )
        if not normalized_by_id:
            return _UpsertStats(processed=0, changed=0)

        existing_records = self._db.scalars(
            select(NormalizedCommerceRecord).where(
                NormalizedCommerceRecord.company_id == tenant.company_id,
                NormalizedCommerceRecord.connection_id == connection.id,
                NormalizedCommerceRecord.entity_type == entity_type,
                NormalizedCommerceRecord.source_record_id.in_(normalized_by_id),
            )
        ).all()
        existing_by_id = {item.source_record_id: item for item in existing_records}
        changed = 0
        for source_record_id, (
            normalized,
            source_updated_at,
            raw_payload,
            payload_hash,
        ) in normalized_by_id.items():
            snapshot = self._db.scalar(
                select(CommerceRawSnapshot).where(
                    CommerceRawSnapshot.connection_id == connection.id,
                    CommerceRawSnapshot.entity_type == entity_type,
                    CommerceRawSnapshot.source_record_id == source_record_id,
                    CommerceRawSnapshot.payload_hash == payload_hash,
                )
            )
            if snapshot is None:
                snapshot = CommerceRawSnapshot(
                    company_id=tenant.company_id,
                    connection_id=connection.id,
                    provider=connection.provider,
                    entity_type=entity_type,
                    source_record_id=source_record_id,
                    payload_hash=payload_hash,
                    raw_payload=raw_payload,
                    source_updated_at=source_updated_at,
                )
                self._db.add(snapshot)
                self._db.flush()
            stored = existing_by_id.get(source_record_id)
            if stored is None:
                self._db.add(
                    NormalizedCommerceRecord(
                        company_id=tenant.company_id,
                        connection_id=connection.id,
                        provider=connection.provider,
                        entity_type=entity_type,
                        source_record_id=source_record_id,
                        source_updated_at=source_updated_at,
                        source_snapshot_id=snapshot.id,
                        normalized_data=normalized,
                    )
                )
                changed += 1
                continue
            if (
                stored.source_updated_at is not None
                and source_updated_at is not None
                and self._as_utc(source_updated_at)
                < self._as_utc(stored.source_updated_at)
            ):
                continue
            if (
                stored.normalized_data == normalized
                and stored.source_snapshot_id == snapshot.id
                and self._same_datetime(stored.source_updated_at, source_updated_at)
                and not stored.deleted
            ):
                continue
            if stored.normalized_data != normalized:
                old_data = dict(stored.normalized_data or {})
                new_data = dict(normalized or {})
                cursor = dict(connection.sync_cursor or {})
                mods = list(cursor.get("modifications") or [])
                now_str = datetime.now(timezone.utc).isoformat()
                entity_label = (
                    new_data.get("product_name")
                    or old_data.get("product_name")
                    or new_data.get("order_id")
                    or f"{entity_type.title()} {source_record_id}"
                )
                for f_key in (
                    "inventory_level",
                    "stock_quantity",
                    "unit_price",
                    "regular_price",
                    "price",
                    "fulfillment_status",
                    "status",
                ):
                    old_v = old_data.get(f_key)
                    new_v = new_data.get(f_key)
                    if (
                        old_v is not None
                        and new_v is not None
                        and str(old_v) != str(new_v)
                    ):
                        diff_badge = ""
                        try:
                            num_delta = float(new_v) - float(old_v)
                            if num_delta.is_integer():
                                diff_badge = (
                                    f"+{int(num_delta)}"
                                    if num_delta > 0
                                    else str(int(num_delta))
                                )
                            else:
                                diff_badge = (
                                    f"+{num_delta:.2f}"
                                    if num_delta > 0
                                    else f"{num_delta:.2f}"
                                )
                        except Exception:
                            pass
                        col_disp = (
                            "stock_quantity"
                            if f_key in ("inventory_level", "stock_quantity")
                            else f_key
                        )
                        mods.append(
                            {
                                "row_id": str(source_record_id),
                                "entity": entity_label,
                                "column": col_disp,
                                "before": str(old_v),
                                "after": str(new_v),
                                "reason": f"Synchronisation {connection.provider.title()}",
                                "source": connection.provider.title(),
                                "timestamp": now_str,
                                "diff": diff_badge,
                                "rule": "Mise à jour connecteur e-commerce",
                                "category": "changed",
                            }
                        )
                cursor["modifications"] = mods[-200:]
                connection.sync_cursor = cursor

            stored.provider = connection.provider
            stored.source_updated_at = source_updated_at
            stored.source_snapshot_id = snapshot.id
            stored.normalized_data = normalized
            stored.deleted = False
            changed += 1
        self._db.flush()
        return _UpsertStats(processed=len(records), changed=changed)

    def _materialize_retail_snapshot(
        self,
        tenant: TenantContext,
        connection: CommerceConnection,
        *,
        changed_records: int = 0,
    ) -> Dataset | None:
        content = self.build_retail_snapshot(tenant, connection)
        if content is None:
            dataset_id = self._dataset_id(connection)
            if dataset_id is not None:
                self._ingestion.delete_if_exists(tenant, dataset_id)
                dataset_ids = dict(connection.dataset_ids or {})
                dataset_ids.pop("retail", None)
                connection.dataset_ids = dataset_ids
            return None
        dataset = self._ingestion.upload(
            tenant,
            "retail",
            f"{connection.provider}-{connection.id}-retail.csv",
            content,
        )
        save_canonical = getattr(self._ingestion, "save_canonical_entities", None)
        if callable(save_canonical):
            canonical = self._canonical_retail_dataset(tenant, connection)
            save_canonical(tenant, dataset, canonical.entities)

        # Merge modifications from connection.sync_cursor into dataset metadata
        try:
            get_vn = getattr(self._ingestion, "_current_version_number", None)
            storage = getattr(self._ingestion, "_storage", None)
            if callable(get_vn) and storage is not None:
                version_number = get_vn(dataset)
                meta_path = storage.metadata_path(
                    tenant.company_id, dataset.id, version_number
                )
                if meta_path.is_file():
                    mdata = json.loads(meta_path.read_text(encoding="utf-8"))
                    existing_mods = list(mdata.get("modifications") or [])
                    conn_mods = list(
                        (connection.sync_cursor or {}).get("modifications") or []
                    )
                    merged_mods = conn_mods + existing_mods
                    seen_mods = set()
                    deduped_mods = []
                    for m in merged_mods:
                        mk = (
                            m.get("entity"),
                            m.get("column"),
                            m.get("before"),
                            m.get("after"),
                            m.get("timestamp"),
                        )
                        if mk not in seen_mods:
                            seen_mods.add(mk)
                            deduped_mods.append(m)
                    mdata["modifications"] = deduped_mods
                    meta_path.write_text(
                        json.dumps(mdata, indent=2, default=str), encoding="utf-8"
                    )
        except Exception:
            pass
        current_version = self._db.scalar(
            select(DatasetVersion).where(
                DatasetVersion.dataset_id == dataset.id,
                DatasetVersion.is_current.is_(True),
            )
        )
        if current_version is None:
            return dataset
        existing = self._db.scalar(
            select(ConnectorDatasetEvaluation.id).where(
                ConnectorDatasetEvaluation.company_id == tenant.company_id,
                ConnectorDatasetEvaluation.connection_id == connection.id,
                ConnectorDatasetEvaluation.dataset_id == dataset.id,
                ConnectorDatasetEvaluation.dataset_generation
                == current_version.version_number,
            )
        )
        if existing is None:
            now = datetime.now(timezone.utc)
            debounce_seconds = (
                0
                if current_version.version_number == 1
                else self._evaluation_debounce_seconds
            )
            self._db.add(
                ConnectorDatasetEvaluation(
                    company_id=tenant.company_id,
                    connection_id=connection.id,
                    dataset_id=dataset.id,
                    dataset_generation=current_version.version_number,
                    changed_records=max(0, changed_records),
                    status=DatasetEvaluationStatus.PENDING,
                    due_at=now + timedelta(seconds=debounce_seconds),
                )
            )
            self._db.commit()
        return dataset

    def _canonical_retail_dataset(
        self,
        tenant: TenantContext,
        connection: CommerceConnection,
    ):
        records = self._db.scalars(
            select(NormalizedCommerceRecord).where(
                NormalizedCommerceRecord.company_id == tenant.company_id,
                NormalizedCommerceRecord.connection_id == connection.id,
                NormalizedCommerceRecord.deleted.is_(False),
            )
        ).all()
        normalized_by_entity: dict[str, list[dict[str, Any]]] = {}
        for record in records:
            normalized_by_entity.setdefault(record.entity_type, []).append(
                dict(record.normalized_data or {})
            )
        context = CanonicalRetailContext(
            tenant_id=tenant.company_id,
            company_id=tenant.company_id,
            source_id=connection.id,
            source_provider=connection.provider,
            store_id=connection.external_account_id,
        )
        return project_canonical_retail(context, normalized_by_entity)

    def build_retail_snapshot(
        self,
        tenant: TenantContext,
        connection: CommerceConnection,
    ) -> bytes | None:
        if connection.company_id != tenant.company_id:
            raise CommerceSyncDataError("Commerce connection tenant mismatch")
        records = self._db.scalars(
            select(NormalizedCommerceRecord)
            .where(
                NormalizedCommerceRecord.company_id == tenant.company_id,
                NormalizedCommerceRecord.connection_id == connection.id,
                NormalizedCommerceRecord.deleted.is_(False),
            )
            .order_by(
                NormalizedCommerceRecord.entity_type,
                NormalizedCommerceRecord.source_record_id,
            )
        ).all()
        rows = self._snapshot_rows(connection, records)
        if not rows:
            return None
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=self._SNAPSHOT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
        return buffer.getvalue().encode("utf-8")

    def _snapshot_rows(
        self,
        connection: CommerceConnection,
        records: list[NormalizedCommerceRecord],
    ) -> list[dict[str, Any]]:
        data_by_entity: dict[str, list[dict[str, Any]]] = {}
        for record in records:
            data_by_entity.setdefault(record.entity_type, []).append(
                dict(record.normalized_data or {})
            )

        customers = {
            str(item.get("customer_id")): item
            for item in data_by_entity.get("customers", [])
            if item.get("customer_id")
        }
        variants: dict[str, dict[str, Any]] = {}
        for product in data_by_entity.get("products", []):
            for variant in product.get("variants") or ():
                if not isinstance(variant, dict):
                    continue
                enriched = {
                    **variant,
                    "product_name": product.get("product_name"),
                    "product_category": product.get("product_category"),
                }
                for key in (variant.get("variant_id"), variant.get("sku")):
                    if key:
                        variants[str(key)] = enriched
        inventory: dict[str, dict[str, Any]] = {}
        for item in data_by_entity.get("inventory", []):
            for key in (item.get("inventory_item_id"), item.get("sku")):
                if key:
                    inventory[str(key)] = item

        refunded_quantities: dict[tuple[str, str], int] = {}
        refunded_amounts: dict[tuple[str, str], Decimal] = {}
        priced_refunds: set[tuple[str, str]] = set()
        for refund in data_by_entity.get("refunds", []):
            order_id = str(
                refund.get("source_order_id")
                or refund.get("shopify_order_gid")
                or ""
            )
            for line in refund.get("line_items") or ():
                if not isinstance(line, dict):
                    continue
                line_id = line.get("source_line_item_id") or line.get(
                    "shopify_line_item_gid"
                )
                if not line_id:
                    continue
                key = (order_id, str(line_id))
                refunded_quantities[key] = refunded_quantities.get(key, 0) + self._integer(
                    line.get("quantity")
                )
                raw_amount = line.get("refund_amount")
                if raw_amount is not None and str(raw_amount).strip():
                    refunded_amounts[key] = refunded_amounts.get(
                        key, Decimal("0")
                    ) + self._decimal(raw_amount)
                    priced_refunds.add(key)

        rows: list[dict[str, Any]] = []
        referenced_customers: set[str] = set()
        referenced_products: set[str] = set()
        for order in data_by_entity.get("orders", []):
            lines = [
                item
                for item in order.get("line_items") or ()
                if isinstance(item, dict)
            ]
            if not lines:
                continue
            allocations = self._allocate_total(order.get("total_amount"), lines)
            customer = customers.get(str(order.get("customer_id") or ""), {})
            if order.get("customer_id"):
                referenced_customers.add(str(order["customer_id"]))
            for index, line in enumerate(lines):
                variant = variants.get(str(line.get("variant_id") or "")) or variants.get(
                    str(line.get("sku") or "")
                ) or {}
                stock = inventory.get(str(variant.get("inventory_item_id") or "")) or inventory.get(
                    str(line.get("sku") or "")
                ) or {}
                quantity = self._integer(line.get("quantity"))
                refund_key = (
                    str(
                        order.get("source_order_id")
                        or order.get("shopify_order_gid")
                        or ""
                    ),
                    str(
                        line.get("source_line_item_id")
                        or line.get("shopify_line_item_gid")
                        or ""
                    ),
                )
                refunded = refunded_quantities.get(refund_key, 0)
                product_id = (
                    line.get("sku")
                    or line.get("variant_id")
                    or line.get("product_id")
                    or line.get("shopify_line_item_gid")
                    or ""
                )
                identity_keys = (line.get("variant_id"), line.get("sku"))
                if not any(identity_keys):
                    identity_keys = (line.get("product_id"),)
                for key in identity_keys:
                    if key:
                        referenced_products.add(str(key))
                refund_amount = (
                    refunded_amounts[refund_key]
                    if refund_key in priced_refunds
                    else self._decimal(line.get("unit_price"))
                    * min(quantity, refunded)
                )
                rows.append(
                    {
                        "source_provider": connection.provider,
                        "source_connection_id": str(connection.id),
                        "source_store": connection.external_account_id,
                        "source_order_id": order.get("source_order_id") or "",
                        "source_line_item_id": line.get("source_line_item_id") or "",
                        "shopify_order_gid": order.get("shopify_order_gid") or "",
                        "shopify_line_item_gid": line.get("shopify_line_item_gid") or "",
                        "order_id": order.get("order_id") or "",
                        "order_timestamp": order.get("order_timestamp") or "",
                        "customer_id": order.get("customer_id") or "",
                        "product_id": product_id,
                        "product_name": line.get("product_name")
                        or variant.get("product_name")
                        or "",
                        "product_category": line.get("product_category")
                        or variant.get("product_category")
                        or "",
                        "quantity": quantity,
                        "unit_price": line.get("unit_price") or "0",
                        "total_amount": self._decimal_text(allocations[index]),
                        "inventory_level": stock.get("inventory_level")
                        if stock
                        else line.get("inventory_level", ""),
                        "currency": order.get("currency") or "",
                        "discount_amount": line.get("discount_amount") or "0",
                        "refund_amount": self._decimal_text(refund_amount),
                        "fulfillment_status": order.get("fulfillment_status") or "",
                        "sales_channel": order.get("sales_channel") or "",
                        "customer_email": order.get("customer_email")
                        or customer.get("email")
                        or "",
                        "customer_country": order.get("customer_country")
                        or customer.get("country")
                        or "",
                        "source_updated_at": order.get("updated_at") or "",
                    }
                )

        for customer_id, customer in customers.items():
            if customer_id in referenced_customers:
                continue
            rows.append(
                {
                    "source_provider": connection.provider,
                    "source_connection_id": str(connection.id),
                    "source_store": connection.external_account_id,
                    "customer_id": customer_id,
                    "customer_email": customer.get("email") or "",
                    "customer_country": customer.get("country") or "",
                    "source_updated_at": customer.get("updated_at") or "",
                }
            )

        for product in data_by_entity.get("products", []):
            product_variants = [
                variant
                for variant in product.get("variants") or ()
                if isinstance(variant, dict)
            ] or [{}]
            for variant in product_variants:
                identity_values = (variant.get("variant_id"), variant.get("sku"))
                if not any(identity_values):
                    identity_values = (product.get("product_id"),)
                identifiers = {str(value) for value in identity_values if value}
                if identifiers & referenced_products:
                    continue
                stock = (
                    inventory.get(str(variant.get("inventory_item_id") or ""))
                    or inventory.get(str(variant.get("sku") or ""))
                    or inventory.get(str(product.get("product_id") or ""))
                    or {}
                )
                inv_level = (
                    stock.get("inventory_level")
                    if stock.get("inventory_level") not in (None, "")
                    else variant.get("inventory_level")
                    if variant.get("inventory_level") not in (None, "")
                    else product.get("inventory_level")
                    if product.get("inventory_level") not in (None, "")
                    else product.get("stock_quantity", "")
                )
                rows.append(
                    {
                        "product_name": product.get("product_name") or "",
                        "product_id": variant.get("sku")
                        or variant.get("variant_id")
                        or product.get("product_id")
                        or "",
                        "sku": variant.get("sku") or product.get("sku") or "",
                        "unit_price": variant.get("unit_price")
                        or product.get("unit_price")
                        or "",
                        "inventory_level": inv_level,
                        "product_category": product.get("product_category") or "",
                        "source_updated_at": variant.get("updated_at")
                        or product.get("updated_at")
                        or "",
                        "source_provider": connection.provider,
                        "source_connection_id": str(connection.id),
                        "source_store": connection.external_account_id,
                    }
                )
        return rows

    def _normalize_provider(
        self,
        provider: str,
        entity_type: str,
        record: Mapping[str, Any],
    ) -> dict[str, Any]:
        if provider == "shopify":
            return self._normalize_shopify(entity_type, record)
        if provider == "woocommerce":
            return self._normalize_woocommerce(entity_type, record)
        raise CommerceSyncDataError(f"Unsupported commerce provider '{provider}'")

    def _normalize_shopify(
        self,
        entity_type: str,
        record: Mapping[str, Any],
    ) -> dict[str, Any]:
        normalizers = {
            "orders": self._normalize_order,
            "customers": self._normalize_customer,
            "products": self._normalize_product,
            "inventory": self._normalize_inventory,
            "refunds": self._normalize_refund,
        }
        normalizer = normalizers.get(entity_type)
        if normalizer is None:
            raise CommerceSyncDataError(f"Unsupported Shopify entity '{entity_type}'")
        return normalizer(record)

    def _normalize_woocommerce(
        self,
        entity_type: str,
        record: Mapping[str, Any],
    ) -> dict[str, Any]:
        normalizers = {
            "orders": self._normalize_woocommerce_order,
            "customers": self._normalize_woocommerce_customer,
            "products": self._normalize_woocommerce_product,
            "inventory": self._normalize_woocommerce_inventory,
            "refunds": self._normalize_woocommerce_refund,
        }
        normalizer = normalizers.get(entity_type)
        if normalizer is None:
            raise CommerceSyncDataError(
                f"Unsupported WooCommerce entity '{entity_type}'"
            )
        return normalizer(record)

    def _normalize_woocommerce_order(
        self, record: Mapping[str, Any]
    ) -> dict[str, Any]:
        billing = self._mapping(record.get("billing"))
        shipping = self._mapping(record.get("shipping"))
        lines: list[dict[str, Any]] = []
        for raw_line in record.get("line_items") or ():
            if not isinstance(raw_line, Mapping):
                continue
            subtotal = self._decimal(raw_line.get("subtotal"))
            total = self._decimal(raw_line.get("total"))
            lines.append(
                {
                    "source_line_item_id": self._text(raw_line.get("id")),
                    "product_id": self._text(raw_line.get("product_id")),
                    "variant_id": self._text(raw_line.get("variation_id")),
                    "sku": self._text(raw_line.get("sku")),
                    "product_name": self._text(raw_line.get("name")),
                    "product_category": "",
                    "quantity": self._integer(raw_line.get("quantity")),
                    "unit_price": self._decimal_text(
                        self._decimal(raw_line.get("price"))
                    ),
                    "line_total": self._decimal_text(total),
                    "discount_amount": self._decimal_text(max(subtotal - total, Decimal("0"))),
                    "inventory_level": "",
                }
            )
        customer_id = self._integer(record.get("customer_id"))
        return {
            "source_order_id": self._text(record.get("id")),
            "order_id": self._text(record.get("number") or record.get("id")),
            "order_timestamp": self._text(
                record.get("date_created_gmt") or record.get("date_created")
            ),
            "updated_at": self._text(
                record.get("date_modified_gmt") or record.get("date_modified")
            ),
            "customer_id": str(customer_id) if customer_id > 0 else "",
            "customer_email": self._text(billing.get("email")),
            "customer_country": self._text(
                shipping.get("country") or billing.get("country")
            ),
            "currency": self._text(record.get("currency")),
            "subtotal_amount": self._decimal_text(
                self._decimal(record.get("total"))
                - self._decimal(record.get("total_tax"))
            ),
            "total_amount": self._decimal_text(self._decimal(record.get("total"))),
            "tax_amount": self._decimal_text(
                self._decimal(record.get("total_tax"))
            ),
            "discount_amount": self._decimal_text(
                self._decimal(record.get("discount_total"))
            ),
            "fulfillment_status": self._text(record.get("status")),
            "sales_channel": self._text(record.get("created_via") or "woocommerce"),
            "line_items": lines,
        }

    def _normalize_woocommerce_customer(
        self, record: Mapping[str, Any]
    ) -> dict[str, Any]:
        billing = self._mapping(record.get("billing"))
        return {
            "customer_id": self._text(record.get("id")),
            "email": self._text(record.get("email") or billing.get("email")),
            "first_name": self._text(record.get("first_name")),
            "last_name": self._text(record.get("last_name")),
            "country": self._text(billing.get("country")),
            "orders_count": self._integer(record.get("orders_count")),
            "lifetime_value": self._decimal_text(
                self._decimal(record.get("total_spent"))
            ),
            "created_at": self._text(
                record.get("date_created_gmt") or record.get("date_created")
            ),
            "updated_at": self._text(
                record.get("date_modified_gmt") or record.get("date_modified")
            ),
        }

    def _normalize_woocommerce_product(
        self, record: Mapping[str, Any]
    ) -> dict[str, Any]:
        categories = [
            self._text(item.get("name"))
            for item in record.get("categories") or ()
            if isinstance(item, Mapping) and item.get("name")
        ]
        variations = []
        for variation in record.get("avenqo_variations") or ():
            if not isinstance(variation, Mapping):
                continue
            variations.append(
                {
                    "variant_id": self._text(variation.get("id")),
                    "sku": self._text(variation.get("sku")),
                    "variant_name": self._woocommerce_attributes(variation),
                    "unit_price": self._decimal_text(
                        self._decimal(variation.get("price"))
                    ),
                    "inventory_level": variation.get("stock_quantity", ""),
                    "inventory_item_id": self._text(variation.get("id")),
                    "updated_at": self._text(
                        variation.get("date_modified_gmt")
                        or variation.get("date_modified")
                    ),
                }
            )
        stock_qty = record.get("stock_quantity")
        return {
            "product_id": self._text(record.get("id")),
            "product_name": self._text(record.get("name")),
            "product_category": ", ".join(categories),
            "vendor": "",
            "sku": self._text(record.get("sku")),
            "unit_price": self._decimal_text(self._decimal(record.get("price"))),
            "inventory_level": stock_qty if stock_qty is not None else "",
            "stock_quantity": stock_qty if stock_qty is not None else "",
            "created_at": self._text(
                record.get("date_created_gmt") or record.get("date_created")
            ),
            "updated_at": self._text(
                record.get("date_modified_gmt") or record.get("date_modified")
            ),
            "variants": variations,
        }

    def _normalize_woocommerce_inventory(
        self, record: Mapping[str, Any]
    ) -> dict[str, Any]:
        return {
            "inventory_item_id": self._text(record.get("inventory_item_id")),
            "product_id": self._text(record.get("product_id")),
            "sku": self._text(record.get("sku")),
            "inventory_level": self._integer(record.get("stock_quantity")),
            "updated_at": self._text(record.get("updated_at")),
            "locations": [],
        }

    def _normalize_woocommerce_refund(
        self, record: Mapping[str, Any]
    ) -> dict[str, Any]:
        return {
            "refund_id": self._text(record.get("id")),
            "source_order_id": self._text(record.get("avenqo_order_id")),
            "refund_timestamp": self._text(
                record.get("date_created_gmt") or record.get("date_created")
            ),
            "updated_at": self._text(
                record.get("date_created_gmt") or record.get("date_created")
            ),
            "refund_amount": self._decimal_text(
                abs(self._decimal(record.get("amount")))
            ),
            "currency": "",
            "line_items": [
                {
                    "source_line_item_id": self._text(item.get("id")),
                    "quantity": abs(self._integer(item.get("quantity"))),
                    "refund_amount": self._decimal_text(
                        abs(self._decimal(item.get("refund_total")))
                    ),
                }
                for item in record.get("line_items") or ()
                if isinstance(item, Mapping)
            ],
        }

    @classmethod
    def _woocommerce_attributes(cls, record: Mapping[str, Any]) -> str:
        return " / ".join(
            cls._text(item.get("option"))
            for item in record.get("attributes") or ()
            if isinstance(item, Mapping) and item.get("option")
        )

    def _normalize_order(self, record: Mapping[str, Any]) -> dict[str, Any]:
        customer = self._mapping(record.get("customer"))
        address = self._mapping(record.get("shippingAddress"))
        line_items = self._nodes(record.get("lineItems"))
        normalized_lines = []
        for line in line_items:
            product = self._mapping(line.get("product"))
            variant = self._mapping(line.get("variant"))
            discount = sum(
                (
                    self._decimal(
                        self._mapping(item).get("allocatedAmountSet")
                    )
                    for item in line.get("discountAllocations") or ()
                    if isinstance(item, Mapping)
                ),
                Decimal("0"),
            )
            normalized_lines.append(
                {
                    "shopify_line_item_gid": self._text(line.get("id")),
                    "product_id": self._text(product.get("id")),
                    "variant_id": self._text(variant.get("id")),
                    "sku": self._text(variant.get("sku")),
                    "product_name": self._text(product.get("title")),
                    "product_category": self._text(product.get("productType")),
                    "quantity": self._integer(line.get("quantity")),
                    "unit_price": self._money_text(line.get("originalUnitPriceSet")),
                    "line_total": self._money_text(line.get("discountedTotalSet")),
                    "discount_amount": self._decimal_text(discount),
                    "inventory_level": variant.get("inventoryQuantity", ""),
                }
            )
        return {
            "shopify_order_gid": self._text(record.get("id")),
            "order_id": self._text(record.get("name") or record.get("id")),
            "order_timestamp": self._text(record.get("createdAt")),
            "updated_at": self._text(record.get("updatedAt")),
            "customer_id": self._text(customer.get("id")),
            "customer_email": self._text(record.get("email") or customer.get("email")),
            "customer_country": self._text(address.get("countryCodeV2")),
            "currency": self._text(record.get("currencyCode")),
            "subtotal_amount": self._money_text(record.get("currentSubtotalPriceSet")),
            "total_amount": self._money_text(record.get("currentTotalPriceSet")),
            "tax_amount": self._money_text(record.get("currentTotalTaxSet")),
            "discount_amount": self._money_text(record.get("totalDiscountsSet")),
            "fulfillment_status": self._text(record.get("displayFulfillmentStatus")),
            "sales_channel": self._text(record.get("sourceName")),
            "line_items": normalized_lines,
        }

    def _normalize_customer(self, record: Mapping[str, Any]) -> dict[str, Any]:
        address = self._mapping(record.get("defaultAddress"))
        return {
            "customer_id": self._text(record.get("id")),
            "email": self._text(record.get("email")),
            "first_name": self._text(record.get("firstName")),
            "last_name": self._text(record.get("lastName")),
            "country": self._text(address.get("countryCodeV2")),
            "orders_count": self._integer(record.get("numberOfOrders")),
            "lifetime_value": self._money_text(record.get("amountSpent")),
            "created_at": self._text(record.get("createdAt")),
            "updated_at": self._text(record.get("updatedAt")),
        }

    def _normalize_product(self, record: Mapping[str, Any]) -> dict[str, Any]:
        variants = []
        for variant in self._nodes(record.get("variants")):
            inventory_item = self._mapping(variant.get("inventoryItem"))
            variants.append(
                {
                    "variant_id": self._text(variant.get("id")),
                    "sku": self._text(variant.get("sku")),
                    "variant_name": self._text(variant.get("title")),
                    "unit_price": self._money_text(variant.get("price")),
                    "inventory_level": variant.get("inventoryQuantity", ""),
                    "inventory_item_id": self._text(inventory_item.get("id")),
                    "updated_at": self._text(variant.get("updatedAt")),
                }
            )
        return {
            "product_id": self._text(record.get("id")),
            "product_name": self._text(record.get("title")),
            "product_category": self._text(record.get("productType")),
            "vendor": self._text(record.get("vendor")),
            "created_at": self._text(record.get("createdAt")),
            "updated_at": self._text(record.get("updatedAt")),
            "variants": variants,
        }

    def _normalize_inventory(self, record: Mapping[str, Any]) -> dict[str, Any]:
        levels = []
        total = 0
        for level in self._nodes(record.get("inventoryLevels")):
            location = self._mapping(level.get("location"))
            available = sum(
                self._integer(self._mapping(quantity).get("quantity"))
                for quantity in level.get("quantities") or ()
                if isinstance(quantity, Mapping)
                and self._mapping(quantity).get("name") == "available"
            )
            total += available
            levels.append(
                {
                    "inventory_level_id": self._text(level.get("id")),
                    "location_id": self._text(location.get("id")),
                    "location_name": self._text(location.get("name")),
                    "inventory_level": available,
                }
            )
        return {
            "inventory_item_id": self._text(record.get("id")),
            "sku": self._text(record.get("sku")),
            "inventory_level": total,
            "updated_at": self._text(record.get("updatedAt")),
            "locations": levels,
        }

    def _normalize_refund(self, record: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "refund_id": self._text(record.get("id")),
            "shopify_order_gid": self._text(record.get("orderId")),
            "refund_timestamp": self._text(
                record.get("processedAt") or record.get("createdAt")
            ),
            "updated_at": self._text(record.get("updatedAt")),
            "refund_amount": self._money_text(record.get("totalRefundedSet")),
            "currency": self._money_currency(record.get("totalRefundedSet")),
            "line_items": [
                {
                    "shopify_line_item_gid": self._text(
                        self._mapping(item.get("lineItem")).get("id")
                    ),
                    "quantity": self._integer(item.get("quantity")),
                    "refund_amount": self._money_text(item.get("subtotalSet")),
                }
                for item in self._nodes(record.get("refundLineItems"))
            ],
        }

    def _allocate_total(
        self,
        total_value: Any,
        lines: list[dict[str, Any]],
    ) -> list[Decimal]:
        total = self._decimal(total_value)
        weights = [self._decimal(line.get("line_total")) for line in lines]
        weight_total = sum(weights, Decimal("0"))
        if weight_total <= 0:
            weights = [Decimal("1") for _ in lines]
            weight_total = Decimal(len(lines))
        allocations: list[Decimal] = []
        allocated = Decimal("0")
        for index, weight in enumerate(weights):
            if index == len(weights) - 1:
                amount = total - allocated
            else:
                amount = (total * weight / weight_total).quantize(Decimal("0.000001"))
                allocated += amount
            allocations.append(amount)
        return allocations

    @classmethod
    def _nodes(cls, value: Any) -> tuple[Mapping[str, Any], ...]:
        nodes = cls._mapping(value).get("nodes")
        if not isinstance(nodes, list):
            return ()
        return tuple(item for item in nodes if isinstance(item, Mapping))

    @staticmethod
    def _mapping(value: Any) -> Mapping[str, Any]:
        return value if isinstance(value, Mapping) else {}

    @classmethod
    def _money_text(cls, value: Any) -> str:
        return cls._decimal_text(cls._decimal(value))

    @classmethod
    def _money_currency(cls, value: Any) -> str:
        mapping = cls._mapping(value)
        money = cls._mapping(mapping.get("shopMoney")) if "shopMoney" in mapping else mapping
        return cls._text(money.get("currencyCode"))

    @classmethod
    def _decimal(cls, value: Any) -> Decimal:
        if isinstance(value, Mapping):
            mapping = cls._mapping(value)
            if "shopMoney" in mapping:
                return cls._decimal(cls._mapping(mapping.get("shopMoney")).get("amount"))
            return cls._decimal(mapping.get("amount"))
        try:
            return Decimal(str(value if value not in (None, "") else 0))
        except (InvalidOperation, TypeError, ValueError):
            return Decimal("0")

    @staticmethod
    def _decimal_text(value: Decimal) -> str:
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"

    @staticmethod
    def _integer(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _text(value: Any) -> str:
        return "" if value is None else str(value)

    @classmethod
    def _source_updated_at(cls, record: Mapping[str, Any]) -> datetime | None:
        return cls._parse_datetime(
            record.get("updatedAt")
            or record.get("processedAt")
            or record.get("createdAt")
            or record.get("date_modified_gmt")
            or record.get("date_modified")
            or record.get("date_created_gmt")
            or record.get("date_created")
            or record.get("updated_at")
        )

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return CommerceSyncService._as_utc(parsed)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _isoformat(value: datetime) -> str:
        return CommerceSyncService._as_utc(value).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        return str(value) if value not in (None, "") else None

    @staticmethod
    def _dataset_id(connection: CommerceConnection) -> UUID | None:
        value = (connection.dataset_ids or {}).get("retail")
        try:
            return UUID(str(value)) if value else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _required_header(
        headers: Mapping[str, str],
        name: str,
        *,
        provider: str = "Shopify",
    ) -> str:
        value = headers.get(name, "").strip()
        if not value:
            raise CommerceSyncDataError(f"Missing {provider} webhook header '{name}'")
        return value

    @classmethod
    def _is_active_sync(cls, connection: CommerceConnection) -> bool:
        if connection.status not in {
            CommerceConnectionStatus.SYNCING.value,
            CommerceConnectionStatus.PROCESSING.value,
        }:
            return False
        ref_time = connection.last_heartbeat or connection.sync_started_at
        if ref_time is None:
            return False
        return cls._as_utc(ref_time) > cls._now() - cls._ACTIVE_SYNC_TIMEOUT

    def _recover_zombie_if_stalled(self, connection: CommerceConnection) -> bool:
        if connection.status not in {
            CommerceConnectionStatus.SYNCING.value,
            CommerceConnectionStatus.PROCESSING.value,
        }:
            return False
        ref_time = connection.last_heartbeat or connection.sync_started_at
        if ref_time is None or self._as_utc(ref_time) <= self._now() - self._ACTIVE_SYNC_TIMEOUT:
            connection.status = CommerceConnectionStatus.FAILED.value
            connection.sync_error_code = "STALLED_TIMEOUT"
            connection.sync_error_message = (
                "Synchronisation interrompue par dépassement du délai de pulsation (zombie job)."
            )
            connection.sync_failed_at = self._now()
            connection.sync_started_at = None
            connection.current_entity = None
            self._db.commit()
            return True
        return False

    @classmethod
    def _same_datetime(
        cls,
        left: datetime | None,
        right: datetime | None,
    ) -> bool:
        if left is None or right is None:
            return left is right
        return cls._as_utc(left) == cls._as_utc(right)

    @staticmethod
    def _error_category(exc: Exception) -> str:
        if isinstance(exc, PermissionError):
            return "storage_unavailable"
        if isinstance(exc, ShopifyAuthenticationError):
            return "reauthorization_required"
        if isinstance(exc, WooCommerceAuthenticationError):
            return "reauthorization_required"
        if isinstance(exc, WooCommercePermissionError):
            return "insufficient_permissions"
        if isinstance(exc, WooCommerceRateLimitError):
            return "rate_limited"
        if isinstance(exc, ShopifyTemporaryError):
            return "provider_temporarily_unavailable"
        if isinstance(exc, WooCommerceTemporaryError):
            return "provider_temporarily_unavailable"
        if isinstance(exc, ShopifyConnectorError):
            return "provider_error"
        if isinstance(exc, WooCommerceConnectorError):
            return "provider_error"
        if isinstance(exc, CommerceSyncDataError):
            return "provider_data_invalid"
        return "sync_failed"

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)
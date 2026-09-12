"""Canonical retail entities projected from normalized source records."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any
from uuid import UUID


class RetailEntity(str, Enum):
    STORE = "stores"
    CUSTOMER = "customers"
    PRODUCT = "products"
    ORDER = "orders"
    ORDER_LINE = "order_lines"
    INVENTORY = "inventory"
    PAYMENT = "payments"
    REFUND = "refunds"
    FULFILLMENT = "fulfillments"


@dataclass(frozen=True, slots=True)
class CanonicalRetailContext:
    tenant_id: UUID
    company_id: UUID
    source_id: UUID
    source_provider: str
    store_id: str


@dataclass(frozen=True, slots=True)
class CanonicalRetailDataset:
    entities: Mapping[str, tuple[dict[str, Any], ...]]
    schema_version: str = "retail-canonical-v1"

    def counts(self) -> dict[str, int]:
        return {name: len(records) for name, records in self.entities.items()}


ENTITY_REQUIRED_FIELDS: dict[RetailEntity, frozenset[str]] = {
    RetailEntity.STORE: frozenset({"tenant_id", "source_id", "store_id"}),
    RetailEntity.CUSTOMER: frozenset({"tenant_id", "source_id", "customer_id"}),
    RetailEntity.PRODUCT: frozenset({"tenant_id", "source_id", "product_id"}),
    RetailEntity.ORDER: frozenset({"tenant_id", "source_id", "order_id"}),
    RetailEntity.ORDER_LINE: frozenset(
        {"tenant_id", "source_id", "order_id", "line_item_id"}
    ),
    RetailEntity.INVENTORY: frozenset(
        {"tenant_id", "source_id", "product_id", "stock_quantity"}
    ),
    RetailEntity.PAYMENT: frozenset({"tenant_id", "source_id", "payment_id"}),
    RetailEntity.REFUND: frozenset({"tenant_id", "source_id", "refund_id"}),
    RetailEntity.FULFILLMENT: frozenset(
        {"tenant_id", "source_id", "fulfillment_id"}
    ),
}

ENTITY_DEDUPLICATION_KEYS: dict[RetailEntity, tuple[str, ...]] = {
    entity: tuple(sorted(fields)) for entity, fields in ENTITY_REQUIRED_FIELDS.items()
}


def project_canonical_retail(
    context: CanonicalRetailContext,
    normalized_by_entity: Mapping[str, Sequence[Mapping[str, Any]]],
) -> CanonicalRetailDataset:
    """Project normalized records without embedding provider-specific schemas."""

    output: dict[RetailEntity, list[dict[str, Any]]] = {
        entity: [] for entity in RetailEntity
    }
    output[RetailEntity.STORE].append(_base(context) | {"store_id": context.store_id})

    for customer in normalized_by_entity.get("customers", ()):
        customer_id = _text(customer.get("customer_id"))
        if not customer_id:
            continue
        output[RetailEntity.CUSTOMER].append(
            _base(context)
            | {
                "customer_id": customer_id,
                "first_name": customer.get("first_name"),
                "last_name": customer.get("last_name"),
                "email": customer.get("email"),
                "country": customer.get("country"),
                "region": customer.get("region"),
                "city": customer.get("city"),
                "postal_code": customer.get("postal_code"),
                "created_at": customer.get("created_at"),
                "updated_at": customer.get("updated_at"),
                "external_ids": _external_ids(customer, customer_id),
            }
        )

    for product in normalized_by_entity.get("products", ()):
        product_id = _text(product.get("product_id"))
        if not product_id:
            continue
        variants = tuple(
            variant
            for variant in product.get("variants") or ()
            if isinstance(variant, Mapping)
        ) or ({},)
        for variant in variants:
            variant_id = _text(variant.get("variant_id")) or None
            sku = _text(variant.get("sku")) or None
            output[RetailEntity.PRODUCT].append(
                _base(context)
                | {
                    "product_id": product_id,
                    "variant_id": variant_id,
                    "product_name": product.get("product_name"),
                    "sku": sku,
                    "category": product.get("product_category"),
                    "brand": product.get("vendor"),
                    "current_price": variant.get("unit_price")
                    or product.get("unit_price"),
                    "currency": product.get("currency"),
                    "active": product.get("active"),
                    "updated_at": variant.get("updated_at") or product.get("updated_at"),
                    "external_ids": _external_ids(product, product_id),
                }
            )

    for inventory in normalized_by_entity.get("inventory", ()):
        product_id = _text(inventory.get("product_id"))
        if not product_id:
            continue
        output[RetailEntity.INVENTORY].append(
            _base(context)
            | {
                "product_id": product_id,
                "variant_id": inventory.get("variant_id"),
                "sku": inventory.get("sku"),
                "stock_quantity": inventory.get("inventory_level"),
                "stock_status": inventory.get("stock_status"),
                "inventory_updated_at": inventory.get("updated_at"),
                "external_ids": _external_ids(
                    inventory, _text(inventory.get("inventory_item_id"))
                ),
            }
        )

    for order in normalized_by_entity.get("orders", ()):
        order_id = _text(order.get("order_id") or order.get("source_order_id"))
        if not order_id:
            continue
        output[RetailEntity.ORDER].append(
            _base(context)
            | {
                "store_id": context.store_id,
                "order_id": order_id,
                "order_number": order.get("order_id"),
                "customer_id": order.get("customer_id"),
                "order_created_at": order.get("order_timestamp"),
                "order_updated_at": order.get("updated_at"),
                "order_status": order.get("order_status"),
                "financial_status": order.get("financial_status"),
                "fulfillment_status": order.get("fulfillment_status"),
                "currency": order.get("currency"),
                "subtotal": order.get("subtotal_amount"),
                "discount_total": order.get("discount_amount"),
                "tax_total": order.get("tax_amount"),
                "shipping_total": order.get("shipping_amount"),
                "refund_total": order.get("refund_amount"),
                "order_total": order.get("total_amount"),
                "external_ids": _external_ids(
                    order, _text(order.get("source_order_id"))
                ),
            }
        )
        for index, line in enumerate(order.get("line_items") or ()):
            if not isinstance(line, Mapping):
                continue
            line_item_id = _text(line.get("source_line_item_id")) or str(index + 1)
            output[RetailEntity.ORDER_LINE].append(
                _base(context)
                | {
                    "order_id": order_id,
                    "line_item_id": line_item_id,
                    "product_id": line.get("product_id"),
                    "variant_id": line.get("variant_id"),
                    "sku": line.get("sku"),
                    "product_name": line.get("product_name"),
                    "quantity": line.get("quantity"),
                    "unit_price": line.get("unit_price"),
                    "discount_amount": line.get("discount_amount"),
                    "tax_amount": line.get("tax_amount"),
                    "line_total": line.get("line_total"),
                    "external_ids": _external_ids(line, line_item_id),
                }
            )

    for refund in normalized_by_entity.get("refunds", ()):
        refund_id = _text(refund.get("refund_id"))
        if refund_id:
            output[RetailEntity.REFUND].append(
                _base(context)
                | {
                    "refund_id": refund_id,
                    "order_id": refund.get("source_order_id"),
                    "refund_total": refund.get("refund_amount"),
                    "currency": refund.get("currency"),
                    "refunded_at": refund.get("refund_timestamp"),
                    "external_ids": _external_ids(refund, refund_id),
                }
            )

    for payment in normalized_by_entity.get("payments", ()):
        payment_id = _text(payment.get("payment_id"))
        if payment_id:
            output[RetailEntity.PAYMENT].append(
                _base(context)
                | {
                    "payment_id": payment_id,
                    "order_id": payment.get("order_id")
                    or payment.get("source_order_id"),
                    "payment_method": payment.get("payment_method"),
                    "payment_status": payment.get("payment_status"),
                    "amount": payment.get("payment_amount")
                    or payment.get("total_amount"),
                    "currency": payment.get("currency"),
                    "paid_at": payment.get("paid_at"),
                    "external_ids": _external_ids(payment, payment_id),
                }
            )

    for fulfillment in normalized_by_entity.get("fulfillments", ()):
        fulfillment_id = _text(fulfillment.get("fulfillment_id"))
        if fulfillment_id:
            output[RetailEntity.FULFILLMENT].append(
                _base(context)
                | {
                    "fulfillment_id": fulfillment_id,
                    "order_id": fulfillment.get("order_id")
                    or fulfillment.get("source_order_id"),
                    "fulfillment_status": fulfillment.get("fulfillment_status"),
                    "tracking_number": fulfillment.get("tracking_number"),
                    "carrier": fulfillment.get("carrier"),
                    "fulfilled_at": fulfillment.get("fulfilled_at")
                    or fulfillment.get("delivery_timestamp"),
                    "external_ids": _external_ids(
                        fulfillment, fulfillment_id
                    ),
                }
            )

    entities = {
        entity.value: tuple(_deduplicate(records, ENTITY_DEDUPLICATION_KEYS[entity]))
        for entity, records in output.items()
    }
    return CanonicalRetailDataset(entities=entities)


def project_flat_canonical_retail(
    context: CanonicalRetailContext,
    rows: Sequence[Mapping[str, Any]],
    column_mapping: Mapping[str, str],
) -> CanonicalRetailDataset:
    """Project mapped rows from files into the same entities as connectors."""

    normalized: dict[str, list[dict[str, Any]]] = {
        "customers": [],
        "products": [],
        "orders": [],
        "inventory": [],
        "payments": [],
        "refunds": [],
        "fulfillments": [],
    }
    for row_index, source_row in enumerate(rows, start=1):
        row = {
            column_mapping.get(column, column): value
            for column, value in source_row.items()
        }
        customer_id = _text(row.get("customer_id"))
        product_id = _text(row.get("product_id"))
        order_id = _text(row.get("order_id"))
        if customer_id:
            normalized["customers"].append(row)
        if product_id:
            normalized["products"].append(row)
        if product_id and row.get("inventory_level") is not None:
            normalized["inventory"].append(row)
        if order_id:
            order = dict(row)
            if product_id or row.get("quantity") is not None:
                order["line_items"] = [
                    row
                    | {
                        "source_line_item_id": _text(row.get("line_item_id"))
                        or f"{order_id}:{product_id or row_index}:{row_index}"
                    }
                ]
            normalized["orders"].append(order)
        if _text(row.get("payment_id")):
            normalized["payments"].append(row)
        if _text(row.get("refund_id")):
            normalized["refunds"].append(row)
        if _text(row.get("fulfillment_id")):
            normalized["fulfillments"].append(row)
    return project_canonical_retail(context, normalized)


def _base(context: CanonicalRetailContext) -> dict[str, Any]:
    return {
        "tenant_id": str(context.tenant_id),
        "company_id": str(context.company_id),
        "source_id": str(context.source_id),
        "source_provider": context.source_provider,
    }


def _external_ids(record: Mapping[str, Any], primary_id: str) -> dict[str, str]:
    return {"source_record_id": primary_id} if primary_id else {}


def _deduplicate(
    records: Sequence[dict[str, Any]], keys: Sequence[str]
) -> list[dict[str, Any]]:
    by_identity: dict[tuple[Any, ...], dict[str, Any]] = {}
    for record in records:
        identity = tuple(record.get(key) for key in keys)
        if any(value in (None, "") for value in identity):
            continue
        by_identity[identity] = record
    return list(by_identity.values())


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""
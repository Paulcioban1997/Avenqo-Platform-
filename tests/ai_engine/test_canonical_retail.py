from uuid import uuid4

from shared.ai_engine.dataset_ingestion.canonical_retail import (
    CanonicalRetailContext,
    project_flat_canonical_retail,
    project_canonical_retail,
)


def _context(provider: str) -> CanonicalRetailContext:
    company_id = uuid4()
    return CanonicalRetailContext(
        tenant_id=company_id,
        company_id=company_id,
        source_id=uuid4(),
        source_provider=provider,
        store_id="store-1",
    )


def _source_records() -> dict:
    return {
        "orders": [
            {
                "source_order_id": "external-order-15",
                "order_id": "15",
                "currency": "CAD",
                "total_amount": "100.00",
                "line_items": [
                    {
                        "source_line_item_id": "line-1",
                        "product_id": "product-1",
                        "product_name": "Headphones",
                        "quantity": 1,
                    }
                ],
            }
        ],
        "products": [
            {"product_id": "product-1", "product_name": "Headphones"},
            {"product_id": "product-1", "product_name": "Headphones"},
        ],
        "inventory": [
            {
                "inventory_item_id": "inventory-1",
                "product_id": "product-1",
                "inventory_level": 25,
            }
        ],
    }


def test_projection_is_provider_neutral_and_separates_current_inventory() -> None:
    first = project_canonical_retail(_context("provider-a"), _source_records())
    second = project_canonical_retail(_context("provider-b"), _source_records())

    assert set(first.entities) == set(second.entities)
    assert set(first.entities["orders"][0]) == set(second.entities["orders"][0])
    assert "shopify_order_gid" not in first.entities["orders"][0]
    assert "woocommerce_order_key" not in second.entities["orders"][0]
    assert first.entities["order_lines"][0]["quantity"] == 1
    assert first.entities["inventory"][0]["stock_quantity"] == 25


def test_projection_deduplicates_with_source_scoped_business_keys() -> None:
    projected = project_canonical_retail(_context("provider-a"), _source_records())

    assert projected.counts()["products"] == 1
    product = projected.entities["products"][0]
    assert product["tenant_id"]
    assert product["company_id"]
    assert product["source_id"]


def test_flat_uploaded_rows_project_to_separate_retail_entities() -> None:
    projected = project_flat_canonical_retail(
        _context("uploaded_dataset"),
        [
            {
                "sale": "order-1",
                "client": "customer-1",
                "item": "product-1",
                "name": "Headphones",
                "qty": 2,
                "price": 40.0,
                "stock": 12,
                "payment": "payment-1",
                "method": "card",
                "fulfillment": "fulfillment-1",
            }
        ],
        {
            "sale": "order_id",
            "client": "customer_id",
            "item": "product_id",
            "name": "product_name",
            "qty": "quantity",
            "price": "unit_price",
            "stock": "inventory_level",
            "payment": "payment_id",
            "method": "payment_method",
            "fulfillment": "fulfillment_id",
        },
    )

    assert projected.counts()["orders"] == 1
    assert projected.counts()["order_lines"] == 1
    assert projected.counts()["customers"] == 1
    assert projected.counts()["products"] == 1
    assert projected.counts()["inventory"] == 1
    assert projected.counts()["payments"] == 1
    assert projected.counts()["fulfillments"] == 1
    assert projected.entities["inventory"][0]["stock_quantity"] == 12
    assert projected.entities["order_lines"][0]["quantity"] == 2
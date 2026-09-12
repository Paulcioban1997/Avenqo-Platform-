"""Targeted Tests A-G for Intelligent Auto-Mapping Pipeline.

Tests:
TEST A - WooCommerce dataset: processed and auto-mapped hands-free.
TEST B - Shopify dataset: processed and auto-mapped hands-free.
TEST C - Standard CSV dataset: standard canonical headers mapped.
TEST D - Messy headers: whitespace and case variations (' Product Name ', 'PRICE', 'stock ', 'Date ', 'email').
TEST E - Ambiguous / unknown column: stays unmapped without blocking.
TEST F - Anti-false-mapping: guarantees currency != payment_id, customer_email != customer_id, fulfillment_status != delivery_timestamp.
TEST G - Retail Intelligence: auto-mapped data projects properly into canonical retail model.
"""

from __future__ import annotations

import pytest

from shared.ai_engine.dataset_ingestion.canonical_fields import CANONICAL_FIELDS
from shared.ai_engine.dataset_ingestion.column_mapper import SemanticColumnMapper, MappingConfidence
from shared.ai_engine.dataset_ingestion.profiling import DatasetProfiler, ColumnProfile
from shared.ai_engine.dataset_ingestion.type_inference import SemanticType
from shared.ai_engine.dataset_ingestion.cleaning import CompanyDatasetCleaner
from shared.ai_engine.dataset_ingestion.canonical_retail import (
    CanonicalRetailContext,
    project_flat_canonical_retail,
)


@pytest.fixture
def profiler() -> DatasetProfiler:
    return DatasetProfiler()


@pytest.fixture
def mapper() -> SemanticColumnMapper:
    return SemanticColumnMapper()


@pytest.fixture
def cleaner() -> CompanyDatasetCleaner:
    return CompanyDatasetCleaner()


# ---------------------------------------------------------------------------
# TEST A - WooCommerce existing dataset
# ---------------------------------------------------------------------------
def test_test_a_woocommerce_dataset(mapper: SemanticColumnMapper):
    columns = ("id", "name", "sku", "price", "stock_quantity", "status")
    rows = [
        {"id": "101", "name": "Avenqo Headphones X", "sku": "AVN-HP-01", "price": "199.99", "stock_quantity": "25", "status": "publish"},
        {"id": "102", "name": "Avenqo Case Pro", "sku": "AVN-CS-02", "price": "29.99", "stock_quantity": "150", "status": "publish"},
    ]
    suggestions = mapper.suggest(columns, rows)

    mapping_by_col = {s.original_column: s for s in suggestions}

    assert mapping_by_col["sku"].suggested_field == "sku"
    assert mapping_by_col["name"].suggested_field == "product_name"
    assert mapping_by_col["price"].suggested_field == "unit_price"
    assert mapping_by_col["stock_quantity"].suggested_field == "inventory_level"

    # All should be high confidence auto-accepted
    for col in ("sku", "name", "price", "stock_quantity"):
        assert mapping_by_col[col].confidence in (MappingConfidence.EXACT, MappingConfidence.HIGH, MappingConfidence.MEDIUM)
        assert mapping_by_col[col].suggested_field is not None


# ---------------------------------------------------------------------------
# TEST B - Shopify existing dataset
# ---------------------------------------------------------------------------
def test_test_b_shopify_dataset(mapper: SemanticColumnMapper):
    columns = ("id", "email", "total_price", "currency", "fulfillment_status", "created_at")
    rows = [
        {
            "id": "1001",
            "email": "buyer@example.com",
            "total_price": "249.50",
            "currency": "USD",
            "fulfillment_status": "fulfilled",
            "created_at": "2026-03-01T10:00:00Z",
        },
        {
            "id": "1002",
            "email": "client@domain.ca",
            "total_price": "89.00",
            "currency": "CAD",
            "fulfillment_status": "unfulfilled",
            "created_at": "2026-03-02T11:30:00Z",
        },
    ]
    suggestions = mapper.suggest(columns, rows)
    mapping_by_col = {s.original_column: s for s in suggestions}

    assert mapping_by_col["email"].suggested_field == "customer_email"
    assert mapping_by_col["total_price"].suggested_field == "total_amount"
    assert mapping_by_col["currency"].suggested_field == "currency"
    assert mapping_by_col["fulfillment_status"].suggested_field == "fulfillment_status"
    assert mapping_by_col["created_at"].suggested_field == "order_timestamp"


# ---------------------------------------------------------------------------
# TEST C - Standard CSV dataset
# ---------------------------------------------------------------------------
def test_test_c_standard_csv(mapper: SemanticColumnMapper):
    columns = ("order_id", "customer_id", "quantity", "unit_price", "total_amount")
    rows = [
        {"order_id": "ORD-1", "customer_id": "CUST-99", "quantity": "2", "unit_price": "45.00", "total_amount": "90.00"},
        {"order_id": "ORD-2", "customer_id": "CUST-100", "quantity": "1", "unit_price": "120.00", "total_amount": "120.00"},
    ]
    suggestions = mapper.suggest(columns, rows)
    mapping_by_col = {s.original_column: s for s in suggestions}

    assert mapping_by_col["order_id"].suggested_field == "order_id"
    assert mapping_by_col["customer_id"].suggested_field == "customer_id"
    assert mapping_by_col["quantity"].suggested_field == "quantity"
    assert mapping_by_col["unit_price"].suggested_field == "unit_price"
    assert mapping_by_col["total_amount"].suggested_field == "total_amount"

    for col in columns:
        assert mapping_by_col[col].confidence in (MappingConfidence.EXACT, MappingConfidence.HIGH)


# ---------------------------------------------------------------------------
# TEST D - Dataset with messy headers
# ---------------------------------------------------------------------------
def test_test_d_messy_headers(mapper: SemanticColumnMapper):
    columns = (" Product Name ", "PRICE", "stock ", "Date ", "email")
    rows = [
        {" Product Name ": "Avenqo Smart Band", "PRICE": "49.99", "stock ": "120", "Date ": "2026-01-15", "email": "test@avenqo.ca"},
        {" Product Name ": "Avenqo Charger", "PRICE": "19.99", "stock ": "300", "Date ": "2026-01-16", "email": "info@avenqo.ca"},
    ]
    suggestions = mapper.suggest(columns, rows)
    mapping_by_col = {s.original_column: s for s in suggestions}

    assert mapping_by_col[" Product Name "].suggested_field == "product_name"
    assert mapping_by_col["PRICE"].suggested_field == "unit_price"
    assert mapping_by_col["stock "].suggested_field == "inventory_level"
    assert mapping_by_col["Date "].suggested_field == "order_timestamp"
    assert mapping_by_col["email"].suggested_field == "customer_email"


# ---------------------------------------------------------------------------
# TEST E - Unknown / ambiguous column stays unmapped without blocking
# ---------------------------------------------------------------------------
def test_test_e_unknown_ambiguous_column(mapper: SemanticColumnMapper):
    columns = ("product_name", "price", "custom_ref_xyz_99", "internal_tracking_hash")
    rows = [
        {"product_name": "Item A", "price": "10.00", "custom_ref_xyz_99": "blob1", "internal_tracking_hash": "a1b2c3d4e5"},
        {"product_name": "Item B", "price": "20.00", "custom_ref_xyz_99": "blob2", "internal_tracking_hash": "f6g7h8i9j0"},
    ]
    suggestions = mapper.suggest(columns, rows)
    mapping_by_col = {s.original_column: s for s in suggestions}

    # Known business columns are mapped
    assert mapping_by_col["product_name"].suggested_field == "product_name"
    assert mapping_by_col["price"].suggested_field == "unit_price"

    # Unknown columns must NOT be mapped to random canonical fields!
    assert mapping_by_col["custom_ref_xyz_99"].suggested_field is None
    assert mapping_by_col["custom_ref_xyz_99"].confidence in (MappingConfidence.LOW, MappingConfidence.UNRESOLVED)

    assert mapping_by_col["internal_tracking_hash"].suggested_field is None
    assert mapping_by_col["internal_tracking_hash"].confidence in (MappingConfidence.LOW, MappingConfidence.UNRESOLVED)


# ---------------------------------------------------------------------------
# TEST F - Anti-false-mapping tests
# ---------------------------------------------------------------------------
def test_test_f_anti_false_mappings(mapper: SemanticColumnMapper):
    columns = ("currency", "customer_email", "fulfillment_status")
    rows = [
        {"currency": "USD", "customer_email": "alice@avenqo.com", "fulfillment_status": "shipped"},
        {"currency": "CAD", "customer_email": "bob@avenqo.com", "fulfillment_status": "pending"},
    ]
    suggestions = mapper.suggest(columns, rows)
    mapping_by_col = {s.original_column: s for s in suggestions}

    # Explicit check: currency MUST NOT map to payment_id
    assert mapping_by_col["currency"].suggested_field != "payment_id"
    assert mapping_by_col["currency"].suggested_field == "currency"

    # Explicit check: customer_email MUST NOT map to customer_id
    assert mapping_by_col["customer_email"].suggested_field != "customer_id"
    assert mapping_by_col["customer_email"].suggested_field == "customer_email"

    # Explicit check: fulfillment_status MUST NOT map to delivery_timestamp
    assert mapping_by_col["fulfillment_status"].suggested_field != "delivery_timestamp"
    assert mapping_by_col["fulfillment_status"].suggested_field == "fulfillment_status"


# ---------------------------------------------------------------------------
# TEST G - Retail Intelligence projection
# ---------------------------------------------------------------------------
def test_test_g_retail_intelligence_projection(
    mapper: SemanticColumnMapper,
    cleaner: CompanyDatasetCleaner,
):
    import uuid

    columns = ("order_id", "product_name", "unit_price", "quantity", "currency", "order_date")
    raw_rows = [
        {"order_id": "ORD-001", "product_name": "Avenqo Headphones", "unit_price": "150.00", "quantity": "2", "currency": "USD", "order_date": "2026-02-10"},
        {"order_id": "ORD-002", "product_name": "Avenqo Wireless Mic", "unit_price": "80.00", "quantity": "1", "currency": "USD", "order_date": "2026-02-11"},
    ]
    suggestions = mapper.suggest(columns, raw_rows)

    # Auto-accepted mapping
    accepted_mapping = {
        s.original_column: s.suggested_field
        for s in suggestions
        if s.suggested_field is not None and s.confidence in (MappingConfidence.HIGH, MappingConfidence.MEDIUM)
    }

    cleaned_rows, _ = cleaner.clean(raw_rows, accepted_mapping)

    ctx = CanonicalRetailContext(
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        source_provider="uploaded_dataset",
        store_id="store-test",
    )

    canonical_dataset = project_flat_canonical_retail(ctx, cleaned_rows, accepted_mapping)
    canonical_entities = canonical_dataset.entities

    assert "orders" in canonical_entities
    orders = canonical_entities["orders"]
    assert len(orders) == 2
    assert orders[0]["order_id"] == "ORD-001"
    assert orders[1]["order_id"] == "ORD-002"

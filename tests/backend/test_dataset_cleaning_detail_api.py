import json
from unittest.mock import MagicMock
from uuid import uuid4
from shared.ai_engine.contracts import TenantContext
from backend.app.services.dataset_cleaning_service import DatasetCleaningService
from backend.app.models import Dataset, DatasetStatus, DatasetVersion, DatasetVersionStatus

def test_cleaning_detail_enrichment():
    tenant = TenantContext(company_id=uuid4())
    dataset_id = uuid4()
    dataset = Dataset(
        id=dataset_id,
        company_id=tenant.company_id,
        name="woocommerce-retail.csv",
        status=DatasetStatus.READY,
        rows_count=2,
        columns_count=5,
    )
    version = DatasetVersion(
        dataset_id=dataset_id,
        version_number=1,
        name="v1",
        status=DatasetVersionStatus.READY,
        is_current=True,
        row_count=2,
        column_count=5,
    )
    dataset.versions.append(version)
    
    mock_ingestion = MagicMock()
    mock_ingestion.get.return_value = dataset
    mock_ingestion._expected_row_count.return_value = 2
    raw_rows = [
        {"product_name": "Avenqo Headphones X", "sku": "HP-X", "unit_price": "245", "inventory_level": "19", "source_connection_id": "conn-123"},
        {"product_name": "Avenqo Smart Watch", "sku": "SW-1", "unit_price": "399", "inventory_level": "10", "source_connection_id": "conn-123"},
    ]
    cleaned_rows = [
        {"product_name": "Avenqo Headphones X", "sku": "HP-X", "unit_price": 245.0, "inventory_level": 25, "source_connection_id": "conn-123"},
        {"product_name": "Avenqo Smart Watch", "sku": "SW-1", "unit_price": 399.0, "inventory_level": 10, "source_connection_id": "conn-123"},
    ]
    mock_ingestion._reload_current_version_rows.return_value = raw_rows
    mock_ingestion.get_cleaned_rows.return_value = tuple(cleaned_rows)
    mock_ingestion._storage.metadata_path.return_value.is_file.return_value = False
    mock_ingestion._storage.canonical_path.return_value.is_file.return_value = False

    service = DatasetCleaningService(mock_ingestion)
    detail = service.detail(tenant, dataset_id)

    # 1. Header
    assert "header" in detail
    assert detail["header"]["name"] == "woocommerce-retail.csv"
    assert "WooCommerce" in detail["header"]["source"]
    assert detail["header"]["status"] == "ready"
    assert detail["header"]["rows_count"] == 2
    assert "columns_cleaned_count" in detail["header"]
    assert "values_modified_count" in detail["header"]

    # 2. Business Preview & Technical Preview
    assert "business_preview" in detail
    assert "technical_preview" in detail
    assert len(detail["business_preview"]) == 2
    assert list(detail["business_preview"][0].keys())[0] == "product_name"
    assert "source_connection_id" not in detail["business_preview"][0]
    assert "source_connection_id" in detail["technical_preview"][0]

    # 3. Columns
    assert "columns" in detail
    col_names = [c["name"] for c in detail["columns"]]
    assert "product_name" in col_names
    assert "inventory_level" in col_names

    # 4. Modifications
    assert "modifications" in detail
    hp_mods = [m for m in detail["modifications"] if m.get("entity") == "Avenqo Headphones X"]
    assert len(hp_mods) > 0
    inv_mod = next((m for m in hp_mods if m["column"] == "inventory_level"), None)
    assert inv_mod is not None
    assert str(inv_mod["before"]) == "19"
    assert str(inv_mod["after"]) == "25"
    assert inv_mod["diff"] == "+6"

    # 5. Quality
    assert "quality" in detail
    assert "score" in detail["quality"]
    assert "types_converted" in detail["quality"]
    assert "rows_analyzed" in detail["quality"]
    assert "columns_analyzed" in detail["quality"]


def test_cleaning_detail_classical_dataset_transformations():
    """Verify classical data cleaning captures trimming, currency, stock integer and date normalization."""
    tenant = TenantContext(company_id=uuid4())
    dataset_id = uuid4()
    dataset = Dataset(
        id=dataset_id,
        company_id=tenant.company_id,
        name="imperfect-dataset.csv",
        status=DatasetStatus.READY,
        rows_count=1,
        columns_count=4,
    )
    version = DatasetVersion(
        dataset_id=dataset_id,
        version_number=1,
        name="v1",
        status=DatasetVersionStatus.READY,
        is_current=True,
        row_count=1,
        column_count=4,
    )
    dataset.versions.append(version)

    mock_ingestion = MagicMock()
    mock_ingestion.get.return_value = dataset
    mock_ingestion._expected_row_count.return_value = 1
    raw_rows = [
        {
            " Product Name ": " Avenqo Headphones X ",
            "PRICE": "245.00 $",
            "stock ": "25 ",
            " Date ": "2026-09-10 04:57:39",
        }
    ]
    cleaned_rows = [
        {
            "product_name": "Avenqo Headphones X",
            "unit_price": 245.0,
            "stock": 25,
            "order_timestamp": "2026-09-10T04:57:39",
        }
    ]
    mock_ingestion._reload_current_version_rows.return_value = raw_rows
    mock_ingestion.get_cleaned_rows.return_value = tuple(cleaned_rows)
    mock_ingestion._storage.metadata_path.return_value.is_file.return_value = False
    mock_ingestion._storage.canonical_path.return_value.is_file.return_value = False

    service = DatasetCleaningService(mock_ingestion)
    detail = service.detail(tenant, dataset_id)

    assert "modifications" in detail
    mods = detail["modifications"]
    assert len(mods) > 0

    # Check that product name trim is captured
    trim_mod = next((m for m in mods if "Headphones" in str(m.get("before"))), None)
    assert trim_mod is not None
    assert trim_mod["before"].strip() == trim_mod["after"]
    assert "Trim" in trim_mod["reason"] or "Espaces" in trim_mod["rule"] or "espaces" in trim_mod["reason"]

    # Check price normalization
    price_mod = next((m for m in mods if "245" in str(m.get("before"))), None)
    assert price_mod is not None
    assert "currency" in price_mod["reason"] or "monétaire" in price_mod["reason"] or "Monétaire" in price_mod["rule"]

    # Check stock normalization
    stock_mod = next((m for m in mods if "25" in str(m.get("before"))), None)
    assert stock_mod is not None
    assert "integer" in stock_mod["reason"] or "stock" in stock_mod["rule"].lower()


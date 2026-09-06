from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.app.ai.tools.business import analytics
from backend.app.services import tenant_products_service as products
from shared.ai_engine.dataset_ingestion.prepared_dataset import PreparedCompanyDataset


@pytest.mark.parametrize("entity", ["product_id", "product_name"])
def test_portfolio_scans_only_product_rows(monkeypatch, entity):
    rows = tuple(
        {"item": f"P{i}", "date": date, "amount": amount, "price": 10}
        for i in range(300)
        for date, amount in [("2026-01-15", 10), ("2026-02-15", 20)]
    )
    source = PreparedCompanyDataset(
        company_id=uuid4(), dataset_id=uuid4(), version=1,
        canonical_columns={"item": entity, "date": "order_timestamp",
                           "amount": "total_amount", "price": "unit_price"},
        rows=rows, profile=SimpleNamespace(), mapping=(),
        cleaning_report=SimpleNamespace(), quality=SimpleNamespace(),
        capability_readiness=(),
    )
    scanned = 0
    original = analytics.compute_sales_summary

    def counted(prepared, **kwargs):
        nonlocal scanned
        scanned += len(prepared.rows)
        assert prepared.company_id == source.company_id
        return original(prepared, **kwargs)

    monkeypatch.setattr(analytics, "compute_sales_summary", counted)
    monkeypatch.setattr(products, "compute_sales_summary", counted)
    result = products.TenantProductsService.portfolio(source)
    assert len(result) == 300
    assert scanned == 3 * len(rows)
    for item in result:
        assert item["revenue"] == 30
        assert item["orders"] == 2
        assert item["average_price"] == 10
        assert item["current_revenue"] == 20
        assert item["previous_revenue"] == 10
        assert item["change_percent"] == 100

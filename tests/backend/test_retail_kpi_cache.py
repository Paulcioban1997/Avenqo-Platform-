from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.models import Base, DatasetVersion
from backend.app.schemas.tenant_dashboard import TenantDashboardResponse
from backend.app.services import retail_kpi_cache as cache
from shared.ai_engine.contracts import TenantContext
from tests.backend.test_tenant_dashboard import _company, _dataset, _dashboard_service


@pytest.fixture
def large(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'large.db'}")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        company = _company(session, "Large", "CAD")
        dataset = _dataset(session, company, "retail.csv")
        artifact = tmp_path / "current.csv"
        with artifact.open("w", encoding="utf-8") as handle:
            handle.write("order,customer,quantity,price,date\n")
            for index in range(60000):
                handle.write(f"O{index // 2},C{index % 40001},2,0.10,2026-08-28\n")
            # Revenue without an order must not disappear, nor should extra customers.
            handle.write(",extra,3,0.10,2026-08-28\n")
            handle.write("old,prior,1,10,2026-07-20\n")
        dataset.source = "upload:retail.csv"
        dataset.rows_count = 1  # Current version metadata controls the large path.
        dataset.mapping.mapping_json = {"accepted": {"order": "order_id", "customer": "customer_id",
            "quantity": "quantity", "price": "unit_price", "date": "order_timestamp"}}
        dataset.versions.append(DatasetVersion(version_number=2, name="current", is_current=True,
            artifact_path=str(artifact), row_count=60002))
        dataset.versions.append(DatasetVersion(version_number=3, name="not-current", is_current=False,
            artifact_path=str(tmp_path / "wrong.csv"), row_count=1))
        session.commit()
        yield session, dataset, TenantContext(company.id)
    engine.dispose()


def test_large_exact_current_artifact_cache_and_dashboard(large, monkeypatch):
    session, dataset, tenant = large
    spec = cache.descriptor(tenant, dataset)
    assert spec["version"] == 2
    payload = cache.build(spec)
    assert payload["current"] == {"revenue": 12000.3, "orders": 30000,
                                   "customers": 40002, "average_order_value": 0.4}
    assert payload["previous"] == {"revenue": 10.0, "orders": 1, "customers": 1, "average_order_value": 10.0}
    monkeypatch.setattr(cache, "rows", lambda *_: pytest.fail("Source read in dashboard hot path"))
    service, _ = _dashboard_service(session, {})  # Fails if prepared ingestion is called.
    for _ in range(2):
        dashboard = service.build(tenant)
        assert {k["key"]: k["value"] for k in dashboard["kpis"]} == payload["current"]
        serialized = TenantDashboardResponse.model_validate(dashboard).model_dump()
        assert all(k["state"] == "AVAILABLE" for k in serialized["kpis"])
    dataset.source = "a completely unrelated source"
    assert cache.read_or_schedule(tenant, dataset) == ("AVAILABLE", payload)


def test_cache_miss_is_processing_and_never_builds_inline(large, monkeypatch):
    session, dataset, tenant = large
    submitted = []
    monkeypatch.setattr(cache._pool, "submit", lambda *args: submitted.append(args))
    monkeypatch.setattr(cache, "rows", lambda *_: pytest.fail("Inline source reconstruction"))
    service, _ = _dashboard_service(session, {})
    try:
        for _ in range(2):
            result = service.build(tenant)
            assert result["status"] == "processing"
            assert all(k["state"] == "PROCESSING" for k in result["kpis"])
        assert len(submitted) == 1
    finally:
        cache._pending.discard(str(cache.cache_path(cache.descriptor(tenant, dataset))))


def test_missing_artifact_and_tenant_isolation(large):
    session, dataset, tenant = large
    spec = cache.descriptor(tenant, dataset)
    cache.build(spec)
    assert cache.read_or_schedule(TenantContext(uuid4()), dataset) == ("SOURCE_UNAVAILABLE", None)
    other = _company(session, "Other", "EUR")
    service, _ = _dashboard_service(session, {})
    assert service.build(TenantContext(other.id))["status"] == "no_data"
    from pathlib import Path
    Path(spec["artifact"]).unlink()
    dashboard = service.build(tenant)
    assert all(k["state"] == "SOURCE_UNAVAILABLE" for k in dashboard["kpis"])


def test_cache_identity_changes_with_tenant_version_mapping_and_artifact(large):
    _, dataset, tenant = large
    spec = cache.descriptor(tenant, dataset)
    original = cache.cache_path(spec)
    for field, value in (("company", str(uuid4())), ("dataset", str(uuid4())),
                         ("version", 9), ("checksum", "new"), ("artifact", "other.csv"),
                         ("mapping", {"other": "order_id"})):
        assert cache.cache_path({**spec, field: value}) != original


def test_total_amount_takes_precedence_and_counts_are_distinct(tmp_path):
    path = tmp_path / "amount.csv"
    path.write_text("o,c,a,q,p\nA,C1,0.10,100,100\nA,C2,0.20,100,100\nB,C2,-0.05,100,100\n,,0.15,100,100\n")
    stat = path.stat()
    spec = {"artifact": str(path), "size": stat.st_size, "mtime": stat.st_mtime_ns,
            "mapping": {"o": "order_id", "c": "customer_id", "a": "total_amount", "q": "quantity", "p": "unit_price"}}
    assert cache.build(spec)["current"] == {"revenue": 0.4, "orders": 2, "customers": 2, "average_order_value": 0.2}


def test_worker_failure_is_explicit_and_does_not_leave_processing_forever(large, monkeypatch):
    _, dataset, tenant = large
    spec = cache.descriptor(tenant, dataset)
    key = str(cache.cache_path(spec))
    def fail(_):
        raise OSError("Unreadable artifact")
    monkeypatch.setattr(cache, "build", fail)
    cache._pending.add(key)
    try:
        cache._run(spec, key)
        assert key not in cache._pending
        assert cache.read_or_schedule(tenant, dataset) == ("SOURCE_UNAVAILABLE", None)
    finally:
        cache._failed.discard(key)


def test_xlsx_streaming_preserves_dates_and_multiple_customers_per_order(tmp_path):
    from datetime import datetime
    from openpyxl import Workbook
    path = tmp_path / "sales.xlsx"
    book = Workbook(write_only=True)
    sheet = book.create_sheet()
    sheet.append(["order", "customer", "amount", "date"])
    sheet.append(["A", "C1", 3.5, datetime(2026, 8, 28)])
    sheet.append(["A", "C2", 4.5, datetime(2026, 8, 28)])
    sheet.append(["A", "C1", 9, datetime(2026, 7, 20)])
    book.save(path)
    stat = path.stat()
    spec = {"artifact": str(path), "size": stat.st_size, "mtime": stat.st_mtime_ns,
            "mapping": {"order": "order_id", "customer": "customer_id", "amount": "total_amount", "date": "order_timestamp"}}
    payload = cache.build(spec)
    assert payload["current"] == {"revenue": 8.0, "orders": 1, "customers": 2, "average_order_value": 8.0}
    assert payload["previous"]["revenue"] == 9

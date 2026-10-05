from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.app.services.data_freshness_service import DataFreshnessService
from backend.app.services.business_metrics_service import BusinessMetricsService


@pytest.fixture
def queried_at():
    return datetime(2026, 10, 4, 21, 0, tzinfo=timezone.utc)


def test_freshness_marks_proven_live_query_only_as_live(queried_at):
    service = DataFreshnessService()

    result = service.evaluate(
        source="shopify:Avenqo Retail Test",
        last_updated_at=queried_at,
        queried_at=queried_at,
        live_query_succeeded=True,
    )

    assert result.freshness_status == "LIVE"
    assert result.age_seconds == 0


def test_freshness_marks_recent_webhook_sync_near_realtime_only_with_event_evidence(queried_at):
    service = DataFreshnessService()
    event_received = queried_at - timedelta(seconds=30)

    result = service.evaluate(
        source="shopify:Avenqo Retail Test",
        last_updated_at=queried_at - timedelta(seconds=5),
        event_received_at=event_received,
        queried_at=queried_at,
    )

    assert result.freshness_status == "NEAR_REALTIME"


def test_recent_sync_is_not_reported_as_live_or_near_realtime_without_webhook_evidence(queried_at):
    service = DataFreshnessService()

    result = service.evaluate(
        source="shopify:Avenqo Retail Test",
        last_updated_at=queried_at - timedelta(minutes=1),
        queried_at=queried_at,
    )

    assert result.freshness_status == "SYNCED"


def test_freshness_marks_old_data_stale_and_missing_data_unavailable(queried_at):
    service = DataFreshnessService()
    stale = service.evaluate(
        source="Superstore-utf8-cleaned.csv",
        last_updated_at=queried_at - timedelta(minutes=16),
        queried_at=queried_at,
    )
    unavailable = service.evaluate(
        source="shopify:Avenqo Retail Test",
        last_updated_at=None,
        queried_at=queried_at,
    )

    assert stale.freshness_status == "STALE"
    assert unavailable.freshness_status == "UNAVAILABLE"


def test_business_metrics_use_company_local_day_and_return_source_provenance(queried_at):
    source = SimpleNamespace(
        company_id=uuid4(),
        dataset_id=uuid4(),
        version=1,
        canonical_columns={"created": "order_timestamp", "amount": "total_amount", "order": "order_id"},
        rows=(
            {"created": "2026-10-04T01:00:00", "amount": 12, "order": "TODAY"},
            {"created": "2026-10-04T03:00:00Z", "amount": 99, "order": "PREVIOUS_LOCAL_DAY"},
            {"created": "2026-10-03T23:30:00", "amount": 50, "order": "YESTERDAY"},
        ),
        profile=SimpleNamespace(),
        mapping=(),
        cleaning_report=SimpleNamespace(),
        quality=SimpleNamespace(),
        capability_readiness=(),
    )
    snapshot = SimpleNamespace(
        company=SimpleNamespace(timezone="America/Toronto", currency_code="CAD"),
        currency="CAD",
        active_source_provider="shopify",
        active_source_type="connector",
        active_source_selected=True,
        active_source_name="Avenqo Retail Test",
        active_source_dataset_id=source.dataset_id,
        active_source_last_updated_at=queried_at - timedelta(minutes=1),
        status="ready",
        prepared=(source,),
        retail_summaries=(),
    )
    service = BusinessMetricsService()
    period = service.resolve_period(
        "today",
        timezone_name="America/Toronto",
        now=queried_at,
        source=source,
    )

    result = service.sales_summary(
        snapshot,
        source,
        period_start=period["start"],
        period_end=period["end"],
        queried_at=queried_at,
    )

    assert result["revenue"] == 12
    assert result["orders"] == 1
    assert period["start"] == datetime(2026, 10, 4, 4, tzinfo=timezone.utc)
    assert result["metrics"][0]["metric_id"] == "revenue"
    assert result["metrics"][0]["currency"] == "CAD"
    assert result["metrics"][0]["source_type"] == "shopify"
    assert result["metrics"][0]["source_ids"] == [str(source.dataset_id)]
    assert result["data_freshness"]["freshness_status"] == "SYNCED"


def test_customer_first_purchase_is_counted_in_company_local_period(queried_at):
    source = SimpleNamespace(
        company_id=uuid4(),
        dataset_id=uuid4(),
        version=1,
        canonical_columns={"created": "order_timestamp", "amount": "total_amount", "order": "order_id", "customer": "customer_id"},
        rows=(
            {"created": "2026-10-04T01:00:00", "amount": 12, "order": "O1", "customer": "C1"},
            {"created": "2026-10-04T03:00:00Z", "amount": 99, "order": "O2", "customer": "C2"},
        ),
        profile=SimpleNamespace(),
        mapping=(),
        cleaning_report=SimpleNamespace(),
        quality=SimpleNamespace(),
        capability_readiness=(),
    )
    snapshot = SimpleNamespace(
        company=SimpleNamespace(timezone="America/Toronto"),
        currency="CAD",
        active_source_provider="shopify",
        active_source_type="connector",
        active_source_selected=True,
        active_source_name="Avenqo Retail Test",
        active_source_dataset_id=source.dataset_id,
        active_source_last_updated_at=queried_at - timedelta(minutes=1),
        status="ready",
        prepared=(source,),
        retail_summaries=(),
    )
    service = BusinessMetricsService()
    period = service.resolve_period("today", timezone_name="America/Toronto", now=queried_at, source=source)

    result = service.customer_summary(
        snapshot,
        source,
        period_start=period["start"],
        period_end=period["end"],
        queried_at=queried_at,
    )

    assert result["total_customers"] == 2
    assert result["new_customers"] == 1
    assert result["metrics"][1]["metric_id"] == "new_customers"
    assert result["metrics"][1]["sample_size"] == 1


def test_today_and_month_comparisons_use_matching_company_local_dates(queried_at):
    today = BusinessMetricsService.resolve_period(
        "today", timezone_name="America/Toronto", now=queried_at
    )
    month = BusinessMetricsService.resolve_period(
        "this_month", timezone_name="America/Toronto", now=queried_at
    )
    previous_month = BusinessMetricsService.resolve_period(
        "last_month", timezone_name="America/Toronto", now=queried_at
    )

    assert today["start"] == datetime(2026, 10, 4, 4, tzinfo=timezone.utc)
    assert today["comparison_start"] == datetime(2026, 10, 3, 4, tzinfo=timezone.utc)
    assert today["comparison_end"] == datetime(2026, 10, 3, 21, tzinfo=timezone.utc)
    assert month["start"] == datetime(2026, 10, 1, 4, tzinfo=timezone.utc)
    assert month["comparison_start"] == datetime(2026, 9, 1, 4, tzinfo=timezone.utc)
    assert month["comparison_end"] == datetime(2026, 9, 4, 21, tzinfo=timezone.utc)
    assert previous_month["start"] == datetime(2026, 9, 1, 4, tzinfo=timezone.utc)
    assert previous_month["comparison_start"] == datetime(2026, 8, 1, 4, tzinfo=timezone.utc)
    assert previous_month["comparison_end"] == datetime(2026, 9, 1, 3, 59, 59, 999999, tzinfo=timezone.utc)


def test_top_products_uses_canonical_local_period_and_freshness(queried_at):
    source = SimpleNamespace(
        company_id=uuid4(),
        dataset_id=uuid4(),
        version=1,
        canonical_columns={"created": "order_timestamp", "amount": "total_amount", "order": "order_id", "product": "product_id", "quantity": "quantity"},
        rows=(
            {"created": "2026-10-04T01:00:00", "amount": 12, "order": "O1", "product": "LOCAL", "quantity": 2},
            {"created": "2026-10-04T03:00:00Z", "amount": 99, "order": "O2", "product": "UTC-PREVIOUS-DAY", "quantity": 9},
        ),
        profile=SimpleNamespace(),
        mapping=(),
        cleaning_report=SimpleNamespace(),
        quality=SimpleNamespace(),
        capability_readiness=(),
    )
    snapshot = SimpleNamespace(
        company=SimpleNamespace(timezone="America/Toronto"),
        currency="CAD",
        active_source_provider="shopify",
        active_source_type="connector",
        active_source_selected=True,
        active_source_name="Avenqo Retail Test",
        active_source_dataset_id=source.dataset_id,
        active_source_last_updated_at=queried_at - timedelta(minutes=1),
        active_source_last_event_received_at=None,
        status="ready",
        prepared=(source,),
        retail_summaries=(),
    )
    service = BusinessMetricsService()
    bounds = service.resolve_period("today", timezone_name="America/Toronto", now=queried_at, source=source)

    result = service.top_products(
        snapshot,
        source,
        top_n=5,
        metric="quantity",
        period_start=bounds["start"],
        period_end=bounds["end"],
        queried_at=queried_at,
    )

    assert result["products"] == [{"product_id": "LOCAL", "value": 2.0}]
    assert result["freshness_status"] == "SYNCED"
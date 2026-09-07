from types import SimpleNamespace

from backend.app.ai.tools.business.analytics import compute_sales_trend
from shared.ai_engine.dataset_ingestion.cleaning import CompanyDatasetCleaner


def test_slash_dates_survive_cleaning_and_feed_monthly_comparison():
    mapping = {'Order Date': 'order_timestamp', 'Sales': 'total_amount', 'Order ID': 'order_id'}
    rows, report = CompanyDatasetCleaner().clean([
        {'Order Date': '1/20/2025', 'Sales': 100, 'Order ID': 'a'},
        {'Order Date': '2/08/2025', 'Sales': 80, 'Order ID': 'b'},
        {'Order Date': '3/09/2025', 'Sales': 120, 'Order ID': 'c'},
    ], mapping)
    assert report.date_conversions == 3
    assert report.invalid_values_corrected == 0
    assert report.null_cells_detected == 0
    trend = compute_sales_trend(SimpleNamespace(rows=rows, canonical_columns=mapping))
    assert [p['revenue'] for p in trend['points']] == [100, 80, 120]
    assert [p['change_percent'] for p in trend['points']] == [None, -20, 50]


def test_ambiguous_and_invalid_dates_preserved_without_fake_corrections():
    rows, report = CompanyDatasetCleaner().clean([
        {'date': '1/2/2025'}, {'date': 'not a date'}, {'date': None},
    ], {'date': 'order_timestamp'})
    assert [r['date'] for r in rows] == ['1/2/2025', 'not a date', None]
    assert report.null_cells_detected == 1
    assert report.invalid_values_detected == 2
    assert report.invalid_values_corrected == 0


def test_missing_month_and_zero_baseline_have_no_percentage():
    source = SimpleNamespace(canonical_columns={'d': 'order_timestamp', 'v': 'total_amount'}, rows=(
        {'d': '2025-01-01', 'v': 100}, {'d': '2025-03-01', 'v': 0}, {'d': '2025-04-01', 'v': 90},
    ))
    assert all(p['change_percent'] is None for p in compute_sales_trend(source)['points'])

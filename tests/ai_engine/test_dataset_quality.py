from shared.ai_engine.dataset_ingestion.cleaning import (
    CleaningReport,
    ColumnCleaningReport,
)
from shared.ai_engine.dataset_ingestion.quality import (
    DataQualityStatus,
    NullClassification,
    assess_quality,
)


def _column(name: str, field: str | None, missing: int) -> ColumnCleaningReport:
    return ColumnCleaningReport(
        column_name=name,
        canonical_field=field,
        semantic_type="text",
        missing_values_detected=missing,
        missing_values_corrected=0,
        invalid_values_detected=0,
        invalid_values_corrected=0,
        numeric_conversions=0,
        date_conversions=0,
        boolean_conversions=0,
    )


def _report(*columns: ColumnCleaningReport) -> CleaningReport:
    return CleaningReport(
        rows_before=10,
        rows_after=10,
        duplicates_removed=0,
        numeric_conversions=0,
        date_conversions=0,
        null_cells_detected=sum(column.missing_values_detected for column in columns),
        invalid_rows=0,
        column_reports=columns,
        column_count=len(columns),
    )


def test_structural_nulls_do_not_reduce_quality() -> None:
    report = _report(
        _column("order_id", "order_id", 0),
        _column("shopify_order_gid", None, 63),
    )

    quality = assess_quality(report, required_fields=frozenset({"order_id"}))

    assert quality.status == DataQualityStatus.EXCELLENT
    assert quality.score == 100.0
    assert dict(quality.null_counts)[NullClassification.STRUCTURAL_NULL] == 63


def test_required_missing_blocks_business_readiness() -> None:
    report = _report(_column("order_id", "order_id", 3))

    quality = assess_quality(report, required_fields=frozenset({"order_id"}))

    assert quality.status == DataQualityStatus.BLOCKED
    assert quality.dimensions is not None
    assert quality.dimensions.business_readiness == 0.0


def test_invalid_values_reduce_business_readiness() -> None:
    report = CleaningReport(
        rows_before=10,
        rows_after=10,
        duplicates_removed=0,
        numeric_conversions=0,
        date_conversions=0,
        null_cells_detected=0,
        invalid_rows=8,
        invalid_values_detected=8,
        column_reports=(_column("total", "total_amount", 0),),
        column_count=1,
    )

    quality = assess_quality(report, required_fields=frozenset({"total_amount"}))

    assert quality.dimensions is not None
    assert quality.dimensions.validity == 20.0
    assert quality.dimensions.business_readiness == 20.0
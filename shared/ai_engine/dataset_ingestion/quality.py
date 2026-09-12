"""Provider-neutral, explainable dataset quality assessment."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from shared.ai_engine.dataset_ingestion.cleaning import CleaningReport


class DataQualityStatus(str, Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    WARNING = "warning"
    POOR = "poor"
    BLOCKED = "blocked"


class NullClassification(str, Enum):
    REQUIRED_MISSING = "required_missing"
    OPTIONAL_MISSING = "optional_missing"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"
    STRUCTURAL_NULL = "structural_null"


@dataclass(frozen=True, slots=True)
class QualityDimensions:
    completeness: float
    validity: float
    consistency: float
    uniqueness: float
    type_accuracy: float
    schema_coverage: float
    business_readiness: float
    mapping_confidence: float


@dataclass(frozen=True, slots=True)
class DataQualityAssessment:
    status: DataQualityStatus
    reasons: tuple[str, ...]
    score: float = 0.0
    dimensions: QualityDimensions | None = None
    null_counts: tuple[tuple[NullClassification, int], ...] = ()


def assess_quality(
    cleaning_report: CleaningReport,
    *,
    required_fields: frozenset[str] = frozenset(),
    optional_fields: frozenset[str] = frozenset(),
    not_applicable_columns: frozenset[str] = frozenset(),
    mapping_confidences: tuple[float, ...] = (),
) -> DataQualityAssessment:
    reasons: list[str] = []

    if cleaning_report.rows_after == 0:
        return DataQualityAssessment(
            status=DataQualityStatus.BLOCKED,
            reasons=("Aucune ligne exploitable après nettoyage.",),
            score=0.0,
        )

    null_counts = {classification: 0 for classification in NullClassification}
    mapped_fields: set[str] = set()
    for column in cleaning_report.column_reports:
        missing = column.missing_values_detected
        if not missing:
            if column.canonical_field:
                mapped_fields.add(column.canonical_field)
            continue
        if column.column_name in not_applicable_columns:
            classification = NullClassification.NOT_APPLICABLE
        elif column.canonical_field in required_fields:
            classification = NullClassification.REQUIRED_MISSING
        elif column.canonical_field in optional_fields:
            classification = NullClassification.OPTIONAL_MISSING
        elif column.canonical_field is None:
            classification = NullClassification.STRUCTURAL_NULL
        else:
            classification = NullClassification.UNKNOWN
        null_counts[classification] += missing
        if column.canonical_field:
            mapped_fields.add(column.canonical_field)

    classified = sum(null_counts.values())
    null_counts[NullClassification.UNKNOWN] += max(
        cleaning_report.null_cells_detected - classified, 0
    )
    relevant_missing = (
        null_counts[NullClassification.REQUIRED_MISSING]
        + null_counts[NullClassification.OPTIONAL_MISSING]
        + null_counts[NullClassification.UNKNOWN]
    )
    total_cells = max(
        cleaning_report.rows_after * max(cleaning_report.column_count, 1), 1
    )
    invalid_ratio = cleaning_report.invalid_values_detected / total_cells
    completeness = 100.0 * (1.0 - min(relevant_missing / total_cells, 1.0))
    validity = 100.0 * (1.0 - min(invalid_ratio, 1.0))
    uniqueness = 100.0 * (
        1.0 - cleaning_report.duplicates_removed / max(cleaning_report.rows_before, 1)
    )
    schema_coverage = (
        100.0
        if not required_fields
        else 100.0 * len(required_fields & mapped_fields) / len(required_fields)
    )
    mapping_confidence = (
        100.0 * sum(mapping_confidences) / len(mapping_confidences)
        if mapping_confidences
        else schema_coverage
    )
    required_missing = null_counts[NullClassification.REQUIRED_MISSING]
    business_readiness = (
        0.0
        if required_missing
        else min(completeness, validity, schema_coverage)
    )
    dimensions = QualityDimensions(
        completeness=round(completeness, 2),
        validity=round(validity, 2),
        consistency=100.0,
        uniqueness=round(uniqueness, 2),
        type_accuracy=round(validity, 2),
        schema_coverage=round(schema_coverage, 2),
        business_readiness=round(business_readiness, 2),
        mapping_confidence=round(mapping_confidence, 2),
    )
    score = round(sum(dimensions.__getattribute__(name) for name in dimensions.__slots__) / 8, 2)

    if required_missing:
        status = DataQualityStatus.BLOCKED
        reasons.append(f"{required_missing} valeur(s) requise(s) manquante(s).")
    elif score >= 90:
        status = DataQualityStatus.EXCELLENT
    elif score >= 80:
        status = DataQualityStatus.GOOD
    elif score >= 65:
        status = DataQualityStatus.FAIR
    elif score >= 45:
        status = DataQualityStatus.POOR
    else:
        status = DataQualityStatus.BLOCKED

    structural = (
        null_counts[NullClassification.STRUCTURAL_NULL]
        + null_counts[NullClassification.NOT_APPLICABLE]
    )
    if structural:
        reasons.append(f"{structural} valeur(s) structurelle(s) exclue(s) du score.")
    if cleaning_report.duplicates_removed:
        reasons.append(f"{cleaning_report.duplicates_removed} ligne(s) dupliquée(s) supprimée(s).")
    if not reasons:
        reasons.append("Aucune anomalie significative détectée.")

    return DataQualityAssessment(
        status=status,
        reasons=tuple(reasons),
        score=score,
        dimensions=dimensions,
        null_counts=tuple(null_counts.items()),
    )

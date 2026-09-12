"""Conservative readiness gate for feature-ready model training inputs."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class MLReadinessAssessment:
    ready: bool
    code: str
    reasons: tuple[str, ...]


def assess_ml_readiness(
    rows: Sequence[Mapping[str, Any]],
    *,
    family: str,
    target_column: str | None = None,
    time_column: str | None = None,
    minimum_samples: int | None = None,
) -> MLReadinessAssessment:
    minimum = minimum_samples or (
        10 if family in {"clustering", "anomaly_detection"} else 20
    )
    reasons: list[str] = []
    if len(rows) < minimum:
        reasons.append(f"minimum_samples:{minimum}")

    duplicate_count = len(rows) - len({_fingerprint(row) for row in rows})
    if rows and duplicate_count / len(rows) > 0.5:
        reasons.append("duplicate_rate_above_50_percent")

    if family not in {"clustering", "anomaly_detection", "recommendation"}:
        if not target_column:
            reasons.append("target_unavailable")
        else:
            target = [row.get(target_column) for row in rows]
            present = [value for value in target if value not in (None, "")]
            if len(present) != len(rows):
                reasons.append("target_missing_values")
            distribution = Counter(str(value) for value in present)
            if len(distribution) < 2:
                reasons.append("target_has_no_variation")
            if family == "classification" and distribution and min(distribution.values()) < 2:
                reasons.append("class_distribution_insufficient")

    if family == "forecasting":
        if not time_column:
            reasons.append("time_column_unavailable")
        elif any(row.get(time_column) in (None, "") for row in rows):
            reasons.append("temporal_values_missing")

    return MLReadinessAssessment(
        ready=not reasons,
        code="READY_FOR_ML" if not reasons else "DATASET_NOT_READY_FOR_ML",
        reasons=tuple(reasons),
    )


def _fingerprint(row: Mapping[str, Any]) -> str:
    return repr(sorted((str(key), repr(value)) for key, value in row.items()))
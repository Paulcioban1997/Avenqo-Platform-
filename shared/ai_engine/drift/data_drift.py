"""Data Drift & Feature Drift — changement de distribution des variables.

Une seule fonction (`detect_feature_drift`) implémente la logique par
variable ; elle est réutilisée telle quelle pour le Prediction Drift et le
Target Drift (voir `prediction_drift.py`/`drift_detector.py`) — zéro
duplication entre les quatre types de drift demandés.
"""

from __future__ import annotations

from typing import Sequence

import pandas as pd

from shared.ai_engine.drift.statistics import (
    category_proportions,
    chi_square_test,
    jensen_shannon_distance,
    kl_divergence,
    kolmogorov_smirnov,
    population_stability_index,
    population_stability_index_categorical,
    wasserstein_distance,
)
from shared.ai_engine.drift.thresholds import classify_js, classify_p_value, classify_psi
from shared.ai_engine.drift.types import DataDriftReport, DriftSeverity, FeatureDriftResult, max_severity


def detect_feature_drift(
    name: str,
    reference: pd.Series,
    current: pd.Series,
    is_categorical: bool,
    include_kl_divergence: bool = False,
) -> FeatureDriftResult:
    """Détecte le drift d'une seule variable — choisit les tests adaptés à son type."""

    if is_categorical:
        return _detect_categorical_drift(name, reference, current, include_kl_divergence)
    return _detect_numerical_drift(name, reference, current)


def detect_data_drift(
    reference_features: pd.DataFrame,
    current_features: pd.DataFrame,
    numerical_columns: Sequence[str],
    categorical_columns: Sequence[str],
) -> DataDriftReport:
    """Détecte le drift de toutes les variables communes aux deux jeux de données."""

    results: list[FeatureDriftResult] = []
    for column in (*numerical_columns, *categorical_columns):
        if column not in reference_features or column not in current_features:
            continue
        results.append(
            detect_feature_drift(
                column,
                reference_features[column],
                current_features[column],
                is_categorical=column in categorical_columns,
            )
        )

    drifted_count = sum(1 for result in results if result.drifted)
    ratio = drifted_count / len(results) if results else 0.0
    overall = max_severity(*(result.severity for result in results)) if results else DriftSeverity.NONE
    return DataDriftReport(
        features=tuple(results),
        drifted_feature_ratio=ratio,
        overall_severity=overall,
    )


def _detect_numerical_drift(name: str, reference: pd.Series, current: pd.Series) -> FeatureDriftResult:
    reference_values = pd.to_numeric(reference, errors="coerce").dropna().to_numpy()
    current_values = pd.to_numeric(current, errors="coerce").dropna().to_numpy()
    if reference_values.size < 2 or current_values.size < 2:
        return FeatureDriftResult(name, {}, DriftSeverity.NONE, False)

    psi = population_stability_index(reference_values, current_values)
    ks_statistic, ks_p_value = kolmogorov_smirnov(reference_values, current_values)
    distance = wasserstein_distance(reference_values, current_values)
    severity = max_severity(classify_psi(psi), classify_p_value(ks_p_value))
    tests = {
        "psi": psi,
        "ks_statistic": ks_statistic,
        "ks_p_value": ks_p_value,
        "wasserstein_distance": distance,
    }
    return FeatureDriftResult(name, tests, severity, severity != DriftSeverity.NONE)


def _detect_categorical_drift(
    name: str,
    reference: pd.Series,
    current: pd.Series,
    include_kl_divergence: bool,
) -> FeatureDriftResult:
    reference_values = reference.dropna()
    current_values = current.dropna()
    if reference_values.empty or current_values.empty:
        return FeatureDriftResult(name, {}, DriftSeverity.NONE, False)

    reference_proportions, current_proportions = category_proportions(
        reference_values.to_numpy(), current_values.to_numpy()
    )
    psi = population_stability_index_categorical(reference_proportions, current_proportions)
    reference_counts = (reference_proportions * reference_values.size).round()
    current_counts = (current_proportions * current_values.size).round()
    chi_statistic, chi_p_value = chi_square_test(reference_counts, current_counts)
    js_distance = jensen_shannon_distance(reference_proportions, current_proportions)
    severity = max_severity(classify_psi(psi), classify_p_value(chi_p_value), classify_js(js_distance))
    tests = {
        "psi": psi,
        "chi_square_statistic": chi_statistic,
        "chi_square_p_value": chi_p_value,
        "jensen_shannon_distance": js_distance,
    }
    if include_kl_divergence:
        tests["kl_divergence"] = kl_divergence(reference_proportions, current_proportions)
    return FeatureDriftResult(name, tests, severity, severity != DriftSeverity.NONE)

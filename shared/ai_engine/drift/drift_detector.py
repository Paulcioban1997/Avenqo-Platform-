"""`DriftDetector` — orchestrateur unique combinant les quatre types de drift.

Point d'entrée algorithmique pur (aucun accès disque/registre ici — voir
`service.py` pour l'intégration avec le `ModelRegistry`).
"""

from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd

from shared.ai_engine.drift.concept_drift import detect_concept_drift
from shared.ai_engine.drift.data_drift import detect_data_drift, detect_feature_drift
from shared.ai_engine.drift.prediction_drift import detect_prediction_drift
from shared.ai_engine.drift.types import DriftReport, DriftSeverity, ReferenceBaseline, max_severity


class DriftDetector:
    """Compare des données/prédictions/métriques actuelles à une `ReferenceBaseline`."""

    def run(
        self,
        reference: ReferenceBaseline,
        current_features: pd.DataFrame,
        current_predictions: np.ndarray | None = None,
        current_target: pd.Series | None = None,
        current_metrics: Mapping[str, float] | None = None,
    ) -> DriftReport:
        data_drift = detect_data_drift(
            reference.features,
            current_features,
            reference.numerical_columns,
            reference.categorical_columns,
        )

        prediction_drift = None
        if reference.predictions is not None and current_predictions is not None:
            prediction_drift = detect_prediction_drift(
                reference.predictions, current_predictions, reference.task_type
            )

        target_drift = None
        if reference.target is not None and current_target is not None:
            target_drift = detect_feature_drift(
                "target",
                reference.target,
                current_target,
                is_categorical=reference.task_type == "classification",
            )

        concept_drift = detect_concept_drift(reference.metrics, current_metrics, reference.task_type)

        overall = max_severity(
            data_drift.overall_severity,
            prediction_drift.severity if prediction_drift is not None else DriftSeverity.NONE,
            target_drift.severity if target_drift is not None else DriftSeverity.NONE,
            concept_drift.severity,
        )
        return DriftReport(
            model_name=reference.model_name,
            task_type=reference.task_type,
            data_drift=data_drift,
            prediction_drift=prediction_drift,
            target_drift=target_drift,
            concept_drift=concept_drift,
            overall_severity=overall,
        )

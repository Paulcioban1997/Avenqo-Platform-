"""Prediction Drift — changement de distribution des prédictions du modèle.

Réutilise `detect_feature_drift` de `data_drift.py` (zéro duplication) : les
prédictions sont traitées comme une variable catégorielle (classes prédites)
en classification, ou continue (valeurs prédites) en régression.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

from shared.ai_engine.drift.data_drift import detect_feature_drift
from shared.ai_engine.drift.types import PredictionDriftReport


def detect_prediction_drift(
    reference_predictions: np.ndarray,
    current_predictions: np.ndarray,
    task_type: Literal["classification", "regression"],
) -> PredictionDriftReport:
    """Détecte un changement de distribution des sorties du modèle.

    En classification, la divergence de Jensen-Shannon est activée en plus de
    PSI/Chi carré : comparer deux distributions de classes prédites est
    précisément son cas d'usage classique en monitoring de modèles.
    """

    result = detect_feature_drift(
        "prediction",
        pd.Series(reference_predictions),
        pd.Series(current_predictions),
        is_categorical=task_type == "classification",
        include_kl_divergence=task_type == "classification",
    )
    return PredictionDriftReport(tests=result.tests, severity=result.severity, drifted=result.drifted)

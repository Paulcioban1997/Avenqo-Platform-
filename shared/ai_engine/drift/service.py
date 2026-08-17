"""Point d'entrée unique de la couche Drift Detection (interne, admin uniquement).

`capture_reference_baseline` est appelée à l'entraînement (pipelines
`training/train_*.py`) pour figer un échantillon borné du split de test comme
référence. `run_drift_check` est appelée plus tard — uniquement après qu'un
modèle est actif (voir `backend/app/services/training_dispatcher.py`) —
jamais pendant l'entraînement lui-même, donc sans jamais le ralentir.
"""

from __future__ import annotations

import logging
from typing import Literal, Mapping

import numpy as np
import pandas as pd

from shared.ai_engine.drift.drift_detector import DriftDetector
from shared.ai_engine.drift.types import (
    ConceptDriftReport,
    DataDriftReport,
    DriftReport,
    DriftSeverity,
    ReferenceBaseline,
)
from shared.ai_engine.preprocessing.tabular import FeatureColumns

logger = logging.getLogger(__name__)

# Borne la taille de l'échantillon de référence conservé : suffisant pour des
# tests statistiques fiables, sans jamais stocker un jeu de données complet
# (scalable, à l'inverse d'un simple "copier toutes les données d'entraînement").
MAX_BASELINE_SAMPLE_SIZE = 2000


def capture_reference_baseline(
    features: pd.DataFrame,
    predictions: np.ndarray | None,
    target: pd.Series | None,
    metrics: Mapping[str, float],
    model_name: str,
    task_type: Literal["classification", "regression"],
    columns: FeatureColumns,
    random_seed: int = 42,
    max_samples: int = MAX_BASELINE_SAMPLE_SIZE,
) -> ReferenceBaseline:
    """Fige un échantillon borné du split de test comme baseline de référence."""

    total = len(features)
    if total > max_samples:
        positions = np.sort(np.random.RandomState(random_seed).choice(total, size=max_samples, replace=False))
    else:
        positions = np.arange(total)

    sampled_features = features.iloc[positions].reset_index(drop=True)
    sampled_predictions = np.asarray(predictions)[positions] if predictions is not None else None
    sampled_target = (
        target.iloc[positions].reset_index(drop=True) if target is not None else None
    )
    return ReferenceBaseline(
        model_name=model_name,
        task_type=task_type,
        features=sampled_features,
        predictions=sampled_predictions,
        target=sampled_target,
        metrics=dict(metrics),
        numerical_columns=columns.numerical,
        categorical_columns=columns.categorical,
    )


def run_drift_check(
    reference: ReferenceBaseline,
    current_features: pd.DataFrame,
    current_predictions: np.ndarray | None = None,
    current_target: pd.Series | None = None,
    current_metrics: Mapping[str, float] | None = None,
) -> DriftReport:
    """Exécute la détection de drift complète — ne lève jamais.

    Best-effort : toute erreur (colonnes incompatibles, données insuffisantes,
    etc.) est absorbée et journalisée, en retournant un rapport "non disponible"
    plutôt que de faire échouer le déploiement du nouveau modèle.
    """

    try:
        return DriftDetector().run(
            reference, current_features, current_predictions, current_target, current_metrics
        )
    except Exception:
        logger.warning(
            "Échec du calcul de drift pour %s : rapport indisponible.",
            reference.model_name,
            exc_info=True,
        )
        return DriftReport(
            model_name=reference.model_name,
            task_type=reference.task_type,
            data_drift=DataDriftReport(features=(), drifted_feature_ratio=0.0, overall_severity=DriftSeverity.NONE),
            prediction_drift=None,
            target_drift=None,
            concept_drift=ConceptDriftReport(
                available=False,
                metric_name=None,
                reference_value=None,
                current_value=None,
                degradation_ratio=None,
                severity=DriftSeverity.NONE,
                drifted=False,
            ),
            overall_severity=DriftSeverity.NONE,
        )

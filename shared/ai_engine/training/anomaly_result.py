"""Résultat public d'un entraînement de détection d'anomalies (IsolationForest)."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from sklearn.pipeline import Pipeline


@dataclass(frozen=True, slots=True)
class AnomalyTrainingResult:
    """Expose le meilleur modèle, ses labels, ses métriques et ses fichiers.

    Même forme que `ClusteringTrainingResult` : non supervisé, aucune colonne
    cible. `labels` suit la convention sklearn (``1`` = normal, ``-1`` =
    anomalie).
    """

    model_name: str
    pipeline: Pipeline
    best_parameters: Mapping[str, Any]
    metrics: Mapping[str, float]
    labels: np.ndarray
    numerical_columns: tuple[str, ...]
    categorical_columns: tuple[str, ...]
    model_path: Path
    preprocessor_path: Path

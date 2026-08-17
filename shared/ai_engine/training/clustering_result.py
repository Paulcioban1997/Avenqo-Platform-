"""Résultat public d'un entraînement de regroupement sklearn."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from sklearn.pipeline import Pipeline


@dataclass(frozen=True, slots=True)
class ClusteringTrainingResult:
    """Expose le meilleur modèle, ses groupes, ses métriques et ses fichiers."""

    model_name: str
    pipeline: Pipeline
    best_parameters: Mapping[str, Any]
    metrics: Mapping[str, float]
    labels: np.ndarray
    numerical_columns: tuple[str, ...]
    categorical_columns: tuple[str, ...]
    model_path: Path
    preprocessor_path: Path
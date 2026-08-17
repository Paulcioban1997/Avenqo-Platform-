"""Calcul des métriques des réseaux neuronaux TensorFlow/Keras.

Autorité unique d'évaluation des modèles Deep Learning, utilisée par le
pipeline officiel de `shared.ai_engine.training`.
"""

from math import sqrt
from typing import Any, Literal, Mapping

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
)


def decode_neural_predictions(
    raw_predictions: np.ndarray,
    task_type: Literal["classification", "regression"],
) -> np.ndarray:
    """Convertit les sorties brutes d'un réseau Keras en valeurs/classes prédites.

    Source unique de cette conversion : réutilisée par `evaluate_neural_network`
    ci-dessous et par `explainability.permutation_importance` (permutation
    importance des réseaux de neurones).
    """

    raw = np.asarray(raw_predictions)
    if task_type == "regression":
        return raw.reshape(-1)
    return (
        (raw.reshape(-1) >= 0.5).astype(int)
        if raw.shape[-1] == 1
        else np.argmax(raw, axis=1)
    )


def evaluate_neural_network(
    model: Any,
    features: np.ndarray,
    target: np.ndarray,
    task_type: Literal["classification", "regression"],
) -> Mapping[str, float]:
    """Convertit les sorties neuronales puis calcule les métriques métier."""

    raw_predictions = np.asarray(model.predict(features, verbose=0))
    predictions = decode_neural_predictions(raw_predictions, task_type)
    if task_type == "regression":
        mse = mean_squared_error(target, predictions)
        return {
            "mae": float(mean_absolute_error(target, predictions)),
            "rmse": float(sqrt(mse)),
            "r2": float(r2_score(target, predictions)),
        }

    return {
        "accuracy": float(accuracy_score(target, predictions)),
        "precision": float(
            precision_score(target, predictions, average="weighted", zero_division=0)
        ),
        "recall": float(recall_score(target, predictions, average="weighted")),
        "f1": float(f1_score(target, predictions, average="weighted")),
    }

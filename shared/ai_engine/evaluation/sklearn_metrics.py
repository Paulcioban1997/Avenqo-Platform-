"""Calcul des métriques et des importances d'un modèle sklearn.

Autorité unique d'évaluation des modèles ML tabulaires (classification et
régression), utilisée par le pipeline officiel de `shared.ai_engine.training`.
"""

from dataclasses import dataclass
from math import sqrt
from typing import Literal, Mapping

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline

from shared.ai_engine.explainability.feature_importance import compute_native_importance
from shared.ai_engine.explainability.permutation_importance import (
    compute_permutation_importance,
)


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    metrics: Mapping[str, float]
    feature_importance: Mapping[str, float]
    permutation_importance: Mapping[str, float]


def evaluate_model(
    pipeline: Pipeline,
    features: pd.DataFrame,
    target: pd.Series,
    task_type: Literal["classification", "regression"],
    random_seed: int = 42,
) -> EvaluationReport:
    """Évalue le Pipeline sur des données qui n'ont pas servi à l'entraîner."""

    predictions = pipeline.predict(features)
    metrics = (
        _classification_metrics(pipeline, features, target, predictions)
        if task_type == "classification"
        else _regression_metrics(target, predictions)
    )
    scoring = "accuracy" if task_type == "classification" else "neg_root_mean_squared_error"
    return EvaluationReport(
        metrics=metrics,
        feature_importance=compute_native_importance(pipeline),
        permutation_importance=compute_permutation_importance(
            pipeline,
            features,
            target,
            scoring,
            random_seed,
        ),
    )


def _classification_metrics(
    pipeline: Pipeline,
    features: pd.DataFrame,
    target: pd.Series,
    predictions: np.ndarray,
) -> dict[str, float]:
    metrics = {
        "accuracy": float(accuracy_score(target, predictions)),
        "precision": float(
            precision_score(target, predictions, average="weighted", zero_division=0)
        ),
        "recall": float(recall_score(target, predictions, average="weighted")),
        "f1": float(f1_score(target, predictions, average="weighted")),
    }
    if target.nunique() == 2 and hasattr(pipeline, "predict_proba"):
        probabilities = pipeline.predict_proba(features)[:, 1]
        metrics["roc_auc"] = float(roc_auc_score(target, probabilities))
    return metrics


def _regression_metrics(target: pd.Series, predictions: np.ndarray) -> dict[str, float]:
    mse = mean_squared_error(target, predictions)
    return {
        "mae": float(mean_absolute_error(target, predictions)),
        "rmse": float(sqrt(mse)),
        "r2": float(r2_score(target, predictions)),
    }




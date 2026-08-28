"""Naive baselines and activation gates for supervised model candidates."""

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
)


@dataclass(frozen=True, slots=True)
class ModelQualityDecision:
    baseline_metrics: Mapping[str, float]
    approved: bool
    reason: str


def compare_with_naive_baseline(
    train_target: pd.Series,
    test_target: pd.Series,
    candidate_metrics: Mapping[str, float],
    task_type: Literal["classification", "regression"],
) -> ModelQualityDecision:
    """Compare held-out candidate metrics with a baseline fitted on training data only."""

    if task_type == "classification":
        majority_class = train_target.mode(dropna=False).iloc[0]
        predictions = np.full(len(test_target), majority_class)
        baseline_metrics = {
            "accuracy": float(accuracy_score(test_target, predictions)),
            "precision": float(
                precision_score(test_target, predictions, average="weighted", zero_division=0)
            ),
            "recall": float(recall_score(test_target, predictions, average="weighted")),
            "f1": float(f1_score(test_target, predictions, average="weighted")),
        }
        candidate_value = candidate_metrics.get("f1")
        approved = candidate_value is not None and candidate_value >= baseline_metrics["f1"]
        reason = "candidate_meets_majority_baseline" if approved else "candidate_below_majority_baseline"
    else:
        mean_value = float(train_target.mean())
        predictions = np.full(len(test_target), mean_value)
        mse = mean_squared_error(test_target, predictions)
        baseline_metrics = {
            "mae": float(mean_absolute_error(test_target, predictions)),
            "rmse": float(sqrt(mse)),
            "r2": float(r2_score(test_target, predictions)),
        }
        candidate_value = candidate_metrics.get("rmse")
        approved = candidate_value is not None and candidate_value <= baseline_metrics["rmse"]
        reason = "candidate_meets_mean_baseline" if approved else "candidate_below_mean_baseline"

    return ModelQualityDecision(
        baseline_metrics=baseline_metrics,
        approved=approved,
        reason=reason,
    )
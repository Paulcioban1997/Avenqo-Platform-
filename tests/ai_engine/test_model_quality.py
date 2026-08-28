import pandas as pd

from shared.ai_engine.evaluation.model_quality import compare_with_naive_baseline


def test_classification_candidate_must_beat_training_majority_baseline() -> None:
    train = pd.Series([0, 0, 0, 1])
    test = pd.Series([0, 0, 1, 1])

    rejected = compare_with_naive_baseline(train, test, {"f1": 0.33}, "classification")
    approved = compare_with_naive_baseline(train, test, {"f1": 0.75}, "classification")

    assert rejected.baseline_metrics["accuracy"] == 0.5
    assert rejected.baseline_metrics["f1"] > 0.3
    assert rejected.approved is False
    assert approved.approved is True


def test_regression_candidate_must_beat_training_mean_baseline() -> None:
    train = pd.Series([1.0, 2.0, 3.0])
    test = pd.Series([2.0, 4.0])

    rejected = compare_with_naive_baseline(train, test, {"rmse": 2.0}, "regression")
    approved = compare_with_naive_baseline(train, test, {"rmse": 1.0}, "regression")

    assert rejected.baseline_metrics["rmse"] > 1.0
    assert rejected.approved is False
    assert approved.approved is True
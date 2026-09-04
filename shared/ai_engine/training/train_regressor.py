"""Entraînement complet des modèles de régression sklearn."""

from pathlib import Path
from time import perf_counter
from typing import Any, Mapping

import pandas as pd
from sklearn.base import BaseEstimator, clone
from sklearn.model_selection import train_test_split

from shared.ai_engine.architectures.machine_learning.optimizer import run_hyperparameter_search
from shared.ai_engine.contracts import DatasetArtifact
from shared.ai_engine.drift.service import capture_reference_baseline
from shared.ai_engine.evaluation.sklearn_metrics import evaluate_model
from shared.ai_engine.evaluation.model_quality import compare_with_naive_baseline
from shared.ai_engine.explainability.service import explain_supervised
from shared.ai_engine.preprocessing.data_sampling import sample_features_and_target
from shared.ai_engine.preprocessing.tabular import (
    build_model_pipeline,
    build_preprocessor,
    detect_feature_columns,
)
from shared.ai_engine.training.experiment_logger import ExperimentLogger
from shared.ai_engine.training.model_saver import save_model
from shared.ai_engine.training.run_context import TrainingRunContext
from shared.ai_engine.training.train_classifier import _split_target
from shared.ai_engine.training.training_result import SupervisedTrainingResult


def train_regressor(
    data: pd.DataFrame,
    target_column: str,
    dataset: DatasetArtifact,
    version: str,
    run_context: TrainingRunContext,
    estimators: Mapping[str, BaseEstimator],
    parameter_spaces: Mapping[str, Mapping[str, Any]],
    destination: Path,
    experiment_logger: ExperimentLogger,
    test_size: float = 0.2,
    random_seed: int = 42,
    cross_validation_folds: int = 3,
    search_max_rows: int | None = None,
    final_fit_max_rows: int | None = None,
    permutation_max_rows: int | None = None,
    explanation_max_rows: int | None = None,
    max_parallel_jobs: int = 1,
) -> SupervisedTrainingResult:
    """Exécute toutes les étapes d'une régression supervisée."""

    run = experiment_logger.start(dataset, version, run_context)
    started = perf_counter()
    try:
        features, target = _split_target(data, target_column)
        columns = detect_feature_columns(features)
        train_features, test_features, train_target, test_target = train_test_split(
            features,
            target,
            test_size=test_size,
            random_state=random_seed,
        )
        preprocessor = build_preprocessor(columns)
        pipelines = {
            name: build_model_pipeline(preprocessor, estimator, "regression")
            for name, estimator in estimators.items()
        }
        search_features, search_target = sample_features_and_target(
            train_features,
            train_target,
            search_max_rows,
            random_seed=random_seed,
        )
        search = run_hyperparameter_search(
            pipelines,
            parameter_spaces,
            search_features,
            search_target,
            run_context.search_method,
            scoring="neg_root_mean_squared_error",
            cross_validation_folds=cross_validation_folds,
            random_seed=random_seed,
            max_parallel_jobs=max_parallel_jobs,
        )
        fit_features, fit_target = sample_features_and_target(
            train_features,
            train_target,
            final_fit_max_rows,
            random_seed=random_seed,
        )
        final_pipeline = clone(search.best_pipeline)
        final_pipeline.fit(fit_features, fit_target)
        report = evaluate_model(
            final_pipeline,
            test_features,
            test_target,
            "regression",
            random_seed,
            permutation_max_rows=permutation_max_rows,
            permutation_max_parallel_jobs=max_parallel_jobs,
        )
        explanation_features, _ = sample_features_and_target(
            test_features,
            test_target,
            explanation_max_rows,
            random_seed=random_seed,
        )
        quality = compare_with_naive_baseline(
            train_target,
            test_target,
            report.metrics,
            "regression",
        )
        explanation = explain_supervised(
            final_pipeline,
            explanation_features,
            search.model_name,
            "regression",
            report.feature_importance,
            report.permutation_importance,
        )
        reference_baseline = capture_reference_baseline(
            test_features,
            final_pipeline.predict(test_features),
            test_target,
            report.metrics,
            search.model_name,
            "regression",
            columns,
            random_seed,
        )
        paths = save_model(final_pipeline, destination)
        experiment_logger.complete(
            run,
            run_context,
            search.model_name,
            search.parameter_space,
            search.best_parameters,
            report.metrics,
            paths.model,
            paths.preprocessor,
            perf_counter() - started,
            columns.numerical,
            columns.categorical,
        )
        return SupervisedTrainingResult(
            model_name=search.model_name,
            pipeline=final_pipeline,
            best_parameters=search.best_parameters,
            metrics=report.metrics,
            feature_importance=report.feature_importance,
            permutation_importance=report.permutation_importance,
            numerical_columns=columns.numerical,
            categorical_columns=columns.categorical,
            model_path=paths.model,
            preprocessor_path=paths.preprocessor,
            baseline_metrics=quality.baseline_metrics,
            quality_approved=quality.approved,
            quality_reason=quality.reason,
            explanation=explanation,
            reference_baseline=reference_baseline,
        )
    except Exception:
        experiment_logger.fail(run, perf_counter() - started)
        raise

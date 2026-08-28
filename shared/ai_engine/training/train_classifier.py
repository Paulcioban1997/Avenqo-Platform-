"""Entraînement complet des modèles de classification sklearn."""

import logging
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
from shared.ai_engine.preprocessing.imbalance import analyze_class_balance, build_resampler
from shared.ai_engine.preprocessing.tabular import (
    build_model_pipeline,
    build_preprocessor,
    build_resampling_pipeline,
    detect_feature_columns,
)
from shared.ai_engine.training.experiment_logger import ExperimentLogger
from shared.ai_engine.training.model_saver import save_model
from shared.ai_engine.training.run_context import TrainingRunContext
from shared.ai_engine.training.training_result import SupervisedTrainingResult

logger = logging.getLogger(__name__)


def train_classifier(
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
) -> SupervisedTrainingResult:
    """Exécute toutes les étapes d'une classification supervisée."""

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
            stratify=target,
        )
        preprocessor = build_preprocessor(columns)
        imbalance = analyze_class_balance(train_target)
        # Une CV stratifiée exige au moins `folds` échantillons dans la classe minoritaire.
        effective_folds = max(2, min(cross_validation_folds, imbalance.minority_class_count or cross_validation_folds))
        resampler = build_resampler(columns, imbalance, random_seed, cv_folds=effective_folds)
        if resampler is not None:
            logger.info(
                "Déséquilibre détecté (ratio=%.2f) : ré-échantillonnage %s appliqué.",
                imbalance.ratio,
                type(resampler).__name__,
            )
            pipelines = {
                name: build_resampling_pipeline(columns, estimator, "classification", clone(resampler))
                for name, estimator in estimators.items()
            }
        else:
            pipelines = {
                name: build_model_pipeline(preprocessor, estimator, "classification")
                for name, estimator in estimators.items()
            }
        search = run_hyperparameter_search(
            pipelines,
            parameter_spaces,
            train_features,
            train_target,
            run_context.search_method,
            scoring="accuracy",
            cross_validation_folds=effective_folds,
            random_seed=random_seed,
        )
        report = evaluate_model(
            search.best_pipeline,
            test_features,
            test_target,
            "classification",
            random_seed,
        )
        quality = compare_with_naive_baseline(
            train_target,
            test_target,
            report.metrics,
            "classification",
        )
        explanation = explain_supervised(
            search.best_pipeline,
            test_features,
            search.model_name,
            "classification",
            report.feature_importance,
            report.permutation_importance,
        )
        reference_baseline = capture_reference_baseline(
            test_features,
            search.best_pipeline.predict(test_features),
            test_target,
            report.metrics,
            search.model_name,
            "classification",
            columns,
            random_seed,
        )
        paths = save_model(search.best_pipeline, destination)
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
            pipeline=search.best_pipeline,
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


def _split_target(data: pd.DataFrame, target_column: str) -> tuple[pd.DataFrame, pd.Series]:
    if target_column not in data:
        raise ValueError(f"Colonne cible absente: {target_column}")
    return data.drop(columns=[target_column]), data[target_column]